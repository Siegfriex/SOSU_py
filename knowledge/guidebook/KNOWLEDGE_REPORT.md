# SOSU Guidebook Knowledge Report (draft → root `SOSU_GUIDEBOOK_KNOWLEDGE_REPORT.md`)

## 1. Version / source
- Pack: `pack_id=sosu-guidebook`, `version=gb2-5edea367`, `schema_version=1.0`
- Source: `가이드북 2차.pdf` — 45 pages, sha256 `5edea367d6d782d43b2fd4ad9c3eee491b44983a3fdf91cca21479071be6cb81`
- The PDF is the owner's proprietary asset. It is **not** copied into the repo, and neither is its raw text. Only the hash, per-page character counts (`knowledge/tools/page_chars.json`) and paraphrased rules are stored.
- READY marker: `knowledge/guidebook/READY` was written at `2026-10-18T13:38:49+09:00` with 90 rules. Three rules were appended after that point (GB-COMP-003, GB-CTA-009, GB-CTA-010), so the current total is **93**. IDs are frozen and append-only: no ID was renumbered or deleted, and GB-BRAND-003 kept its ID when its content was corrected.

## 2. Extraction method & coverage
1. `knowledge/tools/extract_text.sh <pdf> <scratch_dir> [pages…]` does the following:
   - verifies the sha256
   - runs `pdftotext -layout` per page into the scratch dir
   - writes the non-whitespace character count of each page into `page_chars.json`
   - optionally renders pages with `pdftoppm -r 60` for image review
2. Pages with sparse, garbled or diagram-dependent text were viewed as images: **1, 2, 8, 11, 12, 13, 14, 17, 18, 22, 23, 24, 25, 29, 30, 31, 42, 44** (18 pages). This includes every Reel-type chart (A–F on p11–13, combos on p14), every diagram (lighting, angle, grid, storyboard, deadline guide) and the pages whose text extraction came out garbled (p13 two-column interleave, the bottom block of p17, the hook list on p31, the O/X captions on p42 and p44).
3. Image review found and corrected one error. Text extraction alone suggested the customer-anecdote caption on p44 was the good (O) example; the page image shows it is the bad (X) example. GB-BRAND-003's content was corrected and its ID kept.
4. p1 is the cover (title image: "수공예 브랜드가 커지는 릴스 가이드") and p2 is the spine; both were image-reviewed and contain no rule content. The other no-text or near-zero-text pages are the EP comic interludes (5, 9, 15, 19, 26, 39, 45) and the chapter dividers (6, 10, 16, 20, 27, 40). Their extracted text was read: they are narrative and carry no operational rule. The exception is p45 ("꾸준히 달리기"), which is used in GB-PERF-008. These pages were not image-reviewed.
5. 31 of 45 pages are cited by at least one rule. The 14 uncovered pages are all comic, divider or image pages. Per-page detail is in `coverage.md` / `coverage.json`.
6. Rules were authored by hand in `knowledge/tools/build_pack.py`, which is the single source. Running it regenerates `knowledgepack.v1.json`, `coverage.json` and `coverage.md`.

## 3. Schema
- `knowledgepack.schema.json` (JSON Schema 2020-12) defines exactly these fields:
  - top level: `schema_version`, `pack_id`, `version`, `source`, `style{voice,do,dont,example_phrases}`, `rules[]`, `task_mapping{diagnosis,prescription}`
  - each rule: `rule_id GB-<CAT>-NNN`, `category` (17-value enum), `source_pages` (1-based PDF pages, 1..45), `source_section`, `principle` (≤200 chars), `applicability`, `recommended_action` (≤200 chars), `exceptions_or_cautions`, `evidence_type`, `tags`, `priority`
- Validation: `cd SOSU_py && .venv/bin/python knowledge/tools/validate_pack.py`. It is stdlib-only, plus an optional pydantic import that checks the task_mapping keys against the backend contracts. It checks:
  - required and extra keys
  - unique IDs, and that each ID prefix matches its category
  - enums
  - page range
  - non-empty applicability
  - length limits
  - tag regex
  - that every `author_experience` rule carries a caution
  - that every category has at least one rule
  - that the task_mapping keys equal the report model fields
  - that every `q<N>_<code>` tag exists in the matching survey enum in `app/contracts/enums.py`
- Current result: **VALID**.

