"""Workflow B: 3 screenshots → InsightObservation → synthesis → validate/repair."""

from __future__ import annotations

import logging

from app.config import Settings, get_settings
from app.contracts.prescription import PrescriptionReportV1, PrescriptionRequestV1
from app.domain.evidence import InsightObservationV1
from app.domain.validator import validate_prescription
from app.gemini.gateway import GeminiGateway, GenerationSpec, ImagePart
from app.gemini.prompts import insight_observation as insight_prompt
from app.gemini.prompts import prescription as prescription_prompt
from app.gemini.prompts import repair as repair_prompt
from app.gemini.schemas import PrescriptionDraftV1, to_public_prescription
from app.images.types import NormalizedImage
from app.services.deadline import with_deadline
from app.services.repair import run_with_repair

log = logging.getLogger("sosu.prescription")

_PRESCRIPTION_CONSTRAINTS = (
    "- 릴스 URL 내용은 관측되지 않았음. 영상 내용을 본 것처럼 쓰지 말 것.\n"
    "- unreadable로 기록된 지표는 추정하지 말 것."
)


class PrescriptionService:
    def __init__(self, gateway: GeminiGateway, *, settings: Settings | None = None) -> None:
        self._gateway = gateway
        self._settings = settings

    @property
    def settings(self) -> Settings:
        if self._settings is None:
            self._settings = get_settings()
        return self._settings

    async def run(
        self,
        request: PrescriptionRequestV1,
        insight_images: list[NormalizedImage],
        *,
        request_id: str,
    ) -> PrescriptionReportV1:
        return await with_deadline(
            self._run(request, insight_images, request_id=request_id),
            seconds=self.settings.sosu_request_deadline_seconds,
            request_id=request_id,
        )

    async def _run(
        self,
        request: PrescriptionRequestV1,
        insight_images: list[NormalizedImage],
        *,
        request_id: str,
    ) -> PrescriptionReportV1:
        observation = await self._observe(
            insight_images, locale=request.locale, request_id=request_id
        )
        draft = await self._synthesize(
            observation,
            instagram_url=request.instagram_url,
            locale=request.locale,
            request_id=request_id,
        )
        final = await run_with_repair(
            gateway=self._gateway,
            spec_repair=self._spec_repair(),
            draft=draft,
            validate=validate_prescription,
            build_repair_prompt=lambda d, errors: repair_prompt.build_repair_prompt(
                draft=d, errors=errors, constraints=_PRESCRIPTION_CONSTRAINTS
            ),
            schema=PrescriptionDraftV1,
            request_id=request_id,
        )
        log.info("prescription request_id=%s done images=%d", request_id, len(insight_images))
        return to_public_prescription(final)

    # ------------------------------------------------------------------ calls

    async def _observe(
        self, images: list[NormalizedImage], *, locale: str, request_id: str
    ) -> InsightObservationV1:
        s = self.settings
        system, user = insight_prompt.build_insight_observation_prompt(locale=locale)
        result = await self._gateway.generate_structured(
            spec=GenerationSpec(
                model=s.gemini_model_observe,
                thinking=s.gemini_thinking_observe,
                max_output_tokens=s.gemini_max_output_observe,
                prompt_version=insight_prompt.PROMPT_VERSION,
                timeout_seconds=s.gemini_timeout_observe,
            ),
            system_instruction=system,
            user_text=user,
            images=[ImagePart(data=i.data, mime_type=i.mime_type) for i in images],
            schema=InsightObservationV1,
        )
        log.info(
            "prescription request_id=%s prompt=%s ok", request_id, insight_prompt.PROMPT_VERSION
        )
        return result.value

    async def _synthesize(
        self,
        observation: InsightObservationV1,
        *,
        instagram_url: str,
        locale: str,
        request_id: str,
    ) -> PrescriptionDraftV1:
        s = self.settings
        system, user = prescription_prompt.build_prescription_prompt(
            observation, instagram_url=instagram_url, locale=locale
        )
        result = await self._gateway.generate_structured(
            spec=GenerationSpec(
                model=s.gemini_model_prescription,
                thinking=s.gemini_thinking_synthesis,
                max_output_tokens=s.gemini_max_output_prescription,
                prompt_version=prescription_prompt.PROMPT_VERSION,
                timeout_seconds=s.gemini_timeout_synthesis,
            ),
            system_instruction=system,
            user_text=user,
            images=[],
            schema=PrescriptionDraftV1,
        )
        log.info(
            "prescription request_id=%s prompt=%s ok",
            request_id,
            prescription_prompt.PROMPT_VERSION,
        )
        return result.value

    def _spec_repair(self) -> GenerationSpec:
        s = self.settings
        return GenerationSpec(
            model=s.gemini_model_prescription,
            thinking=s.gemini_thinking_repair,
            max_output_tokens=s.gemini_max_output_repair,
            prompt_version=repair_prompt.PROMPT_VERSION,
            timeout_seconds=s.gemini_timeout_repair,
        )
