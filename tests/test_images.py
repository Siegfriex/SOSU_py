"""H: image MIME / size / count tests. I: resize / compression tests."""

from __future__ import annotations

from io import BytesIO

import pytest
from app.contracts.envelope import ErrorCode
from app.domain.errors import SosuError
from app.images.normalize import (
    normalize_insight_screenshot,
    normalize_product_image,
    validate_insight_batch,
    validate_upload,
)
from app.images.types import (
    INSIGHT_IMAGE_MAX_BYTES,
    INSIGHT_IMAGES_MAX_TOTAL_BYTES,
    INSIGHT_TARGET_BYTES,
    PRODUCT_IMAGE_MAX_BYTES,
    PRODUCT_TARGET_BYTES,
)
from PIL import Image

# ------------------------------------------------------------------ helpers


def _encode(image: Image.Image, fmt: str, **kwargs: object) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format=fmt, **kwargs)
    return buffer.getvalue()


def _solid(
    size: tuple[int, int], color: tuple[int, ...] = (200, 40, 40), mode: str = "RGB"
) -> Image.Image:
    return Image.new(mode, size, color)


def _noise(size: tuple[int, int]) -> Image.Image:
    import random

    rng = random.Random(1234)
    image = Image.new("RGB", size)
    image.putdata(
        [
            (rng.randrange(256), rng.randrange(256), rng.randrange(256))
            for _ in range(size[0] * size[1])
        ]
    )
    return image


def _open(data: bytes) -> Image.Image:
    return Image.open(BytesIO(data))


# ------------------------------------------------------------------ H: MIME


@pytest.mark.parametrize(
    "mime", ["image/jpeg", "image/png", "image/webp", "IMAGE/JPEG", "image/png; charset=binary"]
)
def test_validate_upload_accepts_contract_types(mime: str) -> None:
    validate_upload(mime, 10, max_bytes=100)


@pytest.mark.parametrize(
    "mime",
    ["image/gif", "image/jpg", "image/heic", "application/octet-stream", "text/plain", "", None],
)
def test_validate_upload_rejects_non_contract_types(mime: str | None) -> None:
    with pytest.raises(SosuError) as exc_info:
        validate_upload(mime, 10, max_bytes=100)
    assert exc_info.value.code == ErrorCode.INVALID_IMAGE_TYPE
    assert exc_info.value.http_status == 415


# ------------------------------------------------------------------ H: size


def test_validate_upload_size_boundary() -> None:
    validate_upload("image/jpeg", PRODUCT_IMAGE_MAX_BYTES, max_bytes=PRODUCT_IMAGE_MAX_BYTES)
    with pytest.raises(SosuError) as exc_info:
        validate_upload(
            "image/jpeg", PRODUCT_IMAGE_MAX_BYTES + 1, max_bytes=PRODUCT_IMAGE_MAX_BYTES
        )
    err = exc_info.value
    assert err.code == ErrorCode.IMAGE_TOO_LARGE
    assert err.http_status == 413
    assert err.details == [
        {"limit_bytes": PRODUCT_IMAGE_MAX_BYTES, "actual_bytes": PRODUCT_IMAGE_MAX_BYTES + 1}
    ]


def test_validate_upload_checks_type_before_size() -> None:
    with pytest.raises(SosuError) as exc_info:
        validate_upload("image/gif", 10**9, max_bytes=1)
    assert exc_info.value.code == ErrorCode.INVALID_IMAGE_TYPE


# ------------------------------------------------------------------ H: count / batch


@pytest.mark.parametrize("count", [0, 1, 2, 4])
def test_validate_insight_batch_rejects_wrong_count(count: int) -> None:
    with pytest.raises(SosuError) as exc_info:
        validate_insight_batch([1000] * count)
    assert exc_info.value.code == ErrorCode.INVALID_IMAGE_COUNT
    assert exc_info.value.details == [{"expected": 3, "actual": count}]


def test_validate_insight_batch_accepts_three_at_limits() -> None:
    validate_insight_batch([INSIGHT_IMAGE_MAX_BYTES] * 3)
    assert INSIGHT_IMAGE_MAX_BYTES * 3 == INSIGHT_IMAGES_MAX_TOTAL_BYTES


def test_validate_insight_batch_rejects_per_file_limit() -> None:
    with pytest.raises(SosuError) as exc_info:
        validate_insight_batch([1000, INSIGHT_IMAGE_MAX_BYTES + 1, 1000])
    err = exc_info.value
    assert err.code == ErrorCode.IMAGE_TOO_LARGE
    assert err.details[0]["index"] == 1


def test_validate_insight_batch_rejects_combined_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    # Per-file limit ×3 equals the combined limit, so lower the combined cap to isolate the branch.
    import app.images.normalize as mod

    monkeypatch.setattr(mod, "INSIGHT_IMAGES_MAX_TOTAL_BYTES", 2_000_000)
    with pytest.raises(SosuError) as exc_info:
        validate_insight_batch([800_000, 800_000, 800_000])
    err = exc_info.value
    assert err.code == ErrorCode.IMAGE_TOO_LARGE
    assert err.details == [{"limit_bytes": 2_000_000, "actual_bytes": 2_400_000}]


# ------------------------------------------------------------------ H: decode


