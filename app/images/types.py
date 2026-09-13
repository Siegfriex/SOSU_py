"""Image ingress limits and the normalized image value object."""

from __future__ import annotations

from dataclasses import dataclass

ACCEPTED_IMAGE_TYPES: frozenset[str] = frozenset({"image/jpeg", "image/png", "image/webp"})

PRODUCT_IMAGE_MAX_BYTES = 1_250_000  # 1.25 MB ingress
PRODUCT_LONG_EDGE = 1600
PRODUCT_JPEG_QUALITY = 85
PRODUCT_TARGET_BYTES = 700_000

INSIGHT_IMAGE_COUNT = 3
INSIGHT_IMAGE_MAX_BYTES = 900_000  # each
INSIGHT_IMAGES_MAX_TOTAL_BYTES = 2_700_000  # combined
INSIGHT_LONG_EDGE = 2000
INSIGHT_JPEG_QUALITY = 90
INSIGHT_TARGET_BYTES = 900_000


@dataclass(frozen=True, slots=True)
class NormalizedImage:
    """Always JPEG/RGB, EXIF-transposed, aspect ratio preserved. Lives in memory only."""

    data: bytes
    width: int
    height: int
    mime_type: str = "image/jpeg"

    @property
    def size_bytes(self) -> int:
        return len(self.data)
