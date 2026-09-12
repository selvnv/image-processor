"""Pure image-processing core.

This module intentionally knows nothing about HTTP, multipart or filenames.
Endpoints parse transport concerns and delegate to :func:`process_image`, which
is the single entry point reused by both single-file and batch flows.
"""

import io
from dataclasses import dataclass

from PIL import Image, ImageOps

from .schemas import ProcessOptions

# Reject images above this many pixels before decoding their full pixel data.
# This guards against decompression bombs.
MAX_PIXELS = 40_000_000

SUPPORTED_INPUT_FORMATS = {"JPEG", "PNG"}

_OUTPUT_EXTENSIONS = {"jpeg": "jpg", "webp": "webp", "png": "png"}
_OUTPUT_MEDIA_TYPES = {"jpeg": "image/jpeg", "webp": "image/webp", "png": "image/png"}


class ImageProcessingError(Exception):
    """Base class for expected, user-facing processing failures."""


class InvalidImageError(ImageProcessingError):
    """Uploaded bytes could not be decoded as an image."""


class UnsupportedFormatError(ImageProcessingError):
    """Input image format is outside the supported set."""


class ImageTooLargeError(ImageProcessingError):
    """Image exceeds the pixel budget."""


@dataclass(frozen=True)
class ProcessedImage:
    """Result of transforming a single image."""

    data: bytes
    format: str

    @property
    def media_type(self) -> str:
        return _OUTPUT_MEDIA_TYPES[self.format]

    @property
    def extension(self) -> str:
        return _OUTPUT_EXTENSIONS[self.format]


def _resolve_format(input_format: str, requested: str) -> str:
    """Resolve the concrete output format.

    ``requested == "original"`` keeps the input's format (JPEG -> jpeg,
    PNG -> png). Otherwise the requested format is used as-is.
    """
    if requested == "original":
        return "jpeg" if input_format == "JPEG" else "png"
    return requested


def decode_image(source: bytes) -> tuple[Image.Image, str]:
    """Decode, validate, load and exif-transpose ``source``.

    Returns ``(image, input_format)`` where ``input_format`` is the Pillow
    format name ("JPEG"/"PNG") captured before transforms may lose it.
    """
    try:
        image = Image.open(io.BytesIO(source))
    except Exception as exc:  # any decode failure means "not a usable image"
        raise InvalidImageError("could not decode the uploaded image") from exc

    if image.format not in SUPPORTED_INPUT_FORMATS:
        raise UnsupportedFormatError(
            f"unsupported input format '{image.format}'; expected JPEG or PNG"
        )

    input_format = image.format

    if image.width * image.height > MAX_PIXELS:
        raise ImageTooLargeError(f"image is too large ({image.width}x{image.height})")

    image.load()  # force decode; surfaces truncated/corrupt files
    image = ImageOps.exif_transpose(image)
    return image, input_format


def encode_image(
    image: Image.Image, input_format: str, options: ProcessOptions
) -> ProcessedImage:
    """Apply geometry and encode a decoded image according to ``options``."""
    output_format = _resolve_format(input_format, options.format)

    image = _apply_geometry(image, options)
    image = _prepare_for_output(image, output_format)

    buffer = io.BytesIO()
    if output_format == "png":
        image.save(buffer, format="PNG")
    else:
        image.save(buffer, format=output_format.upper(), quality=options.quality)
    return ProcessedImage(data=buffer.getvalue(), format=output_format)


def process_image(source: bytes, options: ProcessOptions) -> ProcessedImage:
    """Transform one image according to ``options``."""
    image, input_format = decode_image(source)
    return encode_image(image, input_format, options)


def _apply_geometry(image: Image.Image, options: ProcessOptions) -> Image.Image:
    if options.mode == "fit":
        return _fit(image, options)
    if options.mode == "cover":
        return _cover(image, options)
    if options.mode == "crop":
        return _crop(image, options)
    raise ValueError(f"unknown mode: {options.mode}")


def _fit(image: Image.Image, options: ProcessOptions) -> Image.Image:
    # Fit within width x height, preserving aspect ratio, never upscaling.
    target_w = options.width if options.width is not None else image.width
    target_h = options.height if options.height is not None else image.height
    result = image.copy()
    result.thumbnail((target_w, target_h), Image.Resampling.LANCZOS)
    return result


def _cover(image: Image.Image, options: ProcessOptions) -> Image.Image:
    # Resize to cover the box, then center-crop to the exact dimensions.
    return ImageOps.fit(
        image,
        (options.width, options.height),
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.5),
    )


def _crop(image: Image.Image, options: ProcessOptions) -> Image.Image:
    # Center crop without resizing. Clamp to the source size so we never pad.
    width = min(options.width, image.width)
    height = min(options.height, image.height)
    left = (image.width - width) // 2
    top = (image.height - height) // 2
    return image.crop((left, top, left + width, top + height))


def _has_alpha(image: Image.Image) -> bool:
    return image.mode in {"RGBA", "LA"} or (
        image.mode == "P" and "transparency" in image.info
    )


def _prepare_for_output(image: Image.Image, fmt: str) -> Image.Image:
    if fmt == "jpeg":
        if _has_alpha(image):
            return _flatten_alpha(image)
        return image.convert("RGB")

    # WebP and PNG support alpha.
    if _has_alpha(image):
        return image.convert("RGBA")
    return image.convert("RGB")


def _flatten_alpha(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    background = Image.new("RGB", rgba.size, (255, 255, 255))
    background.paste(rgba, mask=rgba.getchannel("A"))
    return background