def test_decode_failure_is_invalid_image_type() -> None:
    with pytest.raises(SosuError) as exc_info:
        normalize_product_image(b"definitely not an image")
    assert exc_info.value.code == ErrorCode.INVALID_IMAGE_TYPE
    assert "decoded" in exc_info.value.message


def test_gif_bytes_rejected_even_with_valid_declared_mime() -> None:
    gif = _encode(_solid((10, 10)), "GIF")
    with pytest.raises(SosuError) as exc_info:
        normalize_product_image(gif)
    assert exc_info.value.code == ErrorCode.INVALID_IMAGE_TYPE
    assert exc_info.value.details[0]["detected_format"] == "GIF"


def test_truncated_jpeg_rejected() -> None:
    jpeg = _encode(_noise((400, 400)), "JPEG", quality=90)
    with pytest.raises(SosuError) as exc_info:
        normalize_product_image(jpeg[: len(jpeg) // 2])
    assert exc_info.value.code == ErrorCode.INVALID_IMAGE_TYPE


# ------------------------------------------------------------------ I: normalization


def test_output_is_rgb_jpeg() -> None:
    out = normalize_product_image(_encode(_solid((100, 80)), "PNG"))
    image = _open(out.data)
    assert image.format == "JPEG"
    assert image.mode == "RGB"
    assert out.mime_type == "image/jpeg"
    assert (out.width, out.height) == (100, 80) == image.size
    assert out.size_bytes == len(out.data)


def test_rgba_png_flattened_to_rgb() -> None:
    rgba = _solid((60, 60), (0, 0, 255, 0), mode="RGBA")  # fully transparent blue
    out = normalize_product_image(_encode(rgba, "PNG"))
    image = _open(out.data)
    assert image.mode == "RGB"
    r, g, b = image.getpixel((30, 30))  # type: ignore[misc]
    assert r > 240 and g > 240 and b > 240  # flattened onto white


def test_webp_input_accepted() -> None:
    out = normalize_product_image(_encode(_solid((120, 90)), "WEBP"))
    assert _open(out.data).format == "JPEG"
    assert (out.width, out.height) == (120, 90)


def test_product_downscale_preserves_aspect_ratio() -> None:
    out = normalize_product_image(_encode(_solid((4000, 1000)), "JPEG"))
    assert (out.width, out.height) == (1600, 400)
    assert _open(out.data).size == (1600, 400)


def test_insight_downscale_preserves_aspect_ratio() -> None:
    out = normalize_insight_screenshot(_encode(_solid((4000, 1000)), "JPEG"))
    assert (out.width, out.height) == (2000, 500)


def test_portrait_long_edge_is_height() -> None:
    out = normalize_product_image(_encode(_solid((1000, 3200)), "JPEG"))
    assert (out.width, out.height) == (500, 1600)


def test_small_image_not_upscaled() -> None:
    out = normalize_product_image(_encode(_solid((300, 200)), "JPEG"))
    assert (out.width, out.height) == (300, 200)
    out2 = normalize_insight_screenshot(_encode(_solid((1080, 1920)), "PNG"))
    assert (out2.width, out2.height) == (1080, 1920)


def test_exif_orientation_applied() -> None:
    # 300 wide × 100 tall, left half red, right half blue; orientation 6 = rotate 90° CW on display.
    image = Image.new("RGB", (300, 100), (255, 0, 0))
    image.paste((0, 0, 255), (150, 0, 300, 100))
    exif = image.getexif()
    exif[0x0112] = 6
    raw = _encode(image, "JPEG", exif=exif.tobytes(), quality=95)

    out = normalize_product_image(raw)
    assert (out.width, out.height) == (100, 300)
    result = _open(out.data)
    top = result.getpixel((50, 30))
    bottom = result.getpixel((50, 270))
    assert top[0] > 200 and top[2] < 60  # type: ignore[index]  # red now at top
    assert bottom[2] > 200 and bottom[0] < 60  # type: ignore[index]  # blue now at bottom


def test_exif_metadata_stripped() -> None:
    image = _solid((50, 50))
    exif = image.getexif()
    exif[0x0112] = 1
    exif[0x010F] = "SOSU-TEST-MAKE"
    raw = _encode(image, "JPEG", exif=exif.tobytes())
    out = normalize_product_image(raw)
    assert dict(_open(out.data).getexif()) == {}


def test_large_noisy_product_image_compressed_toward_target() -> None:
    raw = _encode(_noise((2400, 2400)), "PNG")
    assert len(raw) > PRODUCT_TARGET_BYTES
    out = normalize_product_image(raw)
    assert (out.width, out.height) == (1600, 1600)
    assert out.size_bytes < len(raw)
    # Quality steps down to the floor (60); pure noise may miss the target but must shrink.
    baseline = len(_encode(_noise((1600, 1600)), "JPEG", quality=85, optimize=True))
    assert out.size_bytes < baseline


def test_large_noisy_insight_screenshot_not_downscaled_below_policy() -> None:
    raw = _encode(_noise((2000, 2000)), "PNG")
    out = normalize_insight_screenshot(raw)
    # Insight stays at the long-edge limit even if over target (legibility first).
    assert (out.width, out.height) == (2000, 2000)
    assert out.size_bytes < len(raw)


def test_smooth_image_stays_within_target_at_policy_quality() -> None:
    out = normalize_insight_screenshot(_encode(_solid((2000, 1200)), "PNG"))
    assert out.size_bytes <= INSIGHT_TARGET_BYTES
