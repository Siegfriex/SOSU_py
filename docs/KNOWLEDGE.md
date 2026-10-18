# Guidebook knowledge in synthesis prompts

- Source: `knowledge/guidebook/knowledgepack.v1.json` (KnowledgePack schema 1.0, built offline
  from the guidebook PDF; the service never parses the PDF). Override with `SOSU_KNOWLEDGE_PATH`.
- Loading: `app.knowledge.provider.get_knowledge_provider()` — loaded and validated once per process
  (`lru_cache`). Restart the process to pick up a new pack.
- Failure policy: missing file, invalid JSON or schema mismatch → `WARNING` log,
  `knowledge_version = "none"`, zero rules. Requests still succeed; the prompt carries an explicit
  `## GUIDEBOOK KNOWLEDGE (version none)` block telling the model not to cite the guidebook.
- Selection (deterministic): rules whose `applicability` contains the task; rules carrying `q18_*`
  tags are kept only when they include the request's Q18 answer; otherwise rules tagged as
  face/voice-requiring are dropped when Q18 forbids them (unless tagged as an alternative such as
  `hands_only`). When voice is forbidden, rules tagged `narration`/`tts`/`voiceover` are always
  dropped (hard constraint wins over the guidebook's TTS advice — open product decision). Codes
  shared by several questions match only in `q<N>_<code>` form; q11 answers match `q10_*` tags.
  Individually invalid rules are skipped with a warning (the pack is not rejected). Score = priority + task_mapping category + signal-category boost + tag
  matches (q16 pain points, q17 formats, q18, q6 appeals, process/visual cues; for prescription:
  metric labels/notes such as 저장/공유/시청/도달/팔로워/프로필). Pass 1 covers each mapped
  category once, pass 2 fills by score. Cap: 30 rules and 4800 chars of rule text (block ≈ 6k incl. header/style).
- Rendering: `## GUIDEBOOK KNOWLEDGE (version …; cite rule_id and pages)` … one line per rule with
  `[rule_id] (category; p.N; evidence_type)`, recommended action and cautions, then
  `### EDITORIAL STYLE`, ending with `## END GUIDEBOOK KNOWLEDGE`.
- Wiring: diagnosis synthesis (`app/gemini/prompts/diagnosis.py`, `diagnosis-v2`) and prescription
  synthesis (`prescription.py`, `prescription-v2`). Observation prompts and the repair prompt stay
  knowledge-free (evidence purity). The block is separate from the EvidencePack/insight JSON and
  instructs the model not to present guidebook principles as externally verified platform facts.
- Observability: services log `knowledge_version=… rules=N` per request. Public response models are
  unchanged (knowledge version is not exposed in the API contract).
