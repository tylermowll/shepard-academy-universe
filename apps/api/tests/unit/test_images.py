"""Synthetic raster decoder gates including HEIF, orientation and metadata removal."""

from io import BytesIO
from random import Random

import pytest
from PIL import Image, PngImagePlugin
from pillow_heif.heif import from_pillow

from math_tutor.adapters.images import MAX_NORMALIZED_BYTES, normalize


@pytest.mark.parametrize("format", ["JPEG", "PNG", "WEBP"])
def test_normalize_bounded_raster(format: str) -> None:
    source = BytesIO()
    image = Image.new("RGB", (2200, 100), "white")
    image.save(source, format)
    with Image.open(BytesIO(normalize(source.getvalue()))) as result:
        assert result.format == "JPEG" and result.size == (2048, 93)
        assert "exif" not in result.info and "icc_profile" not in result.info


def test_heif_round_trip_and_metadata_stripping() -> None:
    source = BytesIO()
    from_pillow(Image.new("RGB", (64, 32), "white")).save(source)
    with Image.open(BytesIO(normalize(source.getvalue()))) as image:
        assert image.size == (64, 32) and image.format == "JPEG"
    png = BytesIO()
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("private-note", "synthetic metadata")
    Image.new("RGB", (20, 20), "white").save(png, "PNG", pnginfo=metadata)
    assert b"synthetic metadata" not in normalize(png.getvalue())


def test_noisy_jpeg_does_not_expand_into_an_oversized_provider_request() -> None:
    source = BytesIO()
    pixels = Random(7).randbytes(2048 * 2048 * 3)
    Image.frombytes("RGB", (2048, 2048), pixels).save(source, "JPEG", quality=92)
    assert len(source.getvalue()) < 8 * 1024 * 1024
    normalized = normalize(source.getvalue())
    assert len(normalized) <= MAX_NORMALIZED_BYTES
    with Image.open(BytesIO(normalized)) as image:
        assert image.format == "JPEG" and image.size == (2048, 2048)


def test_24_megapixel_class_phone_photo_is_not_rejected_by_rounded_label() -> None:
    source = BytesIO()
    Image.new("RGB", (5712, 4284), "white").save(source, "JPEG")
    with Image.open(BytesIO(normalize(source.getvalue()))) as result:
        assert result.size == (2048, 1536)
        assert "exif" not in result.info and "icc_profile" not in result.info


def test_valid_gif_is_rejected_not_only_corrupt_gif_headers() -> None:
    source = BytesIO()
    Image.new("RGB", (64, 32), "white").save(source, "GIF")
    with pytest.raises(ValueError, match="Use one JPEG"):
        normalize(source.getvalue())


@pytest.mark.parametrize(
    "data",
    [
        b"not an image",
        b'<svg xmlns="http://www.w3.org/2000/svg"></svg>',
        b"GIF89a",
        b"x" * (8 * 1024 * 1024 + 1),
    ],
)
def test_rejects_corrupt_unsupported_and_large_inputs(data: bytes) -> None:
    with pytest.raises(ValueError):
        normalize(data)


def test_orientation_and_pixel_limits() -> None:
    photo = BytesIO()
    image = Image.new("RGB", (30, 20), "white")
    exif = image.getexif()
    exif[274] = 6
    image.save(photo, "JPEG", exif=exif)
    with Image.open(BytesIO(normalize(photo.getvalue()))) as decoded:
        assert decoded.size == (20, 30)
    photo = BytesIO()
    Image.new("1", (5001, 5000)).save(photo, "PNG")
    with pytest.raises(ValueError):
        normalize(photo.getvalue())
