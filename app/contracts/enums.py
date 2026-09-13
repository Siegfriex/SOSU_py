"""Stable categorical codes shared with the frontend. Values are the wire format."""

from __future__ import annotations

from enum import StrEnum


class ProductAppeal(StrEnum):
    """Q6 — what makes the product appealing (max 3)."""

    DESIGN = "design"
    COLOR = "color"
    DETAIL = "detail"
    TEXTURE = "texture"
    MATERIAL = "material"
    PROCESS = "process"
    STORY = "story"
    RARITY = "rarity"
    OTHER = "other"


class PurchaseMotive(StrEnum):
    """Q9 — why customers buy (max 3)."""

    AESTHETIC = "aesthetic"
    SPECIALNESS = "specialness"
    SELF_REWARD = "self_reward"
    GIFT = "gift"
    MEMORIES = "memories"
    SPACE_DECOR = "space_decor"
    SELF_EXPRESSION = "self_expression"


class DesiredEmotion(StrEnum):
    """Q10 — emotion the brand wants customers to feel (max 3)."""

    EXCITEMENT = "excitement"
    HAPPINESS = "happiness"
    WARMTH = "warmth"
    HEALING = "healing"
    FUN = "fun"
    SPECIALNESS = "specialness"
    MOVED = "moved"
    COMFORT = "comfort"
    OTHER = "other"


class BrandAttribute(StrEnum):
    """Q11 — attribute the brand wants to be perceived as (max 3).

    Same string vocabulary as DesiredEmotion but a distinct semantic namespace:
    Q10 is what the *customer feels*, Q11 is what the *brand is*. Never merge.
    """

    EXCITEMENT = "excitement"
    HAPPINESS = "happiness"
    WARMTH = "warmth"
    HEALING = "healing"
    FUN = "fun"
    SPECIALNESS = "specialness"
    MOVED = "moved"
    COMFORT = "comfort"
    OTHER = "other"


class InstagramPainPoint(StrEnum):
    """Q16 — current Instagram difficulty (max 3)."""

    LOW_REACH = "low_reach"
    LOW_FOLLOWER_GROWTH = "low_follower_growth"
    IDEATION = "ideation"
    SHOOTING_DIFFICULTY = "shooting_difficulty"
    EDITING_DIFFICULTY = "editing_difficulty"
    CONSISTENCY_DIFFICULTY = "consistency_difficulty"
    LOW_CONVERSION = "low_conversion"
    OTHER = "other"


class CurrentReelFormat(StrEnum):
    """Q17 — formats currently being posted (max 3)."""

    RARELY_POST = "rarely_post"
    FINISHED_PRODUCT = "finished_product"
    PROCESS = "process"
    PHOTO_VIDEO_MIX = "photo_video_mix"
    TREND_REELS = "trend_reels"
    VLOG = "vlog"


class CreatorDisclosure(StrEnum):
    """Q18 — whether the creator can appear (face) / narrate (voice). Single value."""

    YES = "yes"
    NO = "no"
    FACE_ONLY = "face_only"
    VOICE_ONLY = "voice_only"
