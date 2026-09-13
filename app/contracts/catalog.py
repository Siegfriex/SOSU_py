"""Korean UI label → stable code catalog for every categorical question.

Labels follow the SSOT (§5); codes follow CONTRACT V1 (which wins over SSOT codes).
The frontend owns label rendering; this catalog exists so the backend can prove every
UI option has exactly one stable code and vice versa.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from app.contracts.enums import (
    BrandAttribute,
    CreatorDisclosure,
    CurrentReelFormat,
    DesiredEmotion,
    InstagramPainPoint,
    ProductAppeal,
    PurchaseMotive,
)

Q6_PRODUCT_APPEALS: Final[Mapping[str, ProductAppeal]] = MappingProxyType(
    {
        "디자인": ProductAppeal.DESIGN,
        "색감": ProductAppeal.COLOR,
        "디테일": ProductAppeal.DETAIL,
        "질감": ProductAppeal.TEXTURE,
        "소재": ProductAppeal.MATERIAL,
        "제작 과정": ProductAppeal.PROCESS,
        "스토리": ProductAppeal.STORY,
        "희소성": ProductAppeal.RARITY,
        "기타": ProductAppeal.OTHER,
    }
)

Q9_PURCHASE_MOTIVES: Final[Mapping[str, PurchaseMotive]] = MappingProxyType(
    {
        "예뻐서": PurchaseMotive.AESTHETIC,
        "특별해서": PurchaseMotive.SPECIALNESS,
        "나를 위해": PurchaseMotive.SELF_REWARD,
        "선물하려고": PurchaseMotive.GIFT,
        "추억을 간직하려고": PurchaseMotive.MEMORIES,
        "공간을 꾸미려고": PurchaseMotive.SPACE_DECOR,
        "나만의 것을 갖고 싶어서": PurchaseMotive.SELF_EXPRESSION,
    }
)

# Q10 (customer feels) and Q11 (brand is) share labels but are separate namespaces.
Q10_DESIRED_EMOTIONS: Final[Mapping[str, DesiredEmotion]] = MappingProxyType(
    {
        "설렘": DesiredEmotion.EXCITEMENT,
        "행복": DesiredEmotion.HAPPINESS,
        "따뜻함": DesiredEmotion.WARMTH,
        "힐링": DesiredEmotion.HEALING,
        "재미": DesiredEmotion.FUN,
        "특별함": DesiredEmotion.SPECIALNESS,
        "감동": DesiredEmotion.MOVED,
        "위로": DesiredEmotion.COMFORT,
        "기타": DesiredEmotion.OTHER,
    }
)

Q11_BRAND_ATTRIBUTES: Final[Mapping[str, BrandAttribute]] = MappingProxyType(
    {
        "설렘": BrandAttribute.EXCITEMENT,
        "행복": BrandAttribute.HAPPINESS,
        "따뜻함": BrandAttribute.WARMTH,
        "힐링": BrandAttribute.HEALING,
        "재미": BrandAttribute.FUN,
        "특별함": BrandAttribute.SPECIALNESS,
        "감동": BrandAttribute.MOVED,
        "위로": BrandAttribute.COMFORT,
        "기타": BrandAttribute.OTHER,
    }
)

Q16_PAIN_POINTS: Final[Mapping[str, InstagramPainPoint]] = MappingProxyType(
    {
        "조회수가 안 나와요": InstagramPainPoint.LOW_REACH,
        "팔로워가 안 늘어요": InstagramPainPoint.LOW_FOLLOWER_GROWTH,
        "어떤 콘텐츠를 만들지 모르겠어요": InstagramPainPoint.IDEATION,
        "촬영이 어려워요": InstagramPainPoint.SHOOTING_DIFFICULTY,
        "편집이 어려워요": InstagramPainPoint.EDITING_DIFFICULTY,
        "꾸준히 올리기 어려워요": InstagramPainPoint.CONSISTENCY_DIFFICULTY,
        "구매로 연결되지 않아요": InstagramPainPoint.LOW_CONVERSION,
        "기타": InstagramPainPoint.OTHER,
    }
)

Q17_CURRENT_FORMATS: Final[Mapping[str, CurrentReelFormat]] = MappingProxyType(
    {
        "거의 안 올려요": CurrentReelFormat.RARELY_POST,
        "완성품 위주": CurrentReelFormat.FINISHED_PRODUCT,
        "제작 과정 위주": CurrentReelFormat.PROCESS,
        "사진/영상 혼합": CurrentReelFormat.PHOTO_VIDEO_MIX,
        "트렌드 릴스": CurrentReelFormat.TREND_REELS,
        "브이로그": CurrentReelFormat.VLOG,
    }
)

Q18_DISCLOSURE: Final[Mapping[str, CreatorDisclosure]] = MappingProxyType(
    {
        "네": CreatorDisclosure.YES,
        "아니요": CreatorDisclosure.NO,
        "얼굴만": CreatorDisclosure.FACE_ONLY,
        "목소리만": CreatorDisclosure.VOICE_ONLY,
    }
)

UI_OPTION_CATALOG: Final[Mapping[str, Mapping[str, StrEnum]]] = MappingProxyType(
    {
        "q6": Q6_PRODUCT_APPEALS,
        "q9": Q9_PURCHASE_MOTIVES,
        "q10": Q10_DESIRED_EMOTIONS,
        "q11": Q11_BRAND_ATTRIBUTES,
        "q16": Q16_PAIN_POINTS,
        "q17": Q17_CURRENT_FORMATS,
        "q18": Q18_DISCLOSURE,
    }
)

CATALOG_ENUM_TYPES: Final[Mapping[str, type[StrEnum]]] = MappingProxyType(
    {
        "q6": ProductAppeal,
        "q9": PurchaseMotive,
        "q10": DesiredEmotion,
        "q11": BrandAttribute,
        "q16": InstagramPainPoint,
        "q17": CurrentReelFormat,
        "q18": CreatorDisclosure,
    }
)

# Multi-select caps. Q18 is single-select and therefore absent.
MAX_SELECTIONS: Final[Mapping[str, int]] = MappingProxyType(
    {"q6": 3, "q9": 3, "q10": 3, "q11": 3, "q16": 3, "q17": 3}
)


# SSOT §5 code spellings → CONTRACT V1 wire codes. Documentation/translation aid only:
# the wire accepts CONTRACT V1 codes exclusively (section 8 enum contract).
SSOT_CODE_ALIASES: Final[Mapping[str, Mapping[str, str]]] = MappingProxyType(
    {
        "q6": MappingProxyType({"making_process": ProductAppeal.PROCESS.value}),
        "q9": MappingProxyType(
            {
                "special": PurchaseMotive.SPECIALNESS.value,
                "memory": PurchaseMotive.MEMORIES.value,
                "space_styling": PurchaseMotive.SPACE_DECOR.value,
                "unique_ownership": PurchaseMotive.SELF_EXPRESSION.value,
            }
        ),
        "q10": MappingProxyType({"being_moved": DesiredEmotion.MOVED.value}),
        "q11": MappingProxyType({"being_moved": BrandAttribute.MOVED.value}),
        "q16": MappingProxyType(
            {
                "low_views": InstagramPainPoint.LOW_REACH.value,
                "slow_follower_growth": InstagramPainPoint.LOW_FOLLOWER_GROWTH.value,
                "content_ideation": InstagramPainPoint.IDEATION.value,
                "filming": InstagramPainPoint.SHOOTING_DIFFICULTY.value,
                "editing": InstagramPainPoint.EDITING_DIFFICULTY.value,
                "posting_consistency": InstagramPainPoint.CONSISTENCY_DIFFICULTY.value,
                "low_purchase_conversion": InstagramPainPoint.LOW_CONVERSION.value,
            }
        ),
        "q17": MappingProxyType(
            {
                "rarely_posts": CurrentReelFormat.RARELY_POST.value,
                "making_process": CurrentReelFormat.PROCESS.value,
            }
        ),
        "q18": MappingProxyType(
            {
                "face_and_voice": CreatorDisclosure.YES.value,
                "neither": CreatorDisclosure.NO.value,
            }
        ),
    }
)


def catalog_as_json() -> dict[str, object]:
    """Serializable view for contracts/fixtures/ui_option_catalog.json (frontend adapter input)."""
    return {
        "contract_version": "1.0",
        "questions": {
            q: {
                "field": _FIELD_BY_QUESTION[q],
                "selection": "single" if q == "q18" else "multiple",
                "max_selection": MAX_SELECTIONS.get(q),
                "options": [{"label": label, "code": code.value} for label, code in table.items()],
            }
            for q, table in UI_OPTION_CATALOG.items()
        },
        "ssot_code_aliases": {q: dict(m) for q, m in SSOT_CODE_ALIASES.items()},
    }


_FIELD_BY_QUESTION: Final[Mapping[str, str]] = MappingProxyType(
    {
        "q6": "q6_product_appeals",
        "q9": "q9_purchase_motives",
        "q10": "q10_desired_emotions",
        "q11": "q11_brand_attributes",
        "q16": "q16_pain_points",
        "q17": "q17_current_formats",
        "q18": "q18_disclosure",
    }
)
