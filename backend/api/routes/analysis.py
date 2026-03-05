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
    total_frames = job.total_frames or 1

    # Build per-person track spans for timeline visualization
    from core.worker import _track_fragments_cache, _cluster_map_cache
    track_fragments = _track_fragments_cache.get(job_id, {})
    cluster_map = _cluster_map_cache.get(job_id, {})

    def _track_spans(p):
        spans = []
        for tid in (p.track_ids or []):
            obs = track_fragments.get(tid, [])
            if obs:
                frames = [o[0] for o in obs]
                spans.append({"start": min(frames), "end": max(frames)})
        return spans

    return JSONResponse(
        {
            "job_id": job_id,
            "total_frames": total_frames,
            "persons": [
                {
                    "person_id": p.person_id,
                    "thumbnail_url": f"/thumbnails/{job_id}/{p.thumbnail_file}",
                    "frame_count": p.frame_count,
                    "first_frame": p.first_frame,
                    "last_frame": p.last_frame,
                    "track_spans": _track_spans(p),
                }
                for p in persons
            ],
        }
    )
