"""Guidebook KnowledgePack provider: loading, deterministic selection, prompt wiring."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from app.config import Settings
from app.contracts.diagnosis import SurveyAnswersV1, SurveyDiagnosisRequestV1
from app.contracts.prescription import PrescriptionRequestV1
from app.domain.normalizer import normalize_survey
from app.gemini.schemas import DiagnosisDraftV1, PrescriptionDraftV1
from app.knowledge.provider import (
    DEFAULT_KNOWLEDGE_PATH,
    NO_KNOWLEDGE_VERSION,
    GuidebookKnowledgeProvider,
    get_knowledge_provider,
)
from app.services.diagnosis_service import DiagnosisService
from app.services.prescription_service import PrescriptionService

from tests import helpers
from tests.fakes import (
    FakeGateway,
    fake_image,
    sample_diagnosis_draft,
    sample_insight,
    sample_prescription_draft,
    sample_visual,
)


def _rule(rule_id: str, category: str, *, tags: list[str], priority: int = 2, app: Any = None):
    return {
        "rule_id": rule_id,
        "category": category,
        "source_pages": [3, 4],
        "source_section": "1-1",
        "principle": f"{rule_id} 원칙 문장",
        "applicability": app or ["diagnosis", "prescription"],
        "recommended_action": f"{rule_id} 권장 행동",
        "exceptions_or_cautions": None,
        "evidence_type": "guidebook_principle",
        "tags": tags,
        "priority": priority,
    }


def tiny_pack() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "pack_id": "sosu-guidebook",
        "version": "gb2-deadbeef",
        "source": {"filename": "guide.pdf", "sha256": "deadbeef" * 8, "pages": 50},
        "style": {
            "voice": ["다정하고 구체적인 선배 작가의 말투"],
            "do": ["한 문장에 한 행동"],
            "dont": ["과장된 보장 표현"],
            "example_phrases": ["오늘은 손만 찍어보세요"],
        },
        "rules": [
            _rule("GB-HOOK-001", "hook", tags=["hook", "low_reach", "q16_low_reach"], priority=1),
            _rule("GB-TYPE-001", "reel_types", tags=["q18_yes", "talking_head"], priority=1),
            _rule("GB-TYPE-002", "reel_types", tags=["q18_no", "hands_only"], priority=1),
            _rule("GB-TYPE-003", "reel_types", tags=["q17_finished_product", "process"]),
            _rule("GB-TYPE-004", "reel_types", tags=["q17_vlog", "vlog"]),
            _rule("GB-CAP-001", "caption", tags=["caption"], priority=3),
            _rule(
                "GB-PERF-001",
                "performance_interpretation",
                tags=["saves", "retention"],
                app=["prescription"],
            ),
            _rule("GB-CTA-001", "cta", tags=["cta", "saves"], app=["prescription"]),
        ],
        "task_mapping": {
            "diagnosis": {"reel_types": ["reel_types"], "structure": ["hook", "caption"]},
            "prescription": {"next_actions": ["performance_interpretation", "cta"]},
        },
    }


@pytest.fixture
def pack_path(tmp_path: Path) -> Path:
    p = tmp_path / "knowledgepack.v1.json"
    p.write_text(json.dumps(tiny_pack(), ensure_ascii=False), encoding="utf-8")
    return p


@pytest.fixture
def provider(pack_path: Path) -> GuidebookKnowledgeProvider:
    return GuidebookKnowledgeProvider.from_path(pack_path)


def _declared(**overrides: Any):
    answers = helpers.sample_answers_dict()
    answers.update(overrides)
    return normalize_survey(SurveyAnswersV1.model_validate(answers))


def test_loads_and_reports_version(provider: GuidebookKnowledgeProvider) -> None:
    assert provider.available and provider.version == "gb2-deadbeef"


def test_selection_is_deterministic(provider: GuidebookKnowledgeProvider) -> None:
    a = provider.select_for_diagnosis(_declared(), sample_visual()).rule_ids
    b = provider.select_for_diagnosis(_declared(), sample_visual()).rule_ids
    assert a == b and a
    assert "GB-PERF-001" not in a  # prescription-only rule


def test_q18_changes_selection(provider: GuidebookKnowledgeProvider) -> None:
    no = provider.select_for_diagnosis(_declared(q18_disclosure="no")).rule_ids
    yes = provider.select_for_diagnosis(_declared(q18_disclosure="yes")).rule_ids
    assert "GB-TYPE-002" in no and "GB-TYPE-001" not in no
    assert "GB-TYPE-001" in yes and "GB-TYPE-002" not in yes


def test_q17_changes_ranking(pack_path: Path) -> None:
    p = GuidebookKnowledgeProvider.from_path(pack_path)
    p.max_rules = 3
    fin = p.select_for_diagnosis(_declared(q17_current_formats=["finished_product"])).rule_ids
    vlog = p.select_for_diagnosis(_declared(q17_current_formats=["vlog"])).rule_ids
    assert fin != vlog
    assert "GB-TYPE-003" in fin and "GB-TYPE-004" in vlog


def test_prescription_selection_and_render(provider: GuidebookKnowledgeProvider) -> None:
    sel = provider.select_for_prescription(sample_insight())
    assert sel.rule_ids[0] in {"GB-PERF-001", "GB-CTA-001"}
    block = sel.render()
    assert "## GUIDEBOOK KNOWLEDGE (version gb2-deadbeef" in block
    assert "[GB-PERF-001]" in block and "p.3, p.4" in block
    assert "EDITORIAL STYLE" in block and "## END GUIDEBOOK KNOWLEDGE" in block


def test_bounded(pack_path: Path) -> None:
    data = tiny_pack()
    data["rules"] = [
        _rule(f"GB-HOOK-{i:03d}", "hook", tags=["hook"], priority=1 + i % 3) for i in range(200)
    ]
    pack_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    sel = GuidebookKnowledgeProvider.from_path(pack_path).select_for_diagnosis(_declared())
    assert 0 < len(sel.rules) <= 30


@pytest.mark.parametrize("content", [None, "{not json", json.dumps({"schema_version": "9"})])
def test_missing_or_invalid_pack_is_graceful(tmp_path: Path, content: str | None) -> None:
    path = tmp_path / "pack.json"
    if content is not None:
        path.write_text(content, encoding="utf-8")
    p = GuidebookKnowledgeProvider.from_path(path)
    assert p.version == NO_KNOWLEDGE_VERSION and not p.available
    sel = p.select_for_diagnosis(_declared())
    assert sel.rules == () and "version none" in sel.render()


def test_settings_path_default() -> None:
    assert DEFAULT_KNOWLEDGE_PATH.name == "knowledgepack.v1.json"
    assert get_knowledge_provider() is get_knowledge_provider()


# ------------------------------------------------------------------ service prompt wiring


def _settings() -> Settings:
    return Settings(gemini_api_key="x")  # type: ignore[arg-type]


async def _run_diagnosis(provider: GuidebookKnowledgeProvider, **answers: Any) -> FakeGateway:
    gw = FakeGateway([sample_visual(), sample_diagnosis_draft()])
    req_dict = helpers.sample_diagnosis_request_dict()
    req_dict["answers"].update(answers)
    svc = DiagnosisService(gw, settings=_settings(), knowledge=provider)
    await svc.run(SurveyDiagnosisRequestV1.model_validate(req_dict), fake_image(), request_id="t")
    return gw


async def _run_prescription(provider: GuidebookKnowledgeProvider) -> FakeGateway:
    gw = FakeGateway([sample_insight(), sample_prescription_draft()])
    svc = PrescriptionService(gw, settings=_settings(), knowledge=provider)
    req = PrescriptionRequestV1.model_validate(helpers.sample_prescription_request_dict())
    await svc.run(req, [fake_image(i) for i in range(3)], request_id="t")
    return gw


async def test_diagnosis_prompt_contains_knowledge(provider: GuidebookKnowledgeProvider) -> None:
    gw = await _run_diagnosis(provider)
    observe, synth = gw.calls
    assert "GUIDEBOOK" not in observe.text  # observation stays knowledge-free
    assert synth.schema is DiagnosisDraftV1
    assert "## GUIDEBOOK KNOWLEDGE (version gb2-deadbeef" in synth.user_text
    assert "[GB-HOOK-001]" in synth.user_text
    # knowledge block is separate from (after) the evidence pack sections
    assert synth.user_text.index("# DECLARED EVIDENCE") < synth.user_text.index(
        "## GUIDEBOOK KNOWLEDGE"
    )
    assert "외부 검증 사실" in synth.user_text


async def test_diagnosis_prompt_changes_with_q18(provider: GuidebookKnowledgeProvider) -> None:
    no = (await _run_diagnosis(provider, q18_disclosure="no")).calls[-1].user_text
    yes = (await _run_diagnosis(provider, q18_disclosure="yes")).calls[-1].user_text
    assert "[GB-TYPE-002]" in no and "[GB-TYPE-001]" not in no
    assert "[GB-TYPE-001]" in yes and "[GB-TYPE-002]" not in yes


async def test_prescription_prompt_contains_knowledge_and_research(
    provider: GuidebookKnowledgeProvider,
) -> None:
    gw = await _run_prescription(provider)
    observe, synth = gw.calls
    assert "GUIDEBOOK" not in observe.text
    assert synth.schema is PrescriptionDraftV1
    assert "## GUIDEBOOK KNOWLEDGE (version gb2-deadbeef" in synth.user_text
    assert "[GB-PERF-001]" in synth.user_text
    assert "## EXTERNAL RESEARCH (status: none available)" in synth.user_text


async def test_missing_pack_services_still_work(tmp_path: Path) -> None:
    p = GuidebookKnowledgeProvider.from_path(tmp_path / "missing.json")
    d = await _run_diagnosis(p)
    assert "GUIDEBOOK KNOWLEDGE (version none)" in d.calls[-1].user_text
    r = await _run_prescription(p)
    assert "GUIDEBOOK KNOWLEDGE (version none)" in r.calls[-1].user_text


# ------------------------------------------------------------------ real pack (Agent C)

REAL_PACK = DEFAULT_KNOWLEDGE_PATH
needs_real_pack = pytest.mark.skipif(not REAL_PACK.is_file(), reason="real KnowledgePack absent")


@needs_real_pack
async def test_real_pack_wired_into_both_services() -> None:
    version = json.loads(REAL_PACK.read_text(encoding="utf-8"))["version"]
    provider = GuidebookKnowledgeProvider.from_path(REAL_PACK)
    assert provider.available and provider.version == version
    d = (await _run_diagnosis(provider)).calls[-1].user_text
    r = (await _run_prescription(provider)).calls[-1].user_text
    for text in (d, r):
        assert f"## GUIDEBOOK KNOWLEDGE (version {version}" in text
        assert "[GB-" in text
    dsel = provider.select_for_diagnosis(_declared())
    assert 0 < len(dsel.rules) <= 30
    assert all("diagnosis" in rule.applicability for rule in dsel.rules)
    psel = provider.select_for_prescription(sample_insight())
    assert any(rule.category == "performance_interpretation" for rule in psel.rules)


@needs_real_pack
def test_real_pack_q18_changes_selection() -> None:
    provider = GuidebookKnowledgeProvider.from_path(REAL_PACK)
    no = provider.select_for_diagnosis(_declared(q18_disclosure="no")).rule_ids
    yes = provider.select_for_diagnosis(_declared(q18_disclosure="yes")).rule_ids
    assert no != yes
