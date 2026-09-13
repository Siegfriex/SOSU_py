"""Pillow normalization for uploaded images. Everything stays in memory (BytesIO).

Contract (CONTRACT V1 §9):
  validate_upload(content_type, size_bytes, *, max_bytes) -> None   raises SosuError
  validate_insight_batch(sizes) -> None                              raises SosuError
  normalize_product_image(raw: bytes) -> NormalizedImage
  normalize_insight_screenshot(raw: bytes) -> NormalizedImage
"""

from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

from app.contracts.envelope import ErrorCode
from app.domain.errors import SosuError
from app.images.types import (
    ACCEPTED_IMAGE_TYPES,
    INSIGHT_IMAGE_COUNT,
    INSIGHT_IMAGE_MAX_BYTES,
    INSIGHT_IMAGES_MAX_TOTAL_BYTES,
    INSIGHT_JPEG_QUALITY,
    INSIGHT_LONG_EDGE,
    INSIGHT_TARGET_BYTES,
    PRODUCT_JPEG_QUALITY,
    PRODUCT_LONG_EDGE,
    PRODUCT_TARGET_BYTES,
    NormalizedImage,
)

__all__ = [
    "normalize_insight_screenshot",
    "normalize_product_image",
    "validate_insight_batch",
    "validate_upload",
]

# Pillow format names that correspond to the accepted MIME types.
_ACCEPTED_PIL_FORMATS: frozenset[str] = frozenset({"JPEG", "PNG", "WEBP"})

_QUALITY_STEP = 5
_PRODUCT_QUALITY_FLOOR = 60
_INSIGHT_QUALITY_FLOOR = 75  # screenshots must stay legible


def _canonical_mime(content_type: str | None) -> str | None:
    if content_type is None:
        return None
    return content_type.split(";", 1)[0].strip().lower() or None


def validate_upload(content_type: str | None, size_bytes: int, *, max_bytes: int) -> None:
    mime = _canonical_mime(content_type)
    if mime not in ACCEPTED_IMAGE_TYPES:
        raise SosuError(
            ErrorCode.INVALID_IMAGE_TYPE,
            "unsupported image type",
            details=[{"content_type": content_type, "accepted": sorted(ACCEPTED_IMAGE_TYPES)}],
        )
    if size_bytes > max_bytes:
        raise SosuError(
            ErrorCode.IMAGE_TOO_LARGE,
            "image exceeds size limit",
            details=[{"limit_bytes": max_bytes, "actual_bytes": size_bytes}],
        )


def validate_insight_batch(sizes: list[int]) -> None:
    if len(sizes) != INSIGHT_IMAGE_COUNT:
        raise SosuError(
            ErrorCode.INVALID_IMAGE_COUNT,
            f"exactly {INSIGHT_IMAGE_COUNT} insight screenshots are required",
            details=[{"expected": INSIGHT_IMAGE_COUNT, "actual": len(sizes)}],
        )
    for index, size in enumerate(sizes):
        if size > INSIGHT_IMAGE_MAX_BYTES:
            raise SosuError(
                ErrorCode.IMAGE_TOO_LARGE,
                "insight screenshot exceeds per-file size limit",
                details=[
                    {"index": index, "limit_bytes": INSIGHT_IMAGE_MAX_BYTES, "actual_bytes": size}
                ],
            )
    total = sum(sizes)
    if total > INSIGHT_IMAGES_MAX_TOTAL_BYTES:
        raise SosuError(
            ErrorCode.IMAGE_TOO_LARGE,
            "insight screenshots exceed combined size limit",
            details=[{"limit_bytes": INSIGHT_IMAGES_MAX_TOTAL_BYTES, "actual_bytes": total}],
        )


def _decode(raw: bytes) -> Image.Image:
    try:
        image = Image.open(BytesIO(raw))
        image_format = image.format
        image.load()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise SosuError(ErrorCode.INVALID_IMAGE_TYPE, "image could not be decoded") from exc
    if image_format not in _ACCEPTED_PIL_FORMATS:
        raise SosuError(
            ErrorCode.INVALID_IMAGE_TYPE,
            "unsupported image format",
            details=[{"detected_format": image_format, "accepted": sorted(_ACCEPTED_PIL_FORMATS)}],
        )
    return image


def _to_rgb(image: Image.Image) -> Image.Image:
    """Convert to RGB, flattening any alpha channel onto white."""
    if image.mode == "RGB":
        return image
    if image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    return image.convert("RGB")


def _downscale(image: Image.Image, long_edge: int) -> Image.Image:
    width, height = image.size
    longest = max(width, height)
    if longest <= long_edge:
        return image
    scale = long_edge / longest
    new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
    return image.resize(new_size, Image.Resampling.LANCZOS)


def _encode_jpeg(image: Image.Image, quality: int) -> bytes:
    buffer = BytesIO()
    # No exif / icc_profile passed through → metadata stripped.
    image.save(buffer, format="JPEG", quality=quality, optimize=True)
    return buffer.getvalue()


def _normalize(
    raw: bytes,
    *,
    long_edge: int,
    quality: int,
    quality_floor: int,
    target_bytes: int,
) -> NormalizedImage:
    decoded = _decode(raw)
    transposed = ImageOps.exif_transpose(decoded) or decoded
    image = _downscale(_to_rgb(transposed), long_edge)

    data = _encode_jpeg(image, quality)
    while len(data) > target_bytes and quality - _QUALITY_STEP >= quality_floor:
        quality -= _QUALITY_STEP
        data = _encode_jpeg(image, quality)

    width, height = image.size
    return NormalizedImage(data=data, width=width, height=height)


def normalize_product_image(raw: bytes) -> NormalizedImage:
    return _normalize(
        raw,
        long_edge=PRODUCT_LONG_EDGE,
        quality=PRODUCT_JPEG_QUALITY,
        quality_floor=_PRODUCT_QUALITY_FLOOR,
        target_bytes=PRODUCT_TARGET_BYTES,
    )


def normalize_insight_screenshot(raw: bytes) -> NormalizedImage:
    return _normalize(
        raw,
        long_edge=INSIGHT_LONG_EDGE,
        quality=INSIGHT_JPEG_QUALITY,
        quality_floor=_INSIGHT_QUALITY_FLOOR,
        target_bytes=INSIGHT_TARGET_BYTES,
    )
