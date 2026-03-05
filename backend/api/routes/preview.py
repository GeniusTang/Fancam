import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from core.config import settings
from core.job_store import job_store
from core.worker import run_preview
from models.job import JobStatus

router = APIRouter()


@router.get("/preview-video/{filename}")
async def serve_preview_video(filename: str):
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400, "Invalid filename")
    path = settings.output_dir / filename
    if not path.exists():
        raise HTTPException(404, "Preview not found")
    return FileResponse(str(path), media_type="video/mp4")


class PreviewRequest(BaseModel):
    job_id: str
    person_id: str


@router.post("/preview")
async def generate_preview(req: PreviewRequest):
    job = job_store.get(req.job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    if job.status not in (JobStatus.READY_FOR_SELECTION, JobStatus.PREVIEWING):
        raise HTTPException(409, f"Job not ready for preview (status: {job.status})")

    persons = job_store.get_persons(req.job_id)
    valid_ids = {p.person_id for p in persons}
    if req.person_id not in valid_ids:
        raise HTTPException(404, f"Person '{req.person_id}' not found")

    video_path = settings.upload_dir / job.video_filename
    if not video_path.exists():
        raise HTTPException(500, "Source video missing")

    try:
        preview_path = await run_preview(req.job_id, req.person_id, video_path)
        preview_url = f"/preview-video/{preview_path.name}"
        return JSONResponse({"preview_url": preview_url})
    except Exception as e:
        raise HTTPException(500, str(e))
