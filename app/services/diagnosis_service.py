"""Workflow A: request → DeclaredEvidence → (VisualObservation) → synthesis → validate/repair."""

from __future__ import annotations

import logging
from collections.abc import Sequence

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
from app.knowledge.provider import GuidebookKnowledgeProvider, get_knowledge_provider
from app.services.deadline import budget_spec, with_deadline
from app.services.repair import run_with_repair

log = logging.getLogger("sosu.diagnosis")


class DiagnosisService:
    def __init__(
        self,
        gateway: GeminiGateway,
        *,
        settings: Settings | None = None,
        knowledge: GuidebookKnowledgeProvider | None = None,
    ) -> None:
        self._gateway = gateway
        self._settings = settings
        self._knowledge = knowledge

    @property
    def knowledge(self) -> GuidebookKnowledgeProvider:
        if self._knowledge is None:
            self._knowledge = get_knowledge_provider()
        return self._knowledge

    @property
    def settings(self) -> Settings:
        if self._settings is None:
            self._settings = get_settings()
        return self._settings

    async def run(
        self,
        request: SurveyDiagnosisRequestV1,
        product_images: NormalizedImage | Sequence[NormalizedImage] | None,
        *,
        request_id: str,
    ) -> DiagnosisReportV1:
        """`product_images`: 0..3 photos (a single image or None is accepted as shorthand)."""
        if product_images is None:
            images: list[NormalizedImage] = []
        elif isinstance(product_images, NormalizedImage):
            images = [product_images]
        else:
            images = list(product_images)
        return await with_deadline(
            self._run(request, images, request_id=request_id),
            seconds=self.settings.sosu_request_deadline_seconds,
            request_id=request_id,
        )

    async def _run(
        self,
        request: SurveyDiagnosisRequestV1,
        images: list[NormalizedImage],
        *,
        request_id: str,
    ) -> DiagnosisReportV1:
        declared = normalize_survey(request.answers)

        visual: VisualObservationV1 | None = None
        if images:
            # One observation call over all photos: a single product seen from several angles.
            visual = await self._observe(images, locale=request.locale, request_id=request_id)

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
        log.info("diagnosis request_id=%s done images=%d", request_id, len(images))
        return to_public_diagnosis(final)

    # ------------------------------------------------------------------ calls

    async def _observe(
        self, images: list[NormalizedImage], *, locale: str, request_id: str
    ) -> VisualObservationV1:
        s = self.settings
        # Deliberately survey-free: the observation prompt takes no survey argument.
        system, user = visual_prompt.build_visual_observation_prompt(
            locale=locale, image_count=len(images)
        )
        result = await self._gateway.generate_structured(
            spec=budget_spec(
                GenerationSpec(
                    model=s.gemini_model_observe,
                    thinking=s.gemini_thinking_observe,
                    max_output_tokens=s.gemini_max_output_observe,
                    prompt_version=visual_prompt.PROMPT_VERSION,
                    timeout_seconds=s.gemini_timeout_observe,
                )
            ),
            system_instruction=system,
            user_text=user,
            images=[ImagePart(data=image.data, mime_type=image.mime_type) for image in images],
            schema=VisualObservationV1,
        )
        log.info("diagnosis request_id=%s prompt=%s ok", request_id, visual_prompt.PROMPT_VERSION)
        return result.value

    async def _synthesize(self, pack: EvidencePackV1, *, request_id: str) -> DiagnosisDraftV1:
        s = self.settings
        selection = self.knowledge.select_for_diagnosis(pack.declared, pack.visual)
        system, user = diagnosis_prompt.build_diagnosis_prompt(pack, knowledge=selection.render())
        log.info(
            "diagnosis request_id=%s knowledge_version=%s rules=%d",
            request_id,
            selection.version,
            len(selection.rules),
        )
        result = await self._gateway.generate_structured(
            spec=budget_spec(
                GenerationSpec(
                    model=s.gemini_model_diagnosis,
                    thinking=s.gemini_thinking_synthesis,
                    max_output_tokens=s.gemini_max_output_diagnosis,
                    prompt_version=diagnosis_prompt.PROMPT_VERSION,
                    timeout_seconds=s.gemini_timeout_synthesis,
                )
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
