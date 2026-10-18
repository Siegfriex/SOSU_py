# RD-5: prescription grounding (Phase 3)

Problem: on 2026-10-18 the live prescription run (see `docs/LIVE_SMOKE.md`) got every number right,
but its next actions and tone described video content that nobody had observed: "도자기 완성품",
"'도자기에 연기를 입히는 비밀 과정'과 같은 궁금증형 카피", "흙 반죽부터 다듬기까지",
"작업실에서 방금 나온 화병", "다음 판매 일정" and "도자기 제작 과정" (tone).

## Root cause (evidence-based)

1. **The handle was the only content cue, and it reached synthesis as "fact".** The insight
   observation call recorded the screen text verbatim in `qualitative_notes`
   ("하위 텍스트 '@sosu_smoke_ceramics · 2026년 10월 3일 게시'") and in `cross_image_signals`.
   `build_prescription_prompt` sent that JSON unchanged, under a system prompt that calls
   OBSERVED INSIGHTS the *only* source of facts.
2. **The model translated the handle.** smoke→연기 and ceramics→도자기 produce exactly
   "도자기에 연기를 입히는". 화병, 흙 반죽 and 판매 일정 follow from that as pottery associations.
   The URL shortcode `SOSUsmoke01` also contains "smoke".
3. **The prompt asked for concreteness without saying where it may come from.** Rule 4 said
   "일반론이 아니라 … 구체적 처방" and rule 5 said "이번 주에 실행 가능한 수준으로 구체적".
   Rule 1 forbade treating the *URL's* content as seen, but said nothing about the handle or
   about putting product nouns into example copy. The prescription workflow has no survey, so
   the model had no real product to be concrete about and invented one. The guidebook
   techniques (HOOK: completed product first; EDIT: 2–3 s cuts) supplied the sentence frames,
   and the handle supplied the nouns.
4. **No validator check.** `validate_prescription` checked only structure: order, empty
   values and placeholders.

The offending text was framed as examples ("~와 같은", "~처럼"), not as "이 영상에서 …". A check
that only looked for attribution patterns would therefore have missed the live output.

## Changes

| File | Change |
|---|---|
| `app/gemini/prompts/prescription.py` | New **EVIDENCE BOUNDARY** section. Allowed: observed metrics, simple derived calculations, screen text cited as "스크린샷에 보이는 '…' 문구", guidebook techniques, and next-video ideas marked "다음 영상에서 시도해 볼 수 있는 예: …". Forbidden: inferring content from the handle or URL slug; describing unseen scenes, products, materials, processes or editing as facts; putting unobserved product or schedule details into example copy; claiming the URL was visited or the video watched; stating correlation as causation. Rules 1, 4 and 5 now say that concreteness comes from metrics and methods, not from invented products. Before the observation JSON is sent, `@handles` are redacted to `@[계정명]`. |
| `app/gemini/prompts/insight_observation.py` | The observation prompt now tells the model to record handles, captions and visible text in `qualitative_notes` as "화면 텍스트(영상 내용 아님): '…'". It must never translate or interpret that text, and never describe scenes, products or processes. (`InsightObservationV1` has no `visible_text` field, and the contract was not changed.) |
| `app/domain/validator.py` | `validate_prescription(draft, *, observation=None, instagram_url=None)` adds grounding checks (below). The existing one-argument call still runs only the structural checks, and the diagnosis logic is untouched. |
| `app/services/prescription_service.py` | The validator closure now receives the observation and the request URL, so the first draft and the repaired draft go through the same checks. `_PRESCRIPTION_CONSTRAINTS`, which is passed to the repair prompt, now spells out the handle/URL rule, the rule against attributing ideas to the analysed video, and the rule against numbers for unreadable metrics. |

### Validator: `check_prescription_grounding` (all issues are REPAIRABLE, never FATAL)

Evidence comes from `build_grounding_evidence(observation, url)`:
- **observed_text**: every observed string (labels, values, notes, unreadable regions, cross
  signals) with `@handles` and URLs **removed**, so a handle cannot whitelist its own nouns.
- **handle_sources**: Latin tokens found by substring search in the handles and in the URL
  shortcode (letters only, lower-cased), matched against `HANDLE_TOKEN_MAP`. For example
  `ceramic` maps to 도자기/도예/세라믹/흙/점토/화병/가마/유약/물레, `smoke` to 연기/훈연/스모크,
  `candle` to 캔들/양초/향초, and there are entries for leather, knit, wood, clay, jewel, vase,
  glass, soap and others. All keys are at least 4 letters long.
- **unreadable_labels**: known metric labels named in `unreadable_regions` that have no
  readable value elsewhere.

The fields checked are summary, diagnosis, next_actions title and description,
`tone.description` and `tone.keywords`.

