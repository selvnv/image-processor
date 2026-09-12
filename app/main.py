"""HTTP transport layer for the image processor.

Endpoints stay thin: they parse form data and delegate all image work to
``app.processing``. The batch endpoint reuses the exact same core function and
option parser as the single-file endpoint.
"""

import io
import json
import re
import zipfile
from pathlib import Path
from typing import Annotated, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from .cache import image_cache, result_cache, result_key, store_image
from .processing import (
    ImageProcessingError,
    ImageTooLargeError,
    InvalidImageError,
    ProcessedImage,
    UnsupportedFormatError,
    decode_image,
    encode_image,
    process_image,
)
from .schemas import ProcessOptions

MAX_UPLOAD_BYTES = 20 * 1024 * 1024

app = FastAPI(title="Image Processor", version="0.1.0")


def parse_options(
    width: Annotated[Optional[int], Form()] = None,
    height: Annotated[Optional[int], Form()] = None,
    mode: Annotated[Optional[str], Form()] = None,
    format: Annotated[Optional[str], Form()] = None,
    quality: Annotated[Optional[int], Form()] = None,
) -> ProcessOptions:
    """Parse shared form fields into :class:`ProcessOptions`."""
    provided = {
        "width": width,
        "height": height,
        "mode": mode,
        "format": format,
        "quality": quality,
    }
    return ProcessOptions(**{k: v for k, v in provided.items() if v is not None})


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/v1/process")
async def process_single(
    file: Annotated[UploadFile, File(description="Source image (JPEG/PNG)")],
    options: Annotated[ProcessOptions, Depends(parse_options)],
) -> Response:
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="file exceeds the size limit")

    result = await run_in_threadpool(process_image, data, options)

    filename = _output_filename(file.filename, result)
    return Response(
        content=result.data,
        media_type=result.media_type,
        headers={"Content-Disposition": _content_disposition(filename)},
    )


@app.post("/v1/upload")
async def upload_image(
    file: Annotated[UploadFile, File(description="Source image (JPEG/PNG)")],
) -> dict:
    """Upload and cache a decoded image, returning its id."""
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="file exceeds the size limit")

    image, input_format = await run_in_threadpool(decode_image, data)
    file_id = store_image(image, input_format)
    return {"file_id": file_id}


@app.post("/v1/size")
async def image_size(
    file_id: Annotated[str, Form()],
    options: Annotated[ProcessOptions, Depends(parse_options)],
) -> dict:
    """Return the exact compressed size (bytes) for the given parameters."""
    entry = image_cache.get(file_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="file_id not found or expired")

    image, input_format = entry

    key = result_key(file_id, options)
    size = result_cache.get(key)
    if size is None:
        result = await run_in_threadpool(encode_image, image, input_format, options)
        size = len(result.data)
        result_cache.put(key, size)

    return {"size": size}


@app.post("/v1/process/batch")
async def process_batch(
    files: Annotated[list[UploadFile], File(description="Source images (JPEG/PNG)")],
    options: Annotated[ProcessOptions, Depends(parse_options)],
) -> Response:
    results: list[tuple[str, ProcessedImage]] = []
    errors: list[dict] = []

    for file in files:
        original_name = file.filename or "image"
        data = await file.read()

        if len(data) > MAX_UPLOAD_BYTES:
            errors.append(
                {"filename": original_name, "error": "file exceeds the size limit"}
            )
            continue

        try:
            result = await run_in_threadpool(process_image, data, options)
        except ImageProcessingError as exc:
            errors.append({"filename": original_name, "error": str(exc)})
            continue

        results.append((original_name, result))

    if not results:
        raise HTTPException(
            status_code=422,
            detail={"message": "no files could be processed", "errors": errors},
        )

    archive = _build_zip(results, errors)
    return Response(
        content=archive,
        media_type="application/zip",
        headers={"Content-Disposition": _content_disposition("results.zip")},
    )


@app.exception_handler(ImageProcessingError)
async def handle_processing_error(request, exc: ImageProcessingError) -> JSONResponse:
    if isinstance(exc, ImageTooLargeError):
        status = 413
    elif isinstance(exc, InvalidImageError):
        status = 400
    elif isinstance(exc, UnsupportedFormatError):
        status = 415
    else:
        status = 500
    return JSONResponse(status_code=status, content={"detail": str(exc)})


_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def _output_filename(original: Optional[str], result: ProcessedImage) -> str:
    stem = Path(original).stem if original else "image"
    stem = _SAFE_NAME.sub("_", stem).strip("._") or "image"
    return f"{stem}.{result.extension}"


def _unique_name(filename: str, used: set[str]) -> str:
    if filename not in used:
        return filename
    stem, ext = filename.rsplit(".", 1)
    counter = 2
    while f"{stem}_{counter}.{ext}" in used:
        counter += 1
    return f"{stem}_{counter}.{ext}"


def _content_disposition(filename: str) -> str:
    # Filenames are sanitized to ASCII, so a plain header value is safe.
    return f'attachment; filename="{filename}"'


def _build_zip(
    results: list[tuple[str, ProcessedImage]], errors: list[dict]
) -> bytes:
    buffer = io.BytesIO()
    used: set[str] = set()
    manifest = {"files": [], "errors": errors}

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for original_name, result in results:
            filename = _unique_name(_output_filename(original_name, result), used)
            used.add(filename)
            archive.writestr(filename, result.data)
            manifest["files"].append({"input": original_name, "output": filename})

        archive.writestr("manifest.json", json.dumps(manifest, indent=2))

    return buffer.getvalue()