## 4. Rule inventory
| category | n | category | n |
|---|---|---|---|
| reels_fundamentals | 5 | editing_pacing | 9 |
| reel_types (A–F + sequence/locale) | 9 | video_length | 3 |
| combination (4 printed combos + framing) | 7 | music_sound | 5 |
| ideation | 5 | hook | 5 |
| storyboard | 2 | caption | 6 |
| equipment | 4 | cta | 10 |
| lighting | 4 | performance_interpretation | 8 |
| composition | 3 | brand_strategy | 6 |
| camera_angle | 2 | **total** | **93** |

- By evidence type: 70 `guidebook_principle`, 18 `guidebook_example`, 5 `author_experience`. The `author_experience` rules cover:
  - the 29만 followers / 1.7천만 views figures
  - the claim that B+D+F is the most common combo in Korea
  - the ≤30s → 80% completion figure
  - the claim that in-app trending music helps the algorithm
  - the domestic vs overseas subtitle-usage observation
- By priority: 49 rules at P1, 33 at P2, 11 at P3.
- Hook and CTA template lists (p31, p43) are summarized as patterns, with at most one slot pattern per rule. They are not reproduced verbatim.
- Survey-code tags: q6 ×37, q9 ×4, q10 ×6, q16 ×54, q17 ×15, q18 ×14. q11 (BrandAttribute) has the same values as q10 in the enums; rules are tagged with the q10 form only, so match q11 answers against `q10_*` tags or the raw code.

### Page provenance summary
| Chapter | Pages |
|---|---|
| 1 릴스의 이해 | p3–4, 7–8 |
| 2 실전 릴스 유형 | p11–14 |
| 3 콘텐츠 기획 | p17–18 |
| 4 촬영 | p21–25 |
| 5 편집 | p28–38 |
| 6 캡션 | p41–44 |
| EP.7 | p45 |

## 5. How diagnosis / prescription should use the pack
The full detail is in `task_mapping.md`. In short:

**Selecting rules.** Filter by `applicability`, then by `task_mapping[task][section]` categories. Rank by tag match and then by priority.

**Matching survey answers.** Tags carry both the raw survey codes (q6, q9, q10, q16, q17, q18) and a q-prefixed form (`q17_process`, `q18_no`). Use the prefixed form for the codes that collide across questions (`process`, `specialness`, `yes`/`no`).

**Diagnosis**
- The reel_types decision runs in this order: first-show (B completed-first vs A transformation) → sound (C/D) → text/narration (E/F) under the q18 disclosure limits.
- The structure section takes HOOK-001, TYPE-003, EDIT-001, STORY-002 and CTA-001/005.

**Prescription**
- Cite only the metrics that are actually observed. Turn the performance_interpretation rules into hypotheses, and phrase next_actions as single-variable experiments.
- Never invent missing metrics, and never treat a screenshot as causal proof. These are operational rules kept in `task_mapping.md` and `style.dont`. They do not come from the guide.

**Style.** Use `style.*` and `style.md`. Never guarantee views, followers or sales, and never cite author figures as platform facts.

## 6. Unresolved ambiguities
These are recorded as printed and not silently resolved. The full list is in `coverage.md`.
1. **p14 combo labels.** Combo 1 and combo 3 are both printed as `B+C+F`. Combo 1's description and combo 2's body ("A+C+E 조합은…") suggest combo 1 may be A+C+E. Agent B should not present combo 1's label as authoritative; GB-COMBO-002 carries a caution saying so.
2. **p25 angle.** The illustration label says 30~43°; the body text says 30~45°. The body value is used.
3. **p33 resolution.** p33 gives 1080x1950, while p29 gives 1080x1920. 1080x1920 is used.
4. **p34 cross-reference.** p34 says "5-2 참고", but the matching content is in 5-3.
5. **p43 header.** The running header reads "편집", but the page belongs to the caption chapter.
6. **Printed page numbers.** On p41–45 the printed numbers (25/28) do not match the PDF pages. All provenance uses PDF page numbers.
7. **p29 typo.** "원주율" is read as 완주율.
8. **Algorithm and completion claims** (p29, p30, p38) are unsupported author claims.
9. **No dedicated insights/metrics chapter** exists in the guide. The performance_interpretation rules are derived interpretations, and their cautions say so.
10. **No font guidance** exists in the guide. The `fonts` section can rely only on text position (p29) and applying a font (p34).
11. **Creator disclosure (q18)** is not addressed directly. GB-BRAND-005 combines type F with TTS as an interpretation.
12. **Deliberate duplicates** exist across chapters: trending music appears on p12, p30, p34 and p38, and hook = caption first line appears on p31 and p41. They are kept as separate rules with their own provenance.
