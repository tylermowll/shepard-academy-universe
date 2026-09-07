"""Bounded raster decoding and private opaque storage; no filename-derived paths."""

import os
import re
import secrets
import warnings
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif.as_plugin import register_heif_opener

from math_tutor import settings

MAX_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 24_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS
register_heif_opener()


def normalize(data: bytes) -> bytes:
    if len(data) > MAX_BYTES:
        raise ValueError("Image exceeds 8 MiB. Crop or resize it first.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                if (
                    image.format not in {"JPEG", "PNG", "WEBP", "HEIF"}
                    or image.width * image.height > MAX_PIXELS
                    or getattr(image, "n_frames", 1) != 1
                ):
                    raise ValueError(
                        "Use one JPEG, PNG, WebP, HEIC or HEIF image under 24 million pixels."
                    )
                image.load()
                oriented = ImageOps.exif_transpose(image).convert("RGB")
                oriented.thumbnail((2048, 2048))
                # Creating a fresh image drops EXIF, ICC profiles, comments and metadata.
                clean = Image.new("RGB", oriented.size, "white")
                clean.paste(oriented)
                output = BytesIO()
                clean.save(output, "PNG")
                return output.getvalue()
    except (
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise ValueError(
            "Cannot decode this photograph. Retake it or convert it to JPEG/PNG."
        ) from None


def object_root() -> Path:
    root = settings.database_path().parent / "objects"
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.chmod(0o700)
    return root


def object_path(key: str) -> Path:
    if re.fullmatch(r"[a-f0-9]{64}", key) is None:
        raise ValueError("Invalid storage key.")
    return object_root() / key


def store_image(data: bytes) -> str:
    key = secrets.token_hex(32)
    descriptor = os.open(object_path(key), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        output.write(data)
    return key


def read_image(key: str) -> bytes:
    return object_path(key).read_bytes()


def delete_image(key: str) -> None:
    object_path(key).unlink(missing_ok=True)
