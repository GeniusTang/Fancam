from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from core.job_store import job_store
from models.job import JobStatus

router = APIRouter()


@router.get("/analysis/{job_id}")
async def get_analysis(job_id: str):
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    if job.status not in (
        JobStatus.READY_FOR_SELECTION,
        JobStatus.GENERATING,
        JobStatus.COMPLETE,
    ):
        raise HTTPException(409, f"Analysis not ready (status: {job.status})")

    persons = job_store.get_persons(job_id)
    return JSONResponse(
        {
            "job_id": job_id,
            "persons": [
                {
                    "person_id": p.person_id,
                    "thumbnail_url": f"/thumbnails/{job_id}/{p.thumbnail_file}",
                    "frame_count": p.frame_count,
                    "first_frame": p.first_frame,
                    "last_frame": p.last_frame,
                }
                for p in persons
            ],
        }
    )
