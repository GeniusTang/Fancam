import asyncio
from pathlib import Path
from typing import List

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core.config import settings
from core.job_store import job_store
from core.worker import run_generation
from models.job import JobStatus

router = APIRouter()


class CutSection(BaseModel):
    start: int  # first frame to cut (inclusive)
    end: int    # last frame to cut (inclusive)


class GenerateRequest(BaseModel):
    job_id: str
    person_id: str
    cuts: List[CutSection] = []


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

    # Normalize cuts: sort, merge overlaps, validate
    cuts = sorted(req.cuts, key=lambda c: c.start)
    merged_cuts = []
    for c in cuts:
        if c.start > c.end:
            raise HTTPException(400, f"Invalid cut: start ({c.start}) > end ({c.end})")
        if merged_cuts and c.start <= merged_cuts[-1].end + 1:
            merged_cuts[-1] = CutSection(start=merged_cuts[-1].start, end=max(merged_cuts[-1].end, c.end))
        else:
            merged_cuts.append(c)

    job_store.update(req.job_id, selected_person_id=req.person_id)
    cuts_raw = [{"start": c.start, "end": c.end} for c in merged_cuts]
    task = asyncio.create_task(run_generation(req.job_id, req.person_id, video_path, cuts_raw))
    job_store.set_task(req.job_id, task)

    return JSONResponse({"job_id": req.job_id, "person_id": req.person_id})
