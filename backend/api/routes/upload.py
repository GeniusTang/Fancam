import asyncio
from pathlib import Path

import aiofiles
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from core.config import settings
from core.job_store import job_store
from core.worker import run_analysis
from models.job import Job, JobStatus
from storage.file_manager import generate_job_id, upload_path

router = APIRouter()

ALLOWED_TYPES = {"video/mp4", "video/quicktime", "video/x-msvideo", "video/webm", "video/mpeg"}
MAX_BYTES = settings.max_upload_size_mb * 1024 * 1024


@router.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    if file.content_type and file.content_type not in ALLOWED_TYPES:
        # Be lenient with content type — browsers sometimes lie
        ext = Path(file.filename or "").suffix.lower()
        if ext not in {".mp4", ".mov", ".avi", ".webm", ".mpeg", ".mpg"}:
            raise HTTPException(415, "Unsupported file type")

    job_id = generate_job_id()
    save_path = upload_path(job_id, file.filename or "video.mp4")

    # Stream to disk
    size = 0
    async with aiofiles.open(save_path, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_BYTES:
                save_path.unlink(missing_ok=True)
                raise HTTPException(413, f"File too large (limit {settings.max_upload_size_mb} MB)")
            await f.write(chunk)

    job = job_store.create(
        Job(job_id=job_id, status=JobStatus.PENDING, video_filename=save_path.name)
    )

    # Kick off analysis in background
    asyncio.create_task(run_analysis(job_id, save_path))

    return JSONResponse({"job_id": job_id})
