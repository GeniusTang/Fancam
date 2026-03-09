import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core.config import settings
from core.job_store import job_store
from core.worker import run_generation
from models.job import JobStatus

router = APIRouter()


class GenerateRequest(BaseModel):
    job_id: str
    person_id: str


@router.post("/generate")
async def generate_fancam(req: GenerateRequest):
    job = job_store.get(req.job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    if job.status != JobStatus.READY_FOR_SELECTION:
        raise HTTPException(409, f"Job not ready for generation (status: {job.status})")

    persons = job_store.get_persons(req.job_id)
    valid_ids = {p.person_id for p in persons}
    if req.person_id not in valid_ids:
        raise HTTPException(404, f"Person '{req.person_id}' not found")

    # Find video path
    video_path = settings.upload_dir / job.video_filename
    if not video_path.exists():
        raise HTTPException(500, "Source video missing")

    job_store.update(req.job_id, selected_person_id=req.person_id)
    task = asyncio.create_task(run_generation(req.job_id, req.person_id, video_path))
    job_store.set_task(req.job_id, task)

    return JSONResponse({"job_id": req.job_id, "person_id": req.person_id})
