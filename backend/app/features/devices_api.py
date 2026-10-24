"""Optional device photo per camera, shown in the Control Center "Device details" panel.

A rough reference photo of the installed camera helps an operator recognise the device on site.
Files live in `<data dir>/device-images/camera-<id>.jpg|png` (git-ignored, like evidence). Uploads are
decoded, EXIF-rotated, shrunk to at most 1280 px and re-encoded, which also strips EXIF/GPS metadata.
No database column: `camera_dict()` reports `device_image_version` (file mtime in ms) or null, and the
browser adds it to the image URL so a replaced photo is never served from cache.
"""
import os
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse

from ..core import DATA
from ..db import Camera, Session

DEVICE_IMAGE_DIR = (DATA / "device-images").resolve()
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 20_000_000          # same decompression-bomb limit as floor plans
MAX_EDGE = 1280                  # a reference photo, not evidence: keep files small
EXTENSIONS = ("jpg", "png")


def device_image_path(camera_id: int) -> Path | None:
    for extension in EXTENSIONS:
        path = DEVICE_IMAGE_DIR / f"camera-{int(camera_id)}.{extension}"
        if path.is_file():
            return path
    return None


def device_image_version(camera_id: int) -> int | None:
    """Cache-busting version for camera_dict(); None when the camera has no photo."""
    path = device_image_path(camera_id)
    return path.stat().st_mtime_ns // 1_000_000 if path else None


def _normalise(raw: bytes) -> tuple[bytes, str]:
    """Decode a PNG/JPEG upload and return re-encoded bytes + extension, or raise 413/415."""
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        extension = "png"
    elif raw.startswith(b"\xff\xd8\xff"):
        extension = "jpg"
    else:
        raise HTTPException(415, "Device photo must be a PNG or JPEG image")
    from PIL import Image, ImageOps, UnidentifiedImageError
    try:
        with Image.open(BytesIO(raw)) as image:
            if image.format not in ("PNG", "JPEG"):
                raise HTTPException(415, "Device photo must be a PNG or JPEG image")
            width, height = image.size
            if width < 1 or height < 1 or width * height > MAX_PIXELS:
                raise HTTPException(413, "Device photo exceeds the 20 megapixel limit")
            image.verify()
        with Image.open(BytesIO(raw)) as image:
            image = ImageOps.exif_transpose(image)          # phone photos: honour orientation, then drop EXIF
            image.thumbnail((MAX_EDGE, MAX_EDGE))
            output = BytesIO()
            if extension == "jpg":
                image.convert("RGB").save(output, format="JPEG", quality=85, optimize=True)
            else:
                image.save(output, format="PNG", optimize=True)
            return output.getvalue(), extension
    except HTTPException:
        raise
    except Image.DecompressionBombError:
        raise HTTPException(413, "Device photo exceeds the 20 megapixel limit")
    except (UnidentifiedImageError, OSError, ValueError):
        raise HTTPException(415, "Image could not be decoded")


def _require_camera(camera_id: int):
    with Session() as db:
        if not db.get(Camera, camera_id):
            raise HTTPException(404, "Camera not found")


def build_router(deps) -> APIRouter:
    router = APIRouter(prefix="/api/cameras/{camera_id}/device-image", tags=["devices"])

    @router.get("")
    def get_device_image(camera_id: int, user=Depends(deps.current_user)):
        _require_camera(camera_id)
        path = device_image_path(camera_id)
        if not path:
            raise HTTPException(404, "No device photo for this camera")
        # The URL carries ?v=<version>, so a revalidating cache is enough
        return FileResponse(path, media_type="image/png" if path.suffix == ".png" else "image/jpeg",
                            headers={"Cache-Control": "private, no-cache"})

    @router.post("")
    async def upload_device_image(camera_id: int, request: Request, user=Depends(deps.require_admin)):
        _require_camera(camera_id)
        raw = await request.body()
        if not raw or len(raw) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "Device photo must be between 1 byte and 8 MiB")
        data, extension = _normalise(raw)
        DEVICE_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        target = DEVICE_IMAGE_DIR / f"camera-{camera_id}.{extension}"
        temporary = target.with_suffix(f".{extension}.tmp")
        temporary.write_bytes(data)
        os.replace(temporary, target)                        # atomic: readers never see a half-written file
        for other in EXTENSIONS:
            if other != extension:
                (DEVICE_IMAGE_DIR / f"camera-{camera_id}.{other}").unlink(missing_ok=True)
        return {"camera_id": camera_id, "device_image_version": device_image_version(camera_id)}

    @router.delete("", status_code=204)
    def delete_device_image(camera_id: int, user=Depends(deps.require_admin)):
        _require_camera(camera_id)
        for extension in EXTENSIONS:
            (DEVICE_IMAGE_DIR / f"camera-{camera_id}.{extension}").unlink(missing_ok=True)
        return Response(status_code=204)

    return router
