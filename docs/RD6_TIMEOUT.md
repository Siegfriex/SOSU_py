# RD-6 — GEMINI_TIMEOUT_OBSERVE 45 → 60 s

Status: **adopted (code default 60 s)**, Phase 3, 2026-10-18. No live Gemini calls were made; the
evidence below comes from reading the code and from deterministic tests.

## Constraints (unchanged)

| Item | Value | Where |
|---|---|---|
| Request deadline | 180 s | `SOSU_REQUEST_DEADLINE_SECONDS` (`app/config.py`) |
| Vercel function limit | 200 s | `vercel.json` `functions."app/main.py".maxDuration` |
| Synthesis / repair stage | 90 s / 40 s | `GEMINI_TIMEOUT_SYNTHESIS` / `GEMINI_TIMEOUT_REPAIR` |

With observe at 60 s, the worst case is 60 + 90 + 40 = **190 s, more than 180 s**. Before this
change the stages were independent: each call used its full configured timeout, and only the outer
`with_deadline` (`asyncio.timeout`) cut the request. That was already safe against the Vercel kill.
The weak spots were these:

- a late stage could start with less time left than it needed, so it was cancelled by the outer
  timeout instead of its own;
- `http_options.timeout` and the tenacity retry ignored the remaining time;
- the old test `test_stage_timeouts_fit_inside_overall_deadline` (sum ≤ deadline) would have failed
  with 60.

## What changed

1. **Remaining-budget propagation** (`app/services/deadline.py`):
   - While it is active, `with_deadline` publishes the absolute deadline in a ContextVar.
   - `budget_spec(spec)` sets `timeout_seconds = min(stage_timeout, remaining − margin)`. If
     `remaining − margin < min_stage`, it raises `MODEL_TIMEOUT` with
     `details=[{"deadline_seconds", "stage"}]` and the stage is **never started**.
   - The margin is 2 s and the minimum stage is 3 s. Both scale down (5 % and 10 % of the deadline)
     for tiny test deadlines.
   - Applied at:
     - diagnosis observe and synthesis (`diagnosis_service.py`);
     - prescription observe and synthesis (`prescription_service.py`, the `budget_spec(...)`
       wrapper only);
     - repair, for both workflows, right before the call (`repair.py`).
   - Outside `with_deadline`, nothing changes: specs pass through as they are.
2. **Retry inside the stage budget** (`app/gemini/client.py`):
   - The stage timeout, already capped by the request budget, now bounds **all attempts together**.
   - The single tenacity retry gets only what is left after attempt 1 and the backoff.
   - If that is less than min(3 s, 10 % of the stage), the retry is skipped with `MODEL_TIMEOUT`.
   - `wait_for` and `http_options.timeout` use the per-attempt remainder.
3. **Default** `gemini_timeout_observe = 60.0`. `.env.example` now says `GEMINI_TIMEOUT_OBSERVE=60`.

## Why 60 s is safe

- **The deadline is always enforced.** `asyncio.timeout(180)` cancels the in-flight
  `generate_content` coroutine. `CancelledError` is a `BaseException`, so the gateway's
  `except Exception` does not swallow it. The outer timeout maps it to `MODEL_TIMEOUT`, and the API
  returns a 504 envelope.
- **Stages are capped by remaining time.** In the worst case (observe 59 s, synthesis 89 s), repair
  gets min(40, 180 − 148 − 2) = 30 s and ends at about 178 s with `MODEL_TIMEOUT`. That is a
  structured 504, about 22 s before the 200 s Vercel kill.
- **Late stages are not started.** When less than 3 s would be usable, the next stage is refused
  instead of being started and then killed.
- **Retry cannot extend a stage.** It is bounded by the stage timeout, and the stage timeout is
  bounded by the remaining budget.

## Evidence (deterministic tests, no live calls)

`tests/test_deadline_budget.py` (13 tests) runs the pipeline at a tiny scale with a gateway that
honours `spec.timeout_seconds` the way the real client does:

- unit arithmetic:
  - pass-through outside a deadline;
  - kept when the budget is ample;
  - capped at remaining − margin;
  - refused below the minimum;
- slow observation → `MODEL_TIMEOUT` before the deadline; synthesis is never started;
- observation slow but within its timeout → synthesis gets a reduced timeout (about 0.32 s instead
  of 0.4 s), for both diagnosis and prescription;
- budget exhausted after synthesis → repair is never started (`details.stage = repair prompt`);
- worst case 60/90/40 against 180, scaled by 1/100 → `MODEL_TIMEOUT` at about 1.71 s, below the
  1.8 s deadline, with repair capped below 0.4 s;
- the real `GoogleGenAIGateway` under `with_deadline(0.1)` → the in-flight provider call is
  **cancelled**, one call, `MODEL_TIMEOUT` with `deadline_seconds`;
- retry skipped when the stage budget is spent; the retry attempt gets only the rest of the stage;
- HTTP: `TestClient` POST `/api/v1/diagnosis` → **504** `MODEL_TIMEOUT` envelope (`ok=false`,
  `contract_version`, `request_id`, `retryable=true`).

`tests/test_timeouts.py` changes:

- It asserts the **code defaults** (60/90/40/180) with `.env`/`.env.local` ignored.
- It replaces the sum ≤ deadline test with two checks: each stage is shorter than the deadline
  minus the margin, and the `vercel.json` maxDuration is at least the deadline plus 10.

## Notes / residual risk

- **Owner's `.env.local` still sets `GEMINI_TIMEOUT_OBSERVE=45`.** It overrides the default
  locally, so local runs keep 45 until the owner edits that file. Agents do not edit it.
- **Vercel production sets no `GEMINI_TIMEOUT_*` env,** so the code default of 60 s applies there.
- **The 180 s clock starts at `service.run`.** Multipart parsing, upload, normalizing up to three
  4 MB images, and any cold start all happen before it, and they come out of the 20 s gap to
  `maxDuration`. If that gap ever proves too small, lower `SOSU_REQUEST_DEADLINE_SECONDS`. Do not
  raise `maxDuration` without checking the plan limit (see docs/VERCEL.md).
- **The extra 15 s of observation budget is not measured against real latency.** The live smokes
  (29 s diagnosis, 47 s prescription, 4 calls in total) never came close to 45 s, so 60 s is
  headroom, not a measured need. Its cost is that a slow observation can now consume more of the
  synthesis budget, and synthesis then gets the remainder.