| Check | Fires when |
|---|---|
| (b) handle/URL-derived noun | A noun mapped from a handle or slug token appears anywhere in the text and does not appear in observed_text. This fires **however the sentence is phrased**, including example copy. The error message names the noun and the identifier it came from. |
| (a) assertion about the analysed Reel | A sentence has a strong attribution ("영상 속", "영상에서 보여준", "보여주신", "촬영하신", "업로드하신", "올리신", …) or a weak one ("이/해당/이번 영상·릴스 + 은/는/에서/의 …") outside a hypothetical sentence ("다음 영상", "예를 들어", "시도해", "해 보세요"), **and** it contains a content noun (product, material, process, schedule) that is not observed. Frame and edit nouns (장면, 컷, 자막, 편집, …) also count unless the sentence is hedged ("가능성", "보입니다", "수 있"). Metric readings like "이 영상의 3초 이탈률 41%" pass. |
| Watch claim | "영상을 확인해 보니", "시청한 결과", "링크를 살펴보니", … |
| Unreadable metric number | A label recorded as unreadable is followed within 14 characters by a digit. The window stops at punctuation, at "읽을 수 없/확인되지", or at another metric label. |

Sentence splitting keeps decimals such as "6.2초" intact. The error text avoids the substring
"placeholder", so these issues can never push a draft over the FATAL threshold. Each message
names the offending noun or sentence and tells the repair model what to do: delete it, replace
it with a generic term such as '완성작' or '작업 과정', or mark it as a next-video example. The
existing single repair call receives these messages together with the expanded constraints.

## Tests: `tests/test_rd5_grounding.py` (29 tests, deterministic, no network)

- **Baseline:** a clean grounded draft passes. The legacy signature stays structural-only. The
  evidence excludes the handle from observed_text and maps ceramic/smoke back to their source.
- **Adversarial (must flag):** "이 영상에서 도자기에 연기를 입히는 과정" with the ceramics handle;
  a process from the handle (`@hana_candle_pour` → 캔들); a handle noun used inside example
  copy; a suggestive URL slug (`SOSUsmoke01` → 연기) when no handle is present; "영상 속 머그를
  돌리는 장면"; "영상을 확인해 보니"; a number stated for an unreadable metric (공유).
- **Must pass:** generic next-video ideas when only aggregate metrics are visible; hedged metric
  readings about "이 영상"; a product genuinely in screen text, cited as "스크린샷에 보이는 '…'
  문구"; "읽을 수 없어 판단에서 제외"; the derived completion calculation (6.2초 ÷ 15초 ≈ 41%,
  plus 총 시청 시간); guidebook techniques (45° 측광, 매크로, 2–3초 컷, 손동작).
- **Live replica:** the four offending sentences, copied verbatim from
  `.sprint/live_smoke_result.json`, are flagged together (next_actions[0..2] and
  tone.description, with nouns 도자기, 연기, 흙, 화병) and individually (3 parametrized cases).
- **False-positive guards (must pass):** "자막이 영상의 흐름을…" (no word boundary at 이),
  "다음 영상 속 첫 장면…", "직접 만드신 작품…" (present-tense honorific), "시청자가 영상을 보면…",
  and an unreadable "도달 출처 그래프" / "시청 시간 그래프" region next to readable
  "도달한 계정 9,830" / "평균 시청 시간 6.2초" (prefix labels are not treated as unreadable).
- **Prompts:** the synthesis system prompt contains the EVIDENCE BOUNDARY, the hypothetical
  phrasing, the handle/URL ban, the watch-claim ban, the causation ban and the screen-text
  citation form. The user prompt contains neither the raw handle nor "ceramics", but does
  contain the `@[계정명]` marker and the metrics verbatim. Neither prompt contains "도자기",
  so the negative example does not prime the noun. The observation prompt contains the
  "화면 텍스트(영상 내용 아님)" label.
- **Pipeline (FakeGateway):** a hallucinating draft followed by a clean repair returns the clean
  draft. The repair prompt carries the grounding errors and the new constraint. A hallucinating
  repair raises `REPAIR_FAILED` after 3 calls. A clean draft makes no repair call.

## Residual risks

- **Lexicon-bound.** The checks catch only the handle tokens in `HANDLE_TOKEN_MAP` and the
  nouns in `CONTENT_NOUNS`/`FRAME_NOUNS`. An invented product that is unrelated to the handle
  (for example 화병 from a handle with no `ceramic`/`vase`) and is phrased as an example is
  stopped only by the prompt. "다음 판매 일정" is stopped only by the prompt as well.
- **Substring matching.** A random shortcode can contain a key (for example "wood" or "glass"),
  and Korean homonyms exist ("연기" also means postponement or acting). The result is a false
  REPAIRABLE, which costs one repair call and, in the worst case, ends in REPAIR_FAILED.
- **Behaviour, not mechanism.** Whether the model follows the new prompt is unverified until a
  live run, and no live call was made in this phase.
- **Prompt version strings unchanged.** `prescription-v2` and `insight-observation-v1` changed
  content under the same version, because `tests/test_pipelines.py` asserts these strings and
  is outside RD-5 ownership. A bump (→ v3/v2) is a two-line test edit for the orchestrator.
- **Handles without "@".** Handles are detected, stripped from observed_text and redacted from
  the synthesis prompt only when they are written as `@name`. If the observation writes a bare
  username, check (b) does not fire for it and the prompt still shows it. The live screenshots
  used "@".
- **Unreadable check.** It recognises only known labels (`COMMON_METRIC_LABELS`) named in the
  unreadable-region text. A free-form description ("하단 수치 가림") cannot be mapped to a
  metric.
