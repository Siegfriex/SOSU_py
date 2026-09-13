"""Workflow A: request → DeclaredEvidence → (VisualObservation) → synthesis → validate/repair."""

from __future__ import annotations

import logging

from app.config import Settings, get_settings
from app.contracts.diagnosis import DiagnosisReportV1, SurveyDiagnosisRequestV1
from app.domain.evidence import EvidencePackV1, VisualObservationV1
from app.domain.evidence_pack import build_evidence_pack
from app.domain.normalizer import normalize_survey
from app.domain.validator import validate_diagnosis
from app.gemini.gateway import GeminiGateway, GenerationSpec, ImagePart
from app.gemini.prompts import diagnosis as diagnosis_prompt
from app.gemini.prompts import repair as repair_prompt
from app.gemini.prompts import visual_observation as visual_prompt
from app.gemini.prompts._common import constraint_sentences
from app.gemini.schemas import DiagnosisDraftV1, to_public_diagnosis
from app.images.types import NormalizedImage
from app.services.deadline import with_deadline
from app.services.repair import run_with_repair

log = logging.getLogger("sosu.diagnosis")


class DiagnosisService:
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
        request: SurveyDiagnosisRequestV1,
        product_image: NormalizedImage | None,
        *,
        request_id: str,
    ) -> DiagnosisReportV1:
        return await with_deadline(
            self._run(request, product_image, request_id=request_id),
            seconds=self.settings.sosu_request_deadline_seconds,
            request_id=request_id,
        )

    async def _run(
        self,
        request: SurveyDiagnosisRequestV1,
        product_image: NormalizedImage | None,
        *,
        request_id: str,
    ) -> DiagnosisReportV1:
        declared = normalize_survey(request.answers)

        visual: VisualObservationV1 | None = None
        if product_image is not None:
            visual = await self._observe(
                product_image, locale=request.locale, request_id=request_id
            )

        pack = build_evidence_pack(declared, visual, locale=request.locale)
        draft = await self._synthesize(pack, request_id=request_id)

        constraint = declared.creator_constraint
        constraint_text = constraint_sentences(constraint)

        final = await run_with_repair(
            gateway=self._gateway,
            spec_repair=self._spec_repair(),
            draft=draft,
            validate=lambda d: validate_diagnosis(d, constraint),
            build_repair_prompt=lambda d, errors: repair_prompt.build_repair_prompt(
                draft=d, errors=errors, constraints=constraint_text
            ),
            schema=DiagnosisDraftV1,
            request_id=request_id,
        )
        log.info("diagnosis request_id=%s done image=%s", request_id, product_image is not None)
        return to_public_diagnosis(final)

    # ------------------------------------------------------------------ calls

    async def _observe(
        self, image: NormalizedImage, *, locale: str, request_id: str
    ) -> VisualObservationV1:
        s = self.settings
        # Deliberately survey-free: the observation prompt takes no survey argument.
        system, user = visual_prompt.build_visual_observation_prompt(locale=locale)
        result = await self._gateway.generate_structured(
            spec=GenerationSpec(
                model=s.gemini_model_observe,
                thinking=s.gemini_thinking_observe,
                max_output_tokens=s.gemini_max_output_observe,
                prompt_version=visual_prompt.PROMPT_VERSION,
                timeout_seconds=s.gemini_timeout_observe,
            ),
            system_instruction=system,
            user_text=user,
            images=[ImagePart(data=image.data, mime_type=image.mime_type)],
            schema=VisualObservationV1,
        )
        log.info("diagnosis request_id=%s prompt=%s ok", request_id, visual_prompt.PROMPT_VERSION)
        return result.value

    async def _synthesize(self, pack: EvidencePackV1, *, request_id: str) -> DiagnosisDraftV1:
        s = self.settings
        system, user = diagnosis_prompt.build_diagnosis_prompt(pack)
        result = await self._gateway.generate_structured(
            spec=GenerationSpec(
                model=s.gemini_model_diagnosis,
                thinking=s.gemini_thinking_synthesis,
                max_output_tokens=s.gemini_max_output_diagnosis,
                prompt_version=diagnosis_prompt.PROMPT_VERSION,
                timeout_seconds=s.gemini_timeout_synthesis,
            ),
            system_instruction=system,
            user_text=user,
            images=[],
            schema=DiagnosisDraftV1,
        )
        log.info(
            "diagnosis request_id=%s prompt=%s ok", request_id, diagnosis_prompt.PROMPT_VERSION
        )
        return result.value

    def _spec_repair(self) -> GenerationSpec:
        s = self.settings
        return GenerationSpec(
            model=s.gemini_model_diagnosis,
            thinking=s.gemini_thinking_repair,
            max_output_tokens=s.gemini_max_output_repair,
            prompt_version=repair_prompt.PROMPT_VERSION,
            timeout_seconds=s.gemini_timeout_repair,
        )
