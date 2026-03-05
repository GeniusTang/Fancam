from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from core.config import settings
from core.job_store import job_store
from models.job import JobStatus

router = APIRouter()


@router.get("/download/{job_id}")
async def download_fancam(job_id: str):
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    if job.status != JobStatus.COMPLETE:
        raise HTTPException(409, "Fancam not ready yet")

    out_path = settings.output_dir / job.output_filename
    if not out_path.exists():
        raise HTTPException(500, "Output file missing")

    return FileResponse(
        path=str(out_path),
        media_type="video/mp4",
        filename=f"fancam_{job_id}.mp4",
        headers={"Content-Disposition": f'attachment; filename="fancam_{job_id}.mp4"'},
    )


@router.get("/thumbnails/{job_id}/{filename}")
async def serve_thumbnail(job_id: str, filename: str):
    # Sanitize filename
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400, "Invalid filename")
    path = settings.thumbnail_dir / job_id / filename
    if not path.exists():
        raise HTTPException(404, "Thumbnail not found")
    return FileResponse(str(path), media_type="image/jpeg")
