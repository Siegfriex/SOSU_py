#!/usr/bin/env python3
"""Validate SOSU guidebook KnowledgePack (stdlib only; optional contract check via pydantic models).

Usage (from SOSU_py/):  .venv/bin/python knowledge/tools/validate_pack.py [path/to/knowledgepack.v1.json]
Exit 0 = valid. Prints counts per category / evidence type and page coverage.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

KDIR = Path(__file__).resolve().parents[1]
SOSU_PY = KDIR.parent
PACK = Path(sys.argv[1]) if len(sys.argv) > 1 else KDIR / "guidebook" / "knowledgepack.v1.json"
SCHEMA = KDIR / "guidebook" / "knowledgepack.schema.json"

errors: list[str] = []
def err(m: str) -> None: errors.append(m)

schema = json.loads(SCHEMA.read_text())
CATS = schema["$defs"]["category"]["enum"]
CAT_CODE = {"reels_fundamentals": "FUND", "reel_types": "TYPE", "combination": "COMBO", "ideation": "IDEA",
            "storyboard": "STORY", "equipment": "EQUIP", "lighting": "LIGHT", "composition": "COMP",
            "camera_angle": "ANGLE", "editing_pacing": "EDIT", "video_length": "LEN", "music_sound": "MUSIC",
            "hook": "HOOK", "caption": "CAP", "cta": "CTA", "performance_interpretation": "PERF",
            "brand_strategy": "BRAND"}
EVID = {"guidebook_principle", "guidebook_example", "author_experience"}
APPL = {"diagnosis", "prescription"}
TAG_RE = re.compile(r"^[a-z0-9]+(_[a-z0-9]+)*$")
RID_RE = re.compile(r"^GB-([A-Z]+)-(\d{3})$")
REQ = schema["properties"]["rules"]["items"]["required"]

pack = json.loads(PACK.read_text())
for k in schema["required"]:
    if k not in pack: err(f"missing top-level key {k}")
extra = set(pack) - set(schema["properties"])
if extra: err(f"unexpected top-level keys {extra}")
if pack.get("schema_version") != "1.0": err("schema_version must be 1.0")
if pack.get("pack_id") != "sosu-guidebook": err("pack_id")
src = pack.get("source", {})
NPAGES = src.get("pages", 45)
if not re.fullmatch(r"[0-9a-f]{64}", src.get("sha256", "")): err("source.sha256")
if pack.get("version") != f"gb2-{src.get('sha256', '')[:8]}": err("version must be gb2-<sha8>")
st = pack.get("style", {})
for k in ("voice", "do", "dont", "example_phrases"):
    if not isinstance(st.get(k), list) or not st.get(k): err(f"style.{k} empty/missing")
for ph in st.get("example_phrases", []):
    if len(ph) > 15: err(f"example_phrase >15 chars: {ph}")

ids = Counter()
cat_count, ev_count, prio_count, appl_count = Counter(), Counter(), Counter(), Counter()
page_rules: dict[int, list[str]] = {p: [] for p in range(1, NPAGES + 1)}
for i, r in enumerate(pack.get("rules", [])):
    rid = r.get("rule_id", f"<#{i}>")
    for k in REQ:
        if k not in r: err(f"{rid}: missing {k}")
    if set(r) - set(REQ): err(f"{rid}: unexpected keys {set(r) - set(REQ)}")
    ids[rid] += 1
    m = RID_RE.match(rid)
    cat = r.get("category")
    if cat not in CATS: err(f"{rid}: bad category {cat}")
    elif not m or m.group(1) != CAT_CODE[cat]: err(f"{rid}: id prefix does not match category {cat}")
    pages = r.get("source_pages") or []
    if not pages: err(f"{rid}: no source_pages")
    for p in pages:
        if not isinstance(p, int) or not 1 <= p <= NPAGES: err(f"{rid}: page out of range {p}")
        else: page_rules[p].append(rid)
    ap = r.get("applicability") or []
    if not ap or not set(ap) <= APPL: err(f"{rid}: bad applicability {ap}")
    for k in ("principle", "recommended_action"):
        v = r.get(k)
        if not isinstance(v, str) or not v.strip(): err(f"{rid}: {k} empty")
        elif len(v) > 200: err(f"{rid}: {k} >200 chars ({len(v)})")
    if not isinstance(r.get("source_section"), str) or not r["source_section"]: err(f"{rid}: source_section")
    c = r.get("exceptions_or_cautions")
    if c is not None and not isinstance(c, str): err(f"{rid}: exceptions_or_cautions type")
    if r.get("evidence_type") not in EVID: err(f"{rid}: evidence_type")
    if r.get("evidence_type") == "author_experience" and not c: err(f"{rid}: author_experience needs caution")
    for t in r.get("tags", []):
        if not TAG_RE.match(t): err(f"{rid}: bad tag {t!r}")
    if r.get("priority") not in (1, 2, 3): err(f"{rid}: priority")
    cat_count[cat] += 1; ev_count[r.get("evidence_type")] += 1; prio_count[r.get("priority")] += 1
    for a in ap: appl_count[a] += 1
for rid, n in ids.items():
    if n > 1: err(f"duplicate rule_id {rid}")
for c in CATS:
    if not cat_count[c]: err(f"category without rules: {c}")

# survey-code tags (q<N>_<code>) must exist in backend survey enums
Q_ENUMS = {}
try:
    sys.path.insert(0, str(SOSU_PY))
    from app.contracts import enums as _en  # type: ignore
    Q_ENUMS = {"q6": _en.ProductAppeal, "q9": _en.PurchaseMotive, "q10": _en.DesiredEmotion,
               "q11": _en.BrandAttribute, "q16": _en.InstagramPainPoint, "q17": _en.CurrentReelFormat,
               "q18": _en.CreatorDisclosure}
    Q_ENUMS = {k: {m.value for m in e} for k, e in Q_ENUMS.items()}
except ImportError:
    pass
survey_tags = Counter()
if Q_ENUMS:
    for r in pack.get("rules", []):
        for t in r.get("tags", []):
            m = re.match(r"^(q\d+)_(.+)$", t)
            if m:
                qn, code = m.groups()
                if qn not in Q_ENUMS: err(f"{r['rule_id']}: tag {t} references unknown question {qn}")
                elif code not in Q_ENUMS[qn]: err(f"{r['rule_id']}: tag {t}: {code!r} not in {qn} enum")
                else: survey_tags[qn] += 1

tm = pack.get("task_mapping", {})
for task in ("diagnosis", "prescription"):
    if task not in tm: err(f"task_mapping.{task} missing"); continue
    for sec, cats in tm[task].items():
        for c in cats:
            if c not in CATS: err(f"task_mapping.{task}.{sec}: bad category {c}")
# optional: cross-check report section keys against backend pydantic contracts
try:
    sys.path.insert(0, str(SOSU_PY))
    from app.contracts.diagnosis import DiagnosisReportV1  # type: ignore
    from app.contracts.prescription import PrescriptionReportV1  # type: ignore
    for task, model in (("diagnosis", DiagnosisReportV1), ("prescription", PrescriptionReportV1)):
        fields = set(model.model_fields) - {"schema_version"}
        keys = set(tm.get(task, {}))
        if keys - fields: err(f"task_mapping.{task} keys not in {model.__name__}: {keys - fields}")
        if fields - keys: err(f"task_mapping.{task} missing report fields: {fields - keys}")
    contract_check = "OK (keys == report model fields)"
except ImportError as e:
    contract_check = f"SKIPPED ({e})"

print(f"pack {pack.get('pack_id')} {pack.get('version')}  rules={sum(ids.values())}")
print("by category:"); [print(f"  {c:28s} {cat_count[c]}") for c in CATS]
print("by evidence_type:", dict(ev_count))
print("by priority:", dict(sorted(prio_count.items())), " applicability:", dict(appl_count))
covered = [p for p, v in page_rules.items() if v]
print(f"pages with >=1 rule: {len(covered)}/{NPAGES}")
print("uncovered pages:", [p for p, v in page_rules.items() if not v])
print("task_mapping contract check:", contract_check)
print("survey-code tags per question (validated vs app/contracts/enums.py):",
      dict(sorted(survey_tags.items())) if Q_ENUMS else "SKIPPED (enums not importable)")
if errors:
    print(f"\nINVALID: {len(errors)} error(s)"); [print("  -", e) for e in errors]; sys.exit(1)
print("\nVALID")
