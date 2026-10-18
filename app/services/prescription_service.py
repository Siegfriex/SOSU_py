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
from app.knowledge.provider import GuidebookKnowledgeProvider, get_knowledge_provider
from app.research.models import ResearchQuery
from app.research.provider import ResearchProvider, get_research_provider
from app.services.deadline import budget_spec, with_deadline
from app.services.repair import run_with_repair

log = logging.getLogger("sosu.prescription")

_PRESCRIPTION_CONSTRAINTS = (
    "- 릴스 URL 내용은 관측되지 않았음. 영상 내용을 본 것처럼 쓰지 말 것.\n"
    "- 계정명(@handle)·URL은 식별자일 뿐 영상 내용이 아님. 여기서 제품·소재·공정을 유추한 "
    "표현(예: 계정명의 영단어를 번역한 명사)은 삭제하거나 "
    "'완성작', '작업 과정' 같은 일반 표현으로 바꿀 것.\n"
    "- 분석한 릴스의 장면·제품·소재·공정·편집을 사실처럼 쓰지 말 것. 아이디어는 "
    "'다음 영상에서 시도해 볼 수 있는 예'로만 쓰고 분석한 영상에 귀속시키지 말 것.\n"
    "- unreadable로 기록된 지표는 추정하지 말고 숫자를 쓰지 말 것.\n"
    "- 관측된 지표 수치·라벨은 그대로 유지할 것."
)


class PrescriptionService:
    def __init__(
        self,
        gateway: GeminiGateway,
        *,
        settings: Settings | None = None,
        knowledge: GuidebookKnowledgeProvider | None = None,
        research: ResearchProvider | None = None,
    ) -> None:
        self._gateway = gateway
        self._settings = settings
        self._knowledge = knowledge
        self._research = research

    @property
    def knowledge(self) -> GuidebookKnowledgeProvider:
        if self._knowledge is None:
            self._knowledge = get_knowledge_provider()
        return self._knowledge

    @property
    def research(self) -> ResearchProvider:
        if self._research is None:
            self._research = get_research_provider()
        return self._research

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
            validate=lambda d: validate_prescription(
                d, observation=observation, instagram_url=request.instagram_url
            ),
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
            spec=budget_spec(
                GenerationSpec(
                    model=s.gemini_model_observe,
                    thinking=s.gemini_thinking_observe,
                    max_output_tokens=s.gemini_max_output_observe,
                    prompt_version=insight_prompt.PROMPT_VERSION,
                    timeout_seconds=s.gemini_timeout_observe,
                )
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
        selection = self.knowledge.select_for_prescription(observation)
        research = await self.research.research(
            [
                ResearchQuery(
                    query="Instagram Reels 성과 지표 해석 최신 동향",
                    task="prescription",
                    locale=locale,
                )
            ]
        )
        system, user = prescription_prompt.build_prescription_prompt(
            observation,
            instagram_url=instagram_url,
            locale=locale,
            knowledge=selection.render(),
            research=research,
        )
        log.info(
            "prescription request_id=%s knowledge_version=%s rules=%d research=%s",
            request_id,
            selection.version,
            len(selection.rules),
            research.status,
        )
        result = await self._gateway.generate_structured(
            spec=budget_spec(
                GenerationSpec(
                    model=s.gemini_model_prescription,
                    thinking=s.gemini_thinking_synthesis,
                    max_output_tokens=s.gemini_max_output_prescription,
                    prompt_version=prescription_prompt.PROMPT_VERSION,
                    timeout_seconds=s.gemini_timeout_synthesis,
                )
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
