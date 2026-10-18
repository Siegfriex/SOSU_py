"""Semantic validation of Gemini drafts (SSOT §14). Schema-valid is not the same as usable."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from urllib.parse import urlparse

from app.domain.evidence import CreatorConstraint, InsightObservationV1
from app.gemini.schemas import DiagnosisDraftV1, PrescriptionDraftV1


class ValidationOutcome(StrEnum):
    PASS = "PASS"
    REPAIRABLE = "REPAIRABLE"
    FATAL = "FATAL"


@dataclass(slots=True)
class ValidationReport:
    outcome: ValidationOutcome
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.outcome is ValidationOutcome.PASS


# ----------------------------------------------------------------- placeholder detection

_PLACEHOLDER_EXACT = frozenset(
    {"...", "…", "n/a", "na", "tbd", "todo", "placeholder", "미정", "없음", "-", "lorem ipsum"}
)
_PLACEHOLDER_SUBSTR = ("lorem ipsum", "placeholder", "tbd", "n/a")
_ONLY_DOTS = re.compile(r"^[.…\s]+$")


def is_placeholder(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    lowered = stripped.lower()
    if lowered in _PLACEHOLDER_EXACT or _ONLY_DOTS.match(stripped):
        return True
    return any(token in lowered for token in _PLACEHOLDER_SUBSTR)


# ----------------------------------------------------------------- Q18 keyword detection

FACE_KEYWORDS: tuple[str, ...] = (
    "얼굴",
    "표정",
    "셀피",
    "제작자 등장",
    "제작자가 직접 등장",
    "제작자가 등장",
    "얼굴을 보여",
    "on-camera",
    "on camera",
    "face",
    "selfie",
    "talking head",
)
VOICE_KEYWORDS: tuple[str, ...] = (
    "내레이션",
    "나레이션",
    "보이스오버",
    "보이스 오버",
    "목소리",
    "음성 해설",
    "음성으로 설명",
    "음성 설명",
    "직접 말하",
    "voice-over",
    "voiceover",
    "voice over",
    "narration",
    "narrate",
)

# A keyword followed (within a short window) by one of these markers is a compliant negation:
# "얼굴 노출 없이", "내레이션 대신 자막", "목소리를 쓰지 않고".
_NEGATION_MARKERS: tuple[str, ...] = (
    "없이",
    "대신",
    "하지 않",
    "않고",
    "않는",
    "않습",
    "금지",
    "불필요",
    "불가",
    "제외",
    "없는",
    "없어도",
    "without",
    "instead",
    "no ",
)
_NEGATION_WINDOW = 14


def _is_negated(text: str, start: int, end: int) -> bool:
    window = text[end : end + _NEGATION_WINDOW].lower()
    if any(marker in window for marker in _NEGATION_MARKERS):
        return True
    # English-style prefix negation: "without face", "no narration"
    before = text[max(0, start - 10) : start].lower()
    return any(m in before for m in ("without ", "no ", "not "))


def _pattern(keyword: str) -> re.Pattern[str]:
    escaped = re.escape(keyword.lower())
    # ASCII keywords get word boundaries so "face" does not match "surface"/"interface".
    if keyword.isascii():
        return re.compile(rf"\b{escaped}\b")
    return re.compile(escaped)


def find_violations(text: str, keywords: tuple[str, ...]) -> list[str]:
    """Keywords present in `text` that are not covered by a negation window."""
    lowered = text.lower()
    hits: list[str] = []
    for kw in keywords:
        for match in _pattern(kw).finditer(lowered):
            if not _is_negated(text, match.start(), match.end()):
                hits.append(kw)
                break
    return hits


# ----------------------------------------------------------------- helpers


def _check_text(errors: list[str], path: str, value: str) -> None:
    if is_placeholder(value):
        errors.append(f"{path}: 비어 있거나 placeholder입니다.")


def _check_list(errors: list[str], path: str, values: list[str]) -> None:
    if not values:
        errors.append(f"{path}: 비어 있습니다.")
    for i, v in enumerate(values):
        _check_text(errors, f"{path}[{i}]", v)


def _check_constraint(
    errors: list[str], constraint: CreatorConstraint, texts: list[tuple[str, str]]
) -> None:
    for path, text in texts:
        if not constraint.face_allowed:
            hits = find_violations(text, FACE_KEYWORDS)
            if hits:
                errors.append(
                    f"{path}: Q18 제약 위반 — 얼굴 노출 불가인데 {hits!r} 표현이 있습니다."
                )
        if not constraint.voice_allowed:
            hits = find_violations(text, VOICE_KEYWORDS)
            if hits:
                errors.append(
                    f"{path}: Q18 제약 위반 — 목소리 사용 불가인데 {hits!r} 표현이 있습니다."
                )


def _finalize(errors: list[str], total_text_fields: int) -> ValidationReport:
    if not errors:
        return ValidationReport(ValidationOutcome.PASS)
    placeholder_errors = sum(1 for e in errors if "placeholder" in e)
    # Structurally unusable: (almost) every text field is a placeholder → not worth a repair call.
    if total_text_fields and placeholder_errors >= max(3, int(total_text_fields * 0.8)):
        return ValidationReport(ValidationOutcome.FATAL, errors)
    return ValidationReport(ValidationOutcome.REPAIRABLE, errors)


# ----------------------------------------------------------------- public


def validate_diagnosis(draft: DiagnosisDraftV1, constraint: CreatorConstraint) -> ValidationReport:
    errors: list[str] = []
    texts: list[tuple[str, str]] = []

    for path, value in (
        ("brand.name", draft.brand.name),
        ("brand.material", draft.brand.material),
        ("brand.product", draft.brand.product),
        ("positioning.summary", draft.positioning.summary),
        ("positioning.rationale", draft.positioning.rationale),
        ("target.summary", draft.target.summary),
        ("target.description", draft.target.description),
        ("tone.description", draft.tone.description),
        ("fonts.title", draft.fonts.title),
        ("fonts.subtitle", draft.fonts.subtitle),
        ("fonts.reason", draft.fonts.reason),
    ):
        _check_text(errors, path, value)
        texts.append((path, value))

    _check_list(errors, "brand.keywords", draft.brand.keywords)
    _check_list(errors, "tone.keywords", draft.tone.keywords)

    if not draft.strengths:
        errors.append("strengths: 비어 있습니다.")
    for i, s in enumerate(draft.strengths):
        _check_text(errors, f"strengths[{i}].title", s.title)
        _check_text(errors, f"strengths[{i}].description", s.description)
        texts.append((f"strengths[{i}].description", s.description))

    ranks = sorted(p.rank for p in draft.priorities)
    if ranks != [1, 2, 3]:
        errors.append(f"priorities: rank는 정확히 1,2,3이어야 합니다 (현재 {ranks}).")
    constraint_texts: list[tuple[str, str]] = []
    for i, p in enumerate(draft.priorities):
        _check_text(errors, f"priorities[{i}].title", p.title)
        _check_text(errors, f"priorities[{i}].description", p.description)
        constraint_texts.append((f"priorities[{i}]", f"{p.title} {p.description}"))

    for i, r in enumerate(draft.reel_types):
        _check_text(errors, f"reel_types[{i}].name", r.name)
        _check_text(errors, f"reel_types[{i}].reason", r.reason)
        constraint_texts.append((f"reel_types[{i}]", f"{r.name} {r.reason}"))

    for slot in ("hook_0_3", "body_3_10", "body_10_20", "close_20_27", "cta_27_30"):
        value = getattr(draft.structure, slot)
        _check_text(errors, f"structure.{slot}", value)
        constraint_texts.append((f"structure.{slot}", value))

    _check_list(errors, "final_guidance", draft.final_guidance)
    for i, g in enumerate(draft.final_guidance):
        constraint_texts.append((f"final_guidance[{i}]", g))

    _check_constraint(errors, constraint, constraint_texts)

    total = len(texts) + len(constraint_texts) + 2
    return _finalize(errors, total)


def validate_prescription(
    draft: PrescriptionDraftV1,
    *,
    observation: InsightObservationV1 | None = None,
    instagram_url: str | None = None,
) -> ValidationReport:
    """Structural checks always; RD-5 grounding checks when the observation is supplied."""
    errors: list[str] = []
    _check_text(errors, "prescription.summary", draft.prescription.summary)
    _check_text(errors, "prescription.diagnosis", draft.prescription.diagnosis)

    orders = sorted(a.order for a in draft.next_actions)
    if orders != [1, 2, 3, 4]:
        errors.append(f"next_actions: order는 정확히 1,2,3,4이어야 합니다 (현재 {orders}).")
    for i, a in enumerate(draft.next_actions):
        _check_text(errors, f"next_actions[{i}].title", a.title)
        _check_text(errors, f"next_actions[{i}].description", a.description)

    _check_list(errors, "tone.keywords", draft.tone.keywords)
    _check_text(errors, "tone.description", draft.tone.description)

    if observation is not None or instagram_url:
        evidence = build_grounding_evidence(observation, instagram_url)
        errors.extend(check_prescription_grounding(draft, evidence))

    return _finalize(errors, 2 + len(draft.next_actions) * 2 + 2)


# ----------------------------------------------------------------- RD-5 grounding
#
# The analysed Reel is never watched: the only facts are the Insight screenshots. The account
# handle and the URL shortcode are identifiers, not content. A model that reads
# "@sosu_smoke_ceramics" and writes "도자기에 연기를 입히는 과정" has invented video content.

# Latin handle/slug token (substring, >= 4 letters) → Korean content nouns it suggests.
_CERAMIC_CLUSTER: tuple[str, ...] = (
    "도자기",
    "도예",
    "세라믹",
    "흙",
    "점토",
    "화병",
    "가마",
    "유약",
    "물레",
)
HANDLE_TOKEN_MAP: dict[str, tuple[str, ...]] = {
    "ceramic": _CERAMIC_CLUSTER,
    "pottery": _CERAMIC_CLUSTER,
    "potter": _CERAMIC_CLUSTER,
    "porcelain": _CERAMIC_CLUSTER,
    "kiln": ("가마", "소성"),
    "glaze": ("유약",),
    "vase": ("화병", "꽃병"),
    "clay": ("점토", "흙", "클레이"),
    "smoke": ("연기", "훈연", "스모크"),
    "candle": ("캔들", "양초", "향초"),
    "leather": ("가죽", "레더"),
    "knit": ("뜨개", "니트", "털실"),
    "crochet": ("뜨개", "코바늘"),
    "wood": ("나무", "목공", "원목", "우드"),
    "jewel": ("주얼리", "액세서리", "보석"),
    "accessor": ("액세서리",),
    "glass": ("유리",),
    "bead": ("비즈",),
    "soap": ("비누",),
    "resin": ("레진",),
    "silver": ("실버", "은반지"),
    "embroider": ("자수",),
    "fabric": ("원단", "패브릭"),
    "textile": ("원단", "패브릭"),
    "flower": ("플라워", "꽃다발", "생화"),
    "bake": ("베이킹", "케이크"),
    "metal": ("금속", "메탈"),
}

# Concrete product/material/process nouns. Asserting one of these about the analysed Reel
# requires it to appear in observed screenshot text.
_EXTRA_CONTENT_NOUNS: tuple[str, ...] = (
    "머그",
    "찻잔",
    "그릇",
    "접시",
    "반지",
    "귀걸이",
    "목걸이",
    "팔찌",
    "키링",
    "가방",
    "지갑",
    "향수",
    "판매 일정",
    "신제품",
)
CONTENT_NOUNS: tuple[str, ...] = tuple(
    dict.fromkeys(
        [noun for nouns in HANDLE_TOKEN_MAP.values() for noun in nouns] + list(_EXTRA_CONTENT_NOUNS)
    )
)
# Frame/edit nouns: describing these for the analysed Reel is only OK when hedged.
FRAME_NOUNS: tuple[str, ...] = (
    "장면",
    "컷",
    "자막",
    "썸네일",
    "배경음악",
    "BGM",
    "손동작",
    "클로즈업",
    "조명",
    "구도",
    "편집",
    "카피",
)

# Weak attribution: "이 영상은/에서/의…" — exempt inside an explicitly hypothetical sentence.
_WEAK_ATTRIBUTION = re.compile(
    r"(?<![가-힣])(이|해당|이번|분석한|분석 대상)\s*(영상|릴스|게시물)\s*"
    r"(은|는|이|에서|의|에|속|을|를)"
)
# Strong attribution: always a claim about the analysed Reel's content.
_STRONG_ATTRIBUTION = re.compile(
    r"(?<!다음 )(?<!다음)영상\s*속|영상에서\s*보여\s*준|보여\s*주신|촬영하신|업로드하신|올리신"
)
# Claims that the URL was visited or the video watched.
_WATCH_CLAIM = re.compile(
    r"(영상|릴스|링크|URL|url)(을|를)?\s*(직접\s*)?"
    r"(확인해\s*보니|확인한\s*결과|시청해\s*보니|시청한\s*결과|살펴보니|살펴본\s*결과)"
    r"|시청해\s*본\s*결과"
)
_HYPOTHETICAL = (
    "다음 영상",
    "다음 릴스",
    "예를 들어",
    "예를 들면",
    "예시",
    "예:",
    "시도해",
    "해 보세요",
    "해보세요",
)
_HEDGES = ("가능성", "보입니다", "보여요", "수 있", "추정", "것 같", "듯")

_HANDLE_RE = re.compile(r"@[A-Za-z0-9._]+")
_URL_RE = re.compile(r"https?://\S+")
# Split on sentence punctuation but keep decimals ("6.2초") intact.
_SENTENCE_SPLIT = re.compile(r"(?<!\d)[.!?。](?!\d)|\n")

COMMON_METRIC_LABELS: tuple[str, ...] = (
    "팔로워 아닌 계정 비율",
    "팔로워가 아닌 사람",
    "도달한 계정",
    "평균 시청 시간",
    "총 시청 시간",
    "다시 본 비율",
    "3초 이탈률",
    "프로필 방문",
    "프로필 활동",
    "영상 길이",
    "시청 시간",
    "조회수",
    "재생 횟수",
    "좋아요",
    "댓글",
    "공유",
    "저장",
    "팔로우",
    "도달",
    "노출",
)
_METRIC_WINDOW = 14
_NUMBER_STOP = re.compile(r"[,.;·]\s|읽을 수 없|확인되지|확인할 수 없|알 수 없")


@dataclass(slots=True)
class GroundingEvidence:
    """What the prescription may rely on.

    `observed_text` is every observed string with @handles and URLs removed (lower-cased), so
    a handle cannot whitelist the nouns it suggests. `handle_sources` maps each matched Latin
    token (e.g. "ceramic") to the identifier it came from ("@sosu_smoke_ceramics").
    """

    observed_text: str = ""
    handle_sources: dict[str, str] = field(default_factory=dict)
    unreadable_labels: list[str] = field(default_factory=list)
    known_labels: list[str] = field(default_factory=list)

    def is_observed(self, noun: str) -> bool:
        return noun.lower() in self.observed_text


def _observation_strings(observation: InsightObservationV1) -> list[str]:
    out: list[str] = list(observation.cross_image_signals)
    for shot in observation.screenshots:
        out.extend(m.label for m in shot.visible_metrics)
        out.extend(m.value_text for m in shot.visible_metrics)
        out.extend(shot.qualitative_notes)
        out.extend(shot.unreadable_regions)
    return out


def _url_slug(instagram_url: str) -> str:
    try:
        path = urlparse(instagram_url.strip()).path
    except ValueError:
        return ""
    parts = [p for p in path.split("/") if p and p not in {"reel", "reels", "p"}]
    return parts[-1] if parts else ""


def build_grounding_evidence(
    observation: InsightObservationV1 | None, instagram_url: str | None
) -> GroundingEvidence:
    strings = _observation_strings(observation) if observation is not None else []
    identifiers: list[str] = []
    for s in strings:
        identifiers.extend(_HANDLE_RE.findall(s))
    if instagram_url:
        slug = _url_slug(instagram_url)
        if slug:
            identifiers.append(slug)

    handle_sources: dict[str, str] = {}
    for ident in identifiers:
        letters = re.sub(r"[^a-z]", "", ident.lower())
        for token in HANDLE_TOKEN_MAP:
            if token in letters and token not in handle_sources:
                handle_sources[token] = ident

    observed = " ".join(_URL_RE.sub(" ", _HANDLE_RE.sub(" ", s)) for s in strings).lower()

    readable_labels = (
        {m.label for shot in observation.screenshots for m in shot.visible_metrics}
        if observation is not None
        else set()
    )
    unreadable: list[str] = []
    if observation is not None:
        for shot in observation.screenshots:
            for region in shot.unreadable_regions:
                for label in COMMON_METRIC_LABELS:
                    if label not in region:
                        continue
                    # "도달" inside a readable "도달한 계정" is not an unreadable metric.
                    if any(label in readable for readable in readable_labels):
                        continue
                    if any(label in longer for longer in unreadable):
                        continue
                    unreadable.append(label)
    return GroundingEvidence(
        observed_text=observed,
        handle_sources=handle_sources,
        unreadable_labels=unreadable,
        known_labels=sorted(set(COMMON_METRIC_LABELS) | readable_labels, key=len, reverse=True),
    )


def _prescription_texts(draft: PrescriptionDraftV1) -> list[tuple[str, str]]:
    texts = [
        ("prescription.summary", draft.prescription.summary),
        ("prescription.diagnosis", draft.prescription.diagnosis),
    ]
    for i, a in enumerate(draft.next_actions):
        texts.append((f"next_actions[{i}].title", a.title))
        texts.append((f"next_actions[{i}].description", a.description))
    texts.append(("tone.description", draft.tone.description))
    texts.append(("tone.keywords", " ".join(draft.tone.keywords)))
    return texts


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]


def _snippet(sentence: str, limit: int = 60) -> str:
    return sentence if len(sentence) <= limit else sentence[: limit - 1] + "…"


def _number_after(text: str, start: int, labels: list[str]) -> bool:
    window = text[start : start + _METRIC_WINDOW]
    stop = _NUMBER_STOP.search(window)
    if stop:
        window = window[: stop.start()]
    for other in COMMON_METRIC_LABELS:
        idx = window.find(other)
        if idx > 0 and other not in labels:
            window = window[:idx]
    return bool(re.search(r"\d", window))


def _inside_longer_label(text: str, start: int, label: str, known: list[str]) -> bool:
    """True when the match is part of a longer label ("시청 시간" inside "평균 시청 시간")."""
    for longer in known:
        if len(longer) <= len(label) or label not in longer:
            continue
        offset = longer.index(label)
        begin = start - offset
        if begin >= 0 and text[begin : begin + len(longer)] == longer:
            return True
    return False


def check_prescription_grounding(
    draft: PrescriptionDraftV1, evidence: GroundingEvidence
) -> list[str]:
    """REPAIRABLE issues: content inferred from the handle/URL, claims about unseen video
    content, claims of having watched the Reel, numbers for unreadable metrics."""
    errors: list[str] = []
    for path, text in _prescription_texts(draft):
        # (b) handle/URL-derived nouns — flagged however they are phrased (examples included).
        reported: set[str] = set()
        for token, source in evidence.handle_sources.items():
            for noun in HANDLE_TOKEN_MAP[token]:
                if noun in reported or noun not in text or evidence.is_observed(noun):
                    continue
                reported.add(noun)
                errors.append(
                    f"{path}: 근거 없는 영상 내용 — '{noun}'은(는) 스크린샷 화면 텍스트에 없고 "
                    f"계정명/URL('{source}')에서만 유추되는 표현입니다. 계정명·URL은 식별자일 뿐 "
                    "영상 내용이 아닙니다. 이 표현을 삭제하거나 제품·소재·공정을 특정하지 않는 "
                    "일반적인 표현(예: '완성작', '작업 과정')으로 바꾸세요."
                )

        for sentence in _sentences(text):
            # Claims of having visited the URL / watched the video.
            if _WATCH_CLAIM.search(sentence):
                errors.append(
                    f"{path}: 영상 시청 주장 — 릴스 URL/영상을 직접 확인한 것처럼 서술했습니다: "
                    f'"{_snippet(sentence)}". 영상은 관측되지 않았습니다. 스크린샷 지표 근거로만 '
                    "다시 쓰세요."
                )
                continue
            # (a) facts about the analysed Reel's content.
            strong = _STRONG_ATTRIBUTION.search(sentence)
            weak = _WEAK_ATTRIBUTION.search(sentence)
            hypothetical = any(m in sentence for m in _HYPOTHETICAL)
            if not (strong or (weak and not hypothetical)):
                continue
            nouns = [
                n
                for n in CONTENT_NOUNS
                if n in sentence and not evidence.is_observed(n) and n not in reported
            ]
            hedged = any(h in sentence for h in _HEDGES)
            if not hedged or strong:
                nouns += [
                    n for n in FRAME_NOUNS if n in sentence and not evidence.is_observed(n.lower())
                ]
            if nouns:
                errors.append(
                    f"{path}: 근거 없는 영상 내용 단정 — 분석한 릴스의 장면·제품·소재·공정·편집"
                    f"({', '.join(repr(n) for n in nouns)})을 관측된 사실처럼 서술했습니다: "
                    f'"{_snippet(sentence)}". 영상 내용은 관측되지 않았습니다. 관측 지표 근거 '
                    "문장으로 바꾸거나, 아이디어라면 '다음 영상에서 시도해 볼 수 있는 예'로 "
                    "명시하고 분석한 영상에 귀속시키지 마세요."
                )

        # Unreadable metric must not get a number.
        for label in evidence.unreadable_labels:
            for match in re.finditer(re.escape(label), text):
                if _inside_longer_label(text, match.start(), label, evidence.known_labels):
                    continue
                if _number_after(text, match.end(), evidence.unreadable_labels):
                    errors.append(
                        f"{path}: 읽을 수 없는 지표 '{label}'에 수치를 적었습니다. 관측에서 "
                        "unreadable로 기록된 값이므로 숫자를 삭제하고 '확인되지 않음'으로만 "
                        "언급하세요."
                    )
                    break
    return errors
