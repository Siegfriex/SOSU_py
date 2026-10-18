# External research boundary

Status (Phase 1): **boundary only — no live search.**

- `app/research/models.py`: `ResearchQuery`, `ResearchFinding` (query, source_title, source_url,
  published_or_retrieved_date, finding, applicability, confidence), `ResearchResult`
  (status `ok | unavailable | error`, provider, findings, reason).
- `app/research/provider.py`: `ResearchProvider` Protocol (`async research(queries) -> ResearchResult`,
  never raises for provider failures), `NullResearchProvider` (default; status `unavailable`, never
  fabricates), `FixtureResearchProvider` (tests), `get_research_provider()` gated by
  `SOSU_RESEARCH_ENABLED` (default `false`; even `true` returns Null until Phase 2 exists).
- Prescription synthesis prompt carries a separate `## EXTERNAL RESEARCH` block. When unavailable
  it says "none available" and forbids citing trends/statistics/external sources. It is distinct from
  `OBSERVED INSIGHTS` and `GUIDEBOOK KNOWLEDGE`. Diagnosis is not wired (no current need).

## SDK capability found

`.venv` has `google-genai 2.23.0`. `google.genai.types` exposes:

- `Tool(google_search=GoogleSearch(...))` — Gemini grounding with Google Search
  (`GoogleSearch` fields: `search_types, blocking_confidence, exclude_domains, time_range_filter`).
  Also `url_context`, `google_search_retrieval`, `enterprise_web_search`.
- Response `candidates[0].grounding_metadata: GroundingMetadata` with `web_search_queries`,
  `grounding_chunks[].web (uri, title, domain)`, `grounding_supports`, `search_entry_point`.

`app/gemini/client.py` currently sets `response_mime_type="application/json"` +
`response_json_schema` and no `tools`.

## Phase 2 requirements

1. Separate gateway call (e.g. `GoogleGenAIGateway.research(...)`) with
   `tools=[Tool(google_search=GoogleSearch())]`; do not mix grounding into the structured-output
   synthesis call (keep evidence purity and schema guarantees). Verify whether the target model
   allows tools together with `response_json_schema`; if not, parse free text into
   `ResearchFinding` from `grounding_metadata` only.
2. Build `ResearchFinding.source_url/title` exclusively from `grounding_chunks[].web` — never from
   model prose. Drop findings without a grounding chunk. Record retrieval date.
3. Own timeout budget inside `SOSU_REQUEST_DEADLINE_SECONDS`; failures → status `error`, request
   continues with "none available".
4. Display requirements for Google Search grounding (search entry point / attribution) must be
   checked before exposing sources to end users; public contract change required to surface them.
5. Live tests behind `RUN_LIVE_GEMINI_TESTS`.
