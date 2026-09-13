# ruff: noqa: E501
"""SSOT §5 code spellings must map 1:1 onto CONTRACT V1 codes (translation aid for SSOT readers)."""

from __future__ import annotations

import json
from pathlib import Path

from app.contracts.catalog import (
    CATALOG_ENUM_TYPES,
    SSOT_CODE_ALIASES,
    UI_OPTION_CATALOG,
    catalog_as_json,
)

# Verbatim SSOT §5 vocabularies.
SSOT_CODES: dict[str, set[str]] = {
    "q6": {
        "design",
        "color",
        "detail",
        "texture",
        "material",
        "making_process",
        "story",
        "rarity",
        "other",
    },
    "q9": {
        "aesthetic",
        "special",
        "self_reward",
        "gift",
        "memory",
        "space_styling",
        "unique_ownership",
    },
    "q10": {
        "excitement",
        "happiness",
        "warmth",
        "healing",
        "fun",
        "specialness",
        "being_moved",
        "comfort",
        "other",
    },
    "q11": {
        "excitement",
        "happiness",
        "warmth",
        "healing",
        "fun",
        "specialness",
        "being_moved",
        "comfort",
        "other",
    },
    "q16": {
        "low_views",
        "slow_follower_growth",
        "content_ideation",
        "filming",
        "editing",
        "posting_consistency",
        "low_purchase_conversion",
        "other",
    },
    "q17": {
        "rarely_posts",
        "finished_product",
        "making_process",
        "photo_video_mix",
        "trend_reels",
        "vlog",
    },
    "q18": {"face_and_voice", "neither", "face_only", "voice_only"},
}


def _translate(question: str, ssot_code: str) -> str:
    return SSOT_CODE_ALIASES.get(question, {}).get(ssot_code, ssot_code)


def test_every_ssot_code_translates_to_exactly_one_v1_code() -> None:
    for question, ssot_codes in SSOT_CODES.items():
        enum_type = CATALOG_ENUM_TYPES[question]
        v1_values = {m.value for m in enum_type}
        translated = {_translate(question, c) for c in ssot_codes}
        assert translated == v1_values, (question, translated ^ v1_values)
        assert len(translated) == len(ssot_codes), f"{question}: alias map is not injective"


def test_aliases_only_name_real_ssot_codes() -> None:
    for question, aliases in SSOT_CODE_ALIASES.items():
        assert set(aliases) <= SSOT_CODES[question], question


def test_catalog_json_fixture_matches_runtime() -> None:
    path = Path(__file__).resolve().parents[1] / "contracts" / "fixtures" / "ui_option_catalog.json"
    assert path.exists(), "run: uv run python scripts/make_fixtures.py"
    assert json.loads(path.read_text(encoding="utf-8")) == json.loads(json.dumps(catalog_as_json()))


def test_catalog_json_covers_every_option() -> None:
    data = catalog_as_json()
    questions = data["questions"]
    assert isinstance(questions, dict)
    for q, table in UI_OPTION_CATALOG.items():
        options = questions[q]["options"]
        assert [o["label"] for o in options] == list(table)
        assert [o["code"] for o in options] == [c.value for c in table.values()]
