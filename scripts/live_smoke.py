"""Bounded live Gemini smoke: ONE diagnosis + ONE prescription through the real service code.

Safety:
- HARD GLOBAL CAP on provider calls (default 8) across all runs, tracked in
  .sprint/live_smoke_result.json. The (cap+1)-th call raises before touching the network.
  The cap wraps `client.aio.models.generate_content`, so tenacity retries are counted too.
- Aborts on the first failure; never retries a workflow.
- The API key is read only via app.config.get_settings() and is never printed or written.

Model overrides: set GEMINI_MODEL_OBSERVE / _DIAGNOSIS / _PRESCRIPTION in the environment.

Usage:  cd SOSU_py && .venv/bin/python scripts/live_smoke.py
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.contracts.diagnosis import SurveyDiagnosisRequestV1  # noqa: E402
from app.contracts.prescription import PrescriptionRequestV1  # noqa: E402
from app.domain.errors import SosuError  # noqa: E402
from app.gemini.client import GoogleGenAIGateway  # noqa: E402
from app.gemini.gateway import GenerationSpec, ImagePart, StructuredResult  # noqa: E402
from app.images.normalize import (  # noqa: E402
    normalize_insight_screenshot,
    normalize_product_image,
)
from app.knowledge.provider import (  # noqa: E402
    GuidebookKnowledgeProvider,
    KnowledgeSelection,
    get_knowledge_provider,
)
from app.services.diagnosis_service import DiagnosisService  # noqa: E402
from app.services.prescription_service import PrescriptionService  # noqa: E402
from google import genai  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402
from pydantic import BaseModel  # noqa: E402

GLOBAL_CAP = 8
RESULT_PATH = ROOT / ".sprint" / "live_smoke_result.json"
INSTAGRAM_URL = "https://www.instagram.com/reel/SOSUsmoke01/"

FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
)

# Ground truth printed on the synthetic screenshots (for evaluation).
SCREENSHOT_METRICS: dict[str, list[tuple[str, str]]] = {
    "overview": [
        ("조회수", "12,480"),
        ("도달한 계정", "9,830"),
        ("팔로워 아닌 계정 비율", "78%"),
        ("좋아요", "412"),
        ("댓글", "18"),
        ("공유", "37"),
        ("저장", "96"),
    ],
    "retention": [
        ("평균 시청 시간", "6.2초"),
        ("영상 길이", "15초"),
        ("3초 이탈률", "41%"),
        ("다시 본 비율", "12%"),
        ("총 시청 시간", "21시간 29분"),
    ],
    "audience": [
        ("프로필 방문", "214"),
        ("팔로우", "23"),
        ("유입: 탐색 탭", "52%"),
        ("유입: 릴스 탭", "31%"),
        ("유입: 프로필", "9%"),
        ("유입: 기타", "8%"),
    ],
}


class CapExceeded(RuntimeError):
    pass


# ---------------------------------------------------------------- call accounting


class CallBudget:
    def __init__(self, prior_calls: int, cap: int) -> None:
        self.prior = prior_calls
        self.cap = cap
        self.calls = 0

    def take(self) -> None:
        if self.prior + self.calls + 1 > self.cap:
            raise CapExceeded(
                f"global provider-call cap {self.cap} reached "
                f"(prior={self.prior}, this_run={self.calls})"
            )
        self.calls += 1


class _CountingModels:
    def __init__(self, inner: Any, budget: CallBudget) -> None:
        self._inner = inner
        self._budget = budget

    async def generate_content(self, **kwargs: Any) -> Any:
        self._budget.take()  # raises before any network I/O
        return await self._inner.generate_content(**kwargs)


class _CountingAio:
    def __init__(self, inner: Any, budget: CallBudget) -> None:
        self.models = _CountingModels(inner.models, budget)


class CountingClient:
    """Exposes only `.aio.models.generate_content` — the single path the gateway uses."""

    def __init__(self, real: genai.Client, budget: CallBudget) -> None:
        self.aio = _CountingAio(real.aio, budget)


class RecordingGateway:
    def __init__(self, inner: GoogleGenAIGateway, log: list[dict[str, Any]]) -> None:
        self._inner = inner
        self._log = log

    async def generate_structured[T: BaseModel](
        self,
        *,
        spec: GenerationSpec,
        system_instruction: str,
        user_text: str,
        images: list[ImagePart],
        schema: type[T],
    ) -> StructuredResult[T]:
        entry: dict[str, Any] = {
            "model": spec.model,
            "prompt_version": spec.prompt_version,
            "thinking": spec.thinking,
            "max_output_tokens": spec.max_output_tokens,
            "images": len(images),
            "system_chars": len(system_instruction),
            "user_chars": len(user_text),
        }
        started = time.perf_counter()
        try:
            result = await self._inner.generate_structured(
                spec=spec,
                system_instruction=system_instruction,
                user_text=user_text,
                images=images,
                schema=schema,
            )
        except Exception as exc:
            entry["latency_ms"] = int((time.perf_counter() - started) * 1000)
            entry["error"] = _error_dict(exc)
            self._log.append(entry)
            raise
        entry["latency_ms"] = int((time.perf_counter() - started) * 1000)
        entry["usage"] = {
            "prompt_tokens": result.usage.prompt_tokens,
            "output_tokens": result.usage.output_tokens,
            "thoughts_tokens": result.usage.thoughts_tokens,
            "total_tokens": result.usage.total_tokens,
        }
        entry["raw_output"] = json.loads(result.raw_json) if result.raw_json else None
        self._log.append(entry)
        return result


class RecordingKnowledge(GuidebookKnowledgeProvider):
    """Records which guidebook rules were rendered into each synthesis prompt."""

    selections: list[dict[str, Any]]

    def _record(self, sel: KnowledgeSelection) -> KnowledgeSelection:
        self.selections.append(
            {
                "task": sel.task,
                "knowledge_version": sel.version,
                "pack_id": sel.pack_id,
                "rule_count": len(sel.rules),
                "rule_ids": sel.rule_ids,
                "rendered_chars": len(sel.render()),
            }
        )
        return sel

    def select_for_diagnosis(self, *args: Any, **kwargs: Any) -> KnowledgeSelection:
        return self._record(super().select_for_diagnosis(*args, **kwargs))

    def select_for_prescription(self, *args: Any, **kwargs: Any) -> KnowledgeSelection:
        return self._record(super().select_for_prescription(*args, **kwargs))


def _error_dict(exc: BaseException) -> dict[str, Any]:
    if isinstance(exc, SosuError):
        return {
            "type": "SosuError",
            "code": str(getattr(exc.code, "value", exc.code)),
            "message": str(exc),
            "details": getattr(exc, "details", None),
        }
    return {"type": type(exc).__name__, "message": str(exc)[:300]}


# ---------------------------------------------------------------- synthetic inputs


def _font(size: int) -> tuple[ImageFont.FreeTypeFont | ImageFont.ImageFont, bool]:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size), True
    return ImageFont.load_default(), False


def make_product_image() -> bytes:
    """A simple drawn handmade ceramic mug on a wooden table (shapes only)."""
    img = Image.new("RGB", (1024, 1024), (236, 228, 214))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 700, 1024, 1024], fill=(170, 124, 84))  # table
    for y in range(720, 1024, 38):
        d.line([0, y, 1024, y + 6], fill=(150, 106, 70), width=3)
    d.ellipse([300, 860, 760, 920], fill=(120, 86, 58))  # shadow
    d.rectangle([330, 380, 690, 880], fill=(92, 140, 150))  # mug body (celadon glaze)
    d.ellipse([330, 340, 690, 420], fill=(70, 112, 122))  # rim
    d.ellipse([350, 352, 670, 408], fill=(52, 40, 32))  # coffee
    d.ellipse([330, 840, 690, 920], fill=(92, 140, 150))  # base curve
    d.ellipse([650, 480, 820, 720], outline=(92, 140, 150), width=34)  # handle
    for i, y in enumerate(range(450, 840, 70)):  # uneven hand-applied glaze drips
        d.ellipse([350 + i * 40, y, 400 + i * 40, y + 90], fill=(120, 168, 172))
    d.rectangle([330, 820, 690, 880], fill=(196, 170, 140))  # unglazed foot
    d.ellipse([440, 200, 470, 300], fill=(250, 250, 250))  # steam
    d.ellipse([520, 170, 550, 290], fill=(250, 250, 250))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def make_insight_screenshot(title: str, rows: list[tuple[str, str]]) -> tuple[bytes, bool]:
    w, h = 1080, 1920
    img = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(img)
    title_font, korean = _font(64)
    row_font, _ = _font(54)
    small_font, _ = _font(40)
    d.rectangle([0, 0, w, 180], fill=(250, 250, 250))
    d.text((60, 60), "< 릴스 인사이트" if korean else "< Reel insights", font=title_font, fill=0)
    d.text((60, 230), title, font=title_font, fill=(20, 20, 20))
    d.text(
        (60, 320),
        "@sosu_smoke_ceramics · 2026년 10월 3일 게시" if korean else "@sosu_smoke · Oct 3, 2026",
        font=small_font,
        fill=(120, 120, 120),
    )
    y = 450
    for label, value in rows:
        d.line([60, y - 30, w - 60, y - 30], fill=(230, 230, 230), width=2)
        d.text((60, y), label, font=row_font, fill=(30, 30, 30))
        tw = d.textlength(value, font=row_font)
        d.text((w - 60 - tw, y), value, font=row_font, fill=(0, 0, 0))
        y += 150
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue(), korean


def survey_answers() -> dict[str, Any]:
    return {
        "q1_brand_name": "소수도방",
        "q2_product_category": "손으로 빚는 청자 유약 머그와 작은 그릇",
        "q3_hero_product": "유약이 흘러내린 자국이 하나씩 다른 청록색 머그",
        "q4_materials": "백자토, 청자 유약",
        "q5_material_reason": "유약이 흐르는 모양이 매번 달라서 같은 컵이 하나도 없음",
        "q6_product_appeals": ["design", "detail", "rarity"],
        "q7_differentiation": (
            "물레로 하나씩 성형하고 유약을 손으로 부어 흐름 자국이 모두 다릅니다."
        ),
        "q8_target_customer": "아침 커피 시간을 소중히 여기는 25~35세 직장인",
        "q9_purchase_motives": ["aesthetic", "self_expression"],
        "q10_desired_emotions": ["excitement", "specialness"],
        "q11_brand_attributes": ["warmth", "specialness"],
        "q12_avoidance": "공장에서 찍어낸 것처럼 보이는 느낌",
        "q13_motif": "물결, 새벽 하늘",
        "q14_primary_message": "같은 머그는 세상에 하나뿐이라는 것",
        "q15_interesting_process": "유약을 부을 때 흘러내리는 순간",
        "q16_pain_points": ["low_reach", "ideation"],
        "q17_current_formats": ["finished_product"],
        "q18_disclosure": "face_only",
        "q20_must_show": "가마에서 막 꺼낸 머그를 손으로 돌려보는 장면",
    }


# ---------------------------------------------------------------- run


def _load_prior() -> dict[str, Any]:
    if RESULT_PATH.exists():
        try:
            data = json.loads(RESULT_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except ValueError:
            pass
    return {"runs": [], "total_provider_calls": 0}


async def _workflow(
    name: str, coro_factory: Any, calls: list[dict[str, Any]], knowledge: RecordingKnowledge
) -> dict[str, Any]:
    first_call = len(calls)
    first_sel = len(knowledge.selections)
    started = time.perf_counter()
    out: dict[str, Any] = {"workflow": name}
    try:
        report = await coro_factory()
        out["status"] = "success"
        out["public_output"] = report.model_dump(mode="json")
    except Exception as exc:
        out["status"] = "error"
        out["error"] = _error_dict(exc)
    out["latency_ms"] = int((time.perf_counter() - started) * 1000)
    out["calls"] = calls[first_call:]
    out["knowledge"] = knowledge.selections[first_sel:]
    return out


async def main() -> int:
    settings = get_settings()
    if not settings.gemini_configured:
        print("Gemini key not configured; aborting (no calls made).")
        return 2

    prior = _load_prior()
    budget = CallBudget(int(prior.get("total_provider_calls", 0)), GLOBAL_CAP)
    if budget.prior >= GLOBAL_CAP:
        print(f"Global cap already consumed ({budget.prior}/{GLOBAL_CAP}); aborting.")
        return 3

    real_client = genai.Client(api_key=settings.gemini_api_key.get_secret_value())
    gateway = GoogleGenAIGateway(
        settings, client=cast(genai.Client, CountingClient(real_client, budget))
    )
    calls: list[dict[str, Any]] = []
    rec_gateway = RecordingGateway(gateway, calls)

    base = get_knowledge_provider()
    knowledge = RecordingKnowledge(
        pack=base.pack,
        source_path=base.source_path,
        max_rules=base.max_rules,
        max_chars=base.max_chars,
    )
    knowledge.selections = []

    product = normalize_product_image(make_product_image())
    shots: list[bytes] = []
    korean_font = False
    for title, key in (
        ("개요", "overview"),
        ("시청 유지", "retention"),
        ("유입 및 활동", "audience"),
    ):
        raw, korean_font = make_insight_screenshot(title, SCREENSHOT_METRICS[key])
        shots.append(raw)
    sprint = ROOT / ".sprint" / "smoke_inputs"
    sprint.mkdir(parents=True, exist_ok=True)
    (sprint / "product.png").write_bytes(make_product_image())
    for i, raw in enumerate(shots, 1):
        (sprint / f"insight_{i}.png").write_bytes(raw)
    insight_images = [normalize_insight_screenshot(b) for b in shots]

    diag_req = SurveyDiagnosisRequestV1.model_validate(
        {"contract_version": "1.0", "locale": "ko-KR", "answers": survey_answers()}
    )
    presc_req = PrescriptionRequestV1.model_validate(
        {"contract_version": "1.0", "locale": "ko-KR", "instagram_url": INSTAGRAM_URL}
    )

    diag_svc = DiagnosisService(rec_gateway, settings=settings, knowledge=knowledge)
    presc_svc = PrescriptionService(rec_gateway, settings=settings, knowledge=knowledge)

    run: dict[str, Any] = {
        "started_at": datetime.now().astimezone().isoformat(),
        "models": {
            "observe": settings.gemini_model_observe,
            "diagnosis": settings.gemini_model_diagnosis,
            "prescription": settings.gemini_model_prescription,
        },
        "thinking": {
            "observe": settings.gemini_thinking_observe,
            "synthesis": settings.gemini_thinking_synthesis,
            "repair": settings.gemini_thinking_repair,
        },
        "cap": GLOBAL_CAP,
        "prior_calls": budget.prior,
        "korean_font_used": korean_font,
        "synthetic_inputs": {
            "survey_answers": survey_answers(),
            "product_image": "drawn celadon ceramic mug (Pillow shapes), 1024x1024",
            "instagram_url": INSTAGRAM_URL,
            "screenshot_metrics": SCREENSHOT_METRICS,
        },
        "workflows": [],
    }

    # SOSU_SMOKE_ONLY=prescription re-verifies the prescription path alone (same global call cap).
    only = os.getenv("SOSU_SMOKE_ONLY", "").strip()
    run["only"] = only or None
    diag: dict[str, Any] = {"status": "skipped"}
    if only != "prescription":
        diag = await _workflow(
            "diagnosis",
            lambda: diag_svc.run(diag_req, product, request_id="smoke-diag-1"),
            calls,
            knowledge,
        )
        run["workflows"].append(diag)
        print(f"diagnosis: {diag['status']} {diag['latency_ms']}ms calls={len(diag['calls'])}")
    if diag["status"] in ("success", "skipped"):
        presc = await _workflow(
            "prescription",
            lambda: presc_svc.run(presc_req, insight_images, request_id="smoke-presc-1"),
            calls,
            knowledge,
        )
        run["workflows"].append(presc)
        print(
            f"prescription: {presc['status']} {presc['latency_ms']}ms calls={len(presc['calls'])}"
        )
    else:
        print("diagnosis failed -> aborting before prescription:", diag.get("error"))

    run["provider_calls_this_run"] = budget.calls
    prior["runs"].append(run)
    prior["total_provider_calls"] = budget.prior + budget.calls
    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.write_text(json.dumps(prior, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"provider calls this run={budget.calls} total={prior['total_provider_calls']}")
    expected = 1 if only == "prescription" else 2
    statuses = [w["status"] for w in run["workflows"]]
    ok = all(st == "success" for st in statuses) and len(statuses) == expected
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
