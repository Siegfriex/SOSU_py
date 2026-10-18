# Live Gemini smoke (Phase 2)

Run: `cd SOSU_py && .venv/bin/python scripts/live_smoke.py` (key read only via `app.config.get_settings()`).

- Goes through the real service code: `DiagnosisService` / `PrescriptionService` → normalization →
  observation → evidence pack → guidebook selection → synthesis → validator → (repair).
- The real `GoogleGenAIGateway` gets a counting wrapper around `client.aio.models.generate_content`.
  HARD GLOBAL CAP = 8 provider calls across all runs (tracked in `.sprint/live_smoke_result.json`);
  the 9th call raises before any network I/O, tenacity retries included. Aborts on first failure.
- Inputs are fully synthetic (Pillow): one drawn celadon mug; three Korean "릴스 인사이트"
  screenshots (NanumGothic) with internally consistent metrics
  (12,480 views × 6.2 s avg ≈ 21 h 29 m total watch time). Inputs saved to `.sprint/smoke_inputs/`.
- Model overrides: `GEMINI_MODEL_OBSERVE|DIAGNOSIS|PRESCRIPTION` env vars (not needed this run).

## Run 2026-10-18 14:08 KST — result

SDK google-genai 2.23.0, Python 3.12.3. Configured model `gemini-3.8-flash` exists (listed with
generateContent, 1,048,576 in / 65,536 out tokens, thinking=True). `thinking_level` LOW and MEDIUM
accepted (no 400). **Provider calls: 4 / 8** (no retries, no repair needed).

| Workflow | Status | Latency | Calls (prompt_version · thinking · latency · tokens prompt/output/thoughts/total) |
|---|---|---|---|
| diagnosis | success | 29.1 s | visual-observation-v1 · low · 5.5 s · 1499/296/–/1795; diagnosis-v2 · medium · 23.6 s · 6112/2362/739/9213 |
| prescription | success | 46.9 s | insight-observation-v1 · low · 27.2 s · 3695/1018/–/4713; prescription-v2 · medium · 19.7 s · 5114/698/1773/7585 |

Total 23,306 tokens. Cost not estimated (no official pricing for `gemini-3.8-flash` in local docs/SDK).
Validator outcome PASS on first draft for both (no `repair-v1` call).

Knowledge `gb2-5edea367` (pack `sosu-guidebook`):
- diagnosis 27 rules (6,106 chars): GB-HOOK-001/002/004/005, GB-TYPE-003/004/005, GB-COMBO-004/007,
  GB-IDEA-001/004/005, GB-LEN-003, GB-FUND-001/002, GB-LIGHT-002/003, GB-EDIT-001, GB-STORY-001,
  GB-EQUIP-004, GB-CAP-001/002, GB-CTA-007, GB-MUSIC-002, GB-ANGLE-001, GB-BRAND-001, GB-COMP-001
- prescription 24 rules (6,064 chars): GB-PERF-001..005/007, GB-CTA-001/002/005/006, GB-CAP-002,
  GB-COMBO-003/004, GB-HOOK-001/002/004/005, GB-LEN-001/003, GB-BRAND-001, GB-EDIT-001,
  GB-FUND-001, GB-IDEA-001, GB-MUSIC-004

Full public JSON + raw model outputs: `.sprint/live_smoke_result.json` (gitignored).

## Evaluation (honest)

**Diagnosis — good.**
- Schema valid (public `diagnosis.v1`), all sections filled, Korean natural and specific.
- Faithful to the survey: brand/material/target/motifs (물결, 새벽 하늘)/avoidance (공장 느낌) and
  must-show scene (가마에서 꺼낸 머그를 손으로 돌리기) all reflected; uses it as hook and priority #1.
- Disclosure `face_only` (face yes, voice no) respected: every format is voice-free (자막, 현장음, BGM).
- Visual observation was honest: it identified the image as a 2D graphic and the synthesis said
  real glaze texture "검증하기 어렵다" → uncertainty preserved, not hallucinated as a photo.
- Guidebook influence clearly visible: 0–3 s hook with completed product first (HOOK), 완성→재료→과정→완성
  structure (TYPE/COMBO), 2–3 s cuts (EDIT), 45° side light + macro (LIGHT/ANGLE), caption first line
  curiosity sentence + hashtags last (CAP), CTA to profile link (CTA), sustainable cadence (FUND).
- No guaranteed results. Minor: "가마 출납" is slightly unnatural wording; "주 1~2회" cadence is a
  reasonable suggestion, not survey-sourced.

**Prescription — numerically excellent, content partially ungrounded.**
- Observation transcribed all 18 metric rows exactly (labels + values), no unreadable regions,
  correctly linked the 3 shots by handle/date.
- Every number in the prescription matches the screenshots (78%, 52%, 41%, 6.2초/15초, 12,480, 9,830,
  214→23, 댓글 18, 저장 96). No invented metrics or derived ratios.
- Correlation language held ("약했을 가능성이 있습니다", "효과적일 것으로 보입니다"); no guarantees.
- Guidebook influence visible: PERF reading (non-follower reach vs. 3 s drop), HOOK (첫 3초 완성작 +
  궁금증 카피), EDIT (2–3 s cuts), CTA-question at caption end, profile/BRAND one-liner.
- **Issue:** examples assume content details never observed — "도자기에 연기를 입히는 비밀 과정"
  (almost certainly derived from the synthetic handle `@sosu_smoke_ceramics`), "화병", "흙 반죽부터
  다듬기", "다음 판매 일정". The reel URL content is not observed; these are framed as examples but
  read like facts about the video. Recommend tightening `prescription-v2` (examples must be generic
  or explicitly marked 예시, no product/process nouns unless visible in screenshots) and/or a
  validator check. Not a blocker for activation, but worth fixing before public release.
- Unused signals (좋아요 412, 공유 37, 다시 본 비율 12%) — acceptable omission.

**Latency risk:** insight observation took 27.2 s against `gemini_timeout_observe` = 45 s (~60 %
of budget) on clean synthetic screenshots; real, denser screenshots may hit `MODEL_TIMEOUT`.
Consider raising the observe timeout (config owned by Agent C) — finding only.

Verdict: both workflows work end-to-end on live Gemini within ~30–47 s (well under the 180 s
deadline). Diagnosis quality is release-grade; prescription is accurate on numbers but needs a
grounding guard for content examples.
