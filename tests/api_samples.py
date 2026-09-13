"""Self-contained sample payloads for API tests (no dependency on other agents' helpers)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).resolve().parents[1] / "contracts" / "fixtures"


def _load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def diagnosis_request_dict() -> dict[str, Any]:
    return _load("diagnosis.request.json")


def diagnosis_report_dict() -> dict[str, Any]:
    return _load("diagnosis.success.json")["data"]


def prescription_request_dict() -> dict[str, Any]:
    return _load("prescription.request.json")


def prescription_report_dict() -> dict[str, Any]:
    return _load("prescription.success.json")["data"]


def empty_diagnosis_request_dict() -> dict[str, Any]:
    return {"contract_version": "1.0", "locale": "ko-KR", "answers": {}}


# 1x1 white JPEG (valid image bytes) — enough for tests that only need a real-looking upload.
TINY_JPEG = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb004300080606070605080707070909080a0c140d0c0b0b"
    "0c1912130f141d1a1f1e1d1a1c1c20242e2720222c231c1c2837292c30313434341f27393d38323c2e333432"
    "ffc0000b080001000101011100ffc4001f0000010501010101010100000000000000000102030405060708090a"
    "0bffc400b5100002010303020403050504040000017d01020300041105122131410613516107227114328191a1"
    "082342b1c11552d1f02433627282090a161718191a25262728292a3435363738393a434445464748494a535455"
    "565758595a636465666768696a737475767778797a838485868788898a92939495969798999aa2a3a4a5a6a7a8"
    "a9aab2b3b4b5b6b7b8b9bac2c3c4c5c6c7c8c9cad2d3d4d5d6d7d8d9dae1e2e3e4e5e6e7e8e9eaf1f2f3f4f5f6"
    "f7f8f9faffda0008010100003f00fbd0ffd9"
)
