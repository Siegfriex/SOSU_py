# ruff: noqa: E501  -- prompt prose lines are intentionally long
"""GuidebookKnowledgeProvider — loads the KnowledgePack once, selects rules per request.

Failure policy (documented in docs/KNOWLEDGE.md): a missing or invalid pack never breaks the
service. The provider logs a warning, reports `version == "none"`, selects no rules, and the
prompt carries an explicit "guidebook unavailable" block instead.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from pydantic import ValidationError

from app.config import get_settings
from app.contracts.enums import CreatorDisclosure
from app.domain.evidence import DeclaredEvidenceV1, InsightObservationV1, VisualObservationV1
from app.knowledge.models import (
    GuidebookRule,
    KnowledgePackV1,
    KnowledgeTask,
    RuleCategory,
    StyleGuide,
)

log = logging.getLogger("sosu.knowledge")

NO_KNOWLEDGE_VERSION = "none"
DEFAULT_MAX_RULES = 30
DEFAULT_MAX_CHARS = 4800  # rule text only; header + style add ~1k → block ≈ 6k

DEFAULT_KNOWLEDGE_PATH = (
    Path(__file__).resolve().parents[2] / "knowledge" / "guidebook" / "knowledgepack.v1.json"
)

# ------------------------------------------------------------------ survey/insight → signals

# Tags are free-form strings authored in the pack; we match a generous set of synonyms.
# Codes shared by several questions (process, specialness, yes/no …) are matched ONLY in their
# question-prefixed form (q17_process, q18_no); unique codes (q16 pain points) also match raw.
_PAIN_SIGNALS: dict[str, tuple[set[str], set[str]]] = {
    # code: (tags, categories to boost)
    "low_reach": (
        {"reach", "low_reach", "hook", "algorithm", "discovery"},
        {"hook", "video_length"},
    ),
    "low_follower_growth": (
        {"follow", "follower", "follower_growth", "low_follower_growth", "consistency", "series"},
        {"cta", "brand_strategy"},
    ),
    "ideation": (
        {"ideation", "idea", "ideas", "planning", "series"},
        {"ideation", "combination", "reel_types"},
    ),
    "shooting_difficulty": (
        {"shooting", "shooting_difficulty", "equipment", "smartphone", "lighting", "beginner"},
        {"equipment", "lighting", "composition", "camera_angle"},
    ),
    "editing_difficulty": (
        {"editing", "editing_difficulty", "capcut", "cut", "pacing", "beginner"},
        {"editing_pacing", "music_sound", "storyboard"},
    ),
    "consistency_difficulty": (
        {"consistency", "consistency_difficulty", "routine", "series", "batch"},
        {"ideation", "storyboard"},
    ),
    "low_conversion": (
        {"conversion", "low_conversion", "cta", "caption", "profile", "purchase"},
        {"cta", "caption"},
    ),
}

_FORMAT_SIGNALS: dict[str, set[str]] = {
    "rarely_post": {"rarely_post", "beginner", "first_reel", "consistency"},
    "finished_product": {"finished_product", "product", "product_showcase", "showcase"},
    "process": {"making", "making_process", "behind_the_scenes"},
    "photo_video_mix": {"photo_video_mix", "photo", "slideshow"},
    "trend_reels": {"trend", "trend_reels", "trending_audio", "music"},
    "vlog": {"vlog", "storytelling", "daily"},
}

_FACE_TAGS = {"face", "face_required", "on_camera", "talking_head", "selfie", "creator_on_camera"}
_VOICE_TAGS = {"voice", "voice_required", "voiceover", "voice_over", "narration", "talking_head"}
# A rule offering a face/voice alternative is never excluded by the generic keyword filter.
# Current CONSTRAINTS text forbids any narration (incl. TTS) when voice is disallowed.
_HARD_VOICE_TAGS = frozenset({"narration", "tts", "voiceover", "voice_over", "narration_speed"})
_ALTERNATIVE_TAGS = {"voice_alternative", "hands_only", "tts", "faceless", "no_face", "no_voice"}
_FACELESS_TAGS = {"faceless", "no_face", "hands_only", "hands", "caption_only", "text_overlay"}
_VOICELESS_TAGS = {"no_voice", "caption", "subtitle", "subtitles", "text_overlay", "bgm"}

_INSIGHT_KEYWORDS: tuple[tuple[tuple[str, ...], set[str]], ...] = (
    (("저장", "save"), {"save", "saves", "engagement"}),
    (("공유", "share", "보내기"), {"share", "shares", "engagement"}),
    (
        ("시청", "watch", "유지", "retention", "재생"),
        {"retention", "watch_time", "hook", "video_length"},
    ),
    (("도달", "reach", "노출", "impression"), {"reach", "discovery"}),
    (("팔로워", "follow"), {"follow", "follower", "follower_growth"}),
    (("프로필", "profile", "링크", "link"), {"profile", "cta", "conversion"}),
    (("댓글", "comment"), {"comment", "engagement"}),
    (("좋아요", "like"), {"like", "engagement"}),
)

_NORM = re.compile(r"[\s\-]+")


def _norm(tag: str) -> str:
    return _NORM.sub("_", tag.strip().lower())


@dataclass(frozen=True, slots=True)
class SelectionSignals:
    tags: frozenset[str] = frozenset()
    boost_categories: frozenset[str] = frozenset()
    excluded_tags: frozenset[str] = frozenset()
    # q18_* tag of this request ("q18_no" ...). Rules explicitly scoped to other q18 answers
    # (they carry q18_* tags but not this one) are excluded. None → no q18 scoping.
    disclosure_tag: str | None = None
    # Tags excluded regardless of q18 scoping / alternatives (hard creator constraint).
    hard_excluded_tags: frozenset[str] = frozenset()


def diagnosis_signals(
    declared: DeclaredEvidenceV1, visual: VisualObservationV1 | None = None
) -> SelectionSignals:
    tags: set[str] = set()
    cats: set[str] = set()
    excluded: set[str] = set()
    for pain in declared.q16_pain_points:
        code = pain.value
        tags |= {code, f"q16_{code}", f"q16:{code}"}
        extra_tags, extra_cats = _PAIN_SIGNALS.get(code, (set(), set()))
        tags |= extra_tags
        cats |= extra_cats
    for fmt in declared.q17_current_formats:
        code = fmt.value
        tags |= {f"q17_{code}", f"q17:{code}"} | _FORMAT_SIGNALS.get(code, set())
    disclosure = declared.q18_disclosure
    if disclosure is not None:
        tags |= {f"q18_{disclosure.value}", f"q18:{disclosure.value}"}
    constraint = declared.creator_constraint
    if not constraint.face_allowed:
        excluded |= _FACE_TAGS
        tags |= _FACELESS_TAGS
    if not constraint.voice_allowed:
        excluded |= _VOICE_TAGS
        tags |= _VOICELESS_TAGS
    if disclosure is CreatorDisclosure.YES:
        tags |= {"face", "on_camera", "voiceover", "talking_head"}
    for appeal in declared.q6_product_appeals:
        tags |= {f"q6_{appeal.value}"}
    # q11 shares q10's option set; the pack tags both as q10_* (pack convention).
    for emotion in [*declared.q10_desired_emotions, *declared.q11_brand_attributes]:
        tags |= {f"q10_{emotion.value}"}
    for motive in declared.q9_purchase_motives:
        tags |= {f"q9_{motive.value}"}
    if declared.q15_interesting_process:
        tags |= {"process_as_content", "process_reveal", "making"}
    if visual is not None:
        tags |= {"product_closeup", "visual_asset", "detail", "texture"}
    return SelectionSignals(
        tags=frozenset(_norm(t) for t in tags),
        boost_categories=frozenset(cats),
        excluded_tags=frozenset(_norm(t) for t in excluded),
        disclosure_tag=f"q18_{disclosure.value}" if disclosure is not None else None,
        hard_excluded_tags=frozenset() if constraint.voice_allowed else _HARD_VOICE_TAGS,
    )


def prescription_signals(observation: InsightObservationV1) -> SelectionSignals:
    texts: list[str] = list(observation.cross_image_signals)
    for shot in observation.screenshots:
        texts.extend(m.label for m in shot.visible_metrics)
        texts.extend(shot.qualitative_notes)
    blob = " ".join(texts).lower()
    tags: set[str] = {"performance", "metrics", "insight"}
    for keywords, mapped in _INSIGHT_KEYWORDS:
        if any(k in blob for k in keywords):
            tags |= mapped
    return SelectionSignals(
        tags=frozenset(_norm(t) for t in tags),
        boost_categories=frozenset({"performance_interpretation"}),
    )


# ------------------------------------------------------------------ provider


def _valid_rules(raw_rules: list[object]) -> list[GuidebookRule]:
    """Drop individually invalid rules (warning) instead of rejecting the whole pack."""
    valid: list[GuidebookRule] = []
    for i, item in enumerate(raw_rules):
        try:
            valid.append(GuidebookRule.model_validate(item))
        except ValidationError as exc:
            rid = item.get("rule_id") if isinstance(item, dict) else None
            log.warning(
                "knowledge rule skipped index=%d rule_id=%s errors=%d", i, rid, exc.error_count()
            )
    return valid


@dataclass(frozen=True, slots=True)
class KnowledgeSelection:
    task: KnowledgeTask
    version: str
    pack_id: str | None
    rules: tuple[GuidebookRule, ...]
    style: StyleGuide | None

    @property
    def rule_ids(self) -> list[str]:
        return [r.rule_id for r in self.rules]

    def render(self) -> str:
        return render_knowledge_block(self.rules, self.style, version=self.version, task=self.task)


@dataclass(slots=True)
class GuidebookKnowledgeProvider:
    pack: KnowledgePackV1 | None
    source_path: str | None = None
    max_rules: int = DEFAULT_MAX_RULES
    max_chars: int = DEFAULT_MAX_CHARS
    _rules: tuple[GuidebookRule, ...] = field(default=(), init=False)

    def __post_init__(self) -> None:
        if self.pack is None:
            return
        seen: set[str] = set()
        unique: list[GuidebookRule] = []
        for rule in self.pack.rules:
            if rule.rule_id in seen:
                log.warning("knowledge duplicate rule_id=%s ignored", rule.rule_id)
                continue
            seen.add(rule.rule_id)
            unique.append(rule)
        self._rules = tuple(unique)

    # -------------------------------------------------------------- loading

    @classmethod
    def from_path(cls, path: str | Path) -> GuidebookKnowledgeProvider:
        p = Path(path)
        if not p.is_file():
            log.warning("knowledge pack not found path=%s -> knowledge_version=none", p)
            return cls(pack=None, source_path=str(p))
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and isinstance(raw.get("rules"), list):
                raw["rules"] = _valid_rules(raw["rules"])
            pack = KnowledgePackV1.model_validate(raw)
        except (OSError, ValueError, ValidationError) as exc:
            log.warning(
                "knowledge pack invalid path=%s error=%s -> knowledge_version=none",
                p,
                type(exc).__name__,
            )
            return cls(pack=None, source_path=str(p))
        log.info(
            "knowledge pack loaded pack=%s version=%s rules=%d",
            pack.pack_id,
            pack.version,
            len(pack.rules),
        )
        return cls(pack=pack, source_path=str(p))

    @property
    def available(self) -> bool:
        return self.pack is not None and bool(self._rules)

    @property
    def version(self) -> str:
        return self.pack.version if self.pack is not None else NO_KNOWLEDGE_VERSION

    # -------------------------------------------------------------- selection

    def select_for_diagnosis(
        self, declared: DeclaredEvidenceV1, visual: VisualObservationV1 | None = None
    ) -> KnowledgeSelection:
        return self._select("diagnosis", diagnosis_signals(declared, visual))

    def select_for_prescription(self, observation: InsightObservationV1) -> KnowledgeSelection:
        return self._select("prescription", prescription_signals(observation))

    def _select(self, task: KnowledgeTask, signals: SelectionSignals) -> KnowledgeSelection:
        if self.pack is None:
            return KnowledgeSelection(task, NO_KNOWLEDGE_VERSION, None, (), None)

        mapping = self.pack.task_mapping.get(task, {})
        mapped: list[RuleCategory] = []
        for cats in mapping.values():
            for c in cats:
                if c not in mapped:
                    mapped.append(c)

        def tags_of(rule: GuidebookRule) -> set[str]:
            return {_norm(t) for t in rule.tags}

        def compatible(rule: GuidebookRule) -> bool:
            tags = tags_of(rule)
            # Hard Q18 constraint wins over the guidebook: no narration/TTS when voice is forbidden.
            if tags & signals.hard_excluded_tags:
                return False
            q18_scoped = {t for t in tags if t.startswith("q18_")}
            if q18_scoped:
                # Pack-authored disclosure scoping wins over generic keyword exclusion.
                return signals.disclosure_tag is None or signals.disclosure_tag in q18_scoped
            if tags & _ALTERNATIVE_TAGS:
                return True
            return not (tags & signals.excluded_tags)

        candidates = [r for r in self._rules if task in r.applicability and compatible(r)]

        def score(rule: GuidebookRule) -> int:
            s = (4 - rule.priority) * 10
            if rule.category in mapped:
                s += 6
            if rule.category in signals.boost_categories:
                s += 8
            s += 7 * min(len(tags_of(rule) & signals.tags), 3)
            return s

        ranked = sorted(candidates, key=lambda r: (-score(r), r.priority, r.rule_id))

        chosen: list[GuidebookRule] = []
        budget = self.max_chars

        def take(rule: GuidebookRule) -> bool:
            nonlocal budget
            cost = len(_render_rule(rule))
            if rule in chosen or len(chosen) >= self.max_rules or cost > budget:
                return False
            chosen.append(rule)
            budget -= cost
            return True

        # Pass 1: coverage — the best rule of every mapped/boosted category.
        for cat in [*mapped, *sorted(signals.boost_categories - set(mapped))]:
            for rule in ranked:
                if rule.category == cat:
                    take(rule)
                    break
        # Pass 2: fill by score.
        for rule in ranked:
            take(rule)

        order = {r.rule_id: i for i, r in enumerate(ranked)}
        chosen.sort(key=lambda r: order[r.rule_id])
        return KnowledgeSelection(
            task=task,
            version=self.pack.version,
            pack_id=self.pack.pack_id,
            rules=tuple(chosen),
            style=self.pack.style,
        )


# ------------------------------------------------------------------ rendering

_TASK_USE = {
    "diagnosis": (
        "릴스 유형(reel_types)·30초 구조(structure)·훅·자막/캡션·CTA·촬영/편집 가이드를 고를 때 아래 규칙을 적용하세요. "
        "규칙과 CONSTRAINTS가 충돌하면 항상 CONSTRAINTS가 우선합니다."
    ),
    "prescription": (
        "관측된 지표를 해석하고 next_actions의 우선순위를 정할 때 아래 규칙을 적용하세요. "
        "규칙은 관측값을 대체하지 않으며, unreadable 지표를 추정하는 근거로 쓰지 않습니다."
    ),
}


def _pages(rule: GuidebookRule) -> str:
    return ", ".join(f"p.{p}" for p in rule.source_pages) or "p.?"


def _render_rule(rule: GuidebookRule) -> str:
    line = f"- [{rule.rule_id}] ({rule.category}; {_pages(rule)}; {rule.evidence_type}) {rule.principle.strip()}"
    if rule.recommended_action.strip():
        line += f"\n  → 권장: {rule.recommended_action.strip()}"
    if rule.exceptions_or_cautions and rule.exceptions_or_cautions.strip():
        line += f"\n  ⚠ 주의: {rule.exceptions_or_cautions.strip()}"
    return line + "\n"


def _style_lines(style: StyleGuide) -> list[str]:
    lines: list[str] = []
    for label, values in (
        ("voice", style.voice),
        ("do", style.do),
        ("don't", style.dont),
        ("예시 표현", style.example_phrases),
    ):
        for v in values[:8]:
            lines.append(f"- {label}: {v.strip()}")
    return lines


def render_knowledge_block(
    rules: tuple[GuidebookRule, ...] | list[GuidebookRule],
    style: StyleGuide | None,
    *,
    version: str,
    task: KnowledgeTask,
) -> str:
    if version == NO_KNOWLEDGE_VERSION or not rules:
        return (
            f"## GUIDEBOOK KNOWLEDGE (version {NO_KNOWLEDGE_VERSION})\n"
            "가이드북 지식이 제공되지 않았습니다. 가이드북 규칙 ID나 페이지를 인용하지 말고, 제공된 근거만으로 작성하세요.\n"
            "## END GUIDEBOOK KNOWLEDGE"
        )
    parts = [
        f"## GUIDEBOOK KNOWLEDGE (version {version}; cite rule_id and pages)",
        "SOSU 가이드북(저자의 원칙·사례·경험)에서 이 요청에 맞게 선별한 편집 규칙입니다. "
        "사용자 근거(EVIDENCE)가 아니라 '어떻게 만들지'에 대한 전문가 지식입니다.",
        _TASK_USE[task],
        "가이드북 규칙을 Instagram 알고리즘·플랫폼 정책에 대한 외부 검증 사실처럼 표현하지 마세요 "
        "(예: '알고리즘이 반드시 ~한다' 금지; '가이드북 권장 방식' 수준으로 서술).",
        "",
        *[_render_rule(r).rstrip("\n") for r in rules],
    ]
    if style is not None:
        style_lines = _style_lines(style)
        if style_lines:
            parts += [
                "",
                "### EDITORIAL STYLE (가이드북 문체 — 출력 문장의 톤에 반영)",
                *style_lines,
            ]
    parts.append("## END GUIDEBOOK KNOWLEDGE")
    return "\n".join(parts)


@lru_cache(maxsize=1)
def get_knowledge_provider() -> GuidebookKnowledgeProvider:
    configured = get_settings().sosu_knowledge_path.strip()
    return GuidebookKnowledgeProvider.from_path(configured or DEFAULT_KNOWLEDGE_PATH)
