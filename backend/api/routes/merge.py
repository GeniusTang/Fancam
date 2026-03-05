"""Merge two or more person clusters into one."""
from collections import defaultdict
from pathlib import Path
from typing import List

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core.config import settings
from core.job_store import job_store
from core.worker import _cluster_map_cache, _track_fragments_cache
from models.job import JobStatus
from models.person import Person

router = APIRouter()


class MergeRequest(BaseModel):
    job_id: str
    person_ids: List[str]  # 2+ person_ids to merge into one


@router.post("/merge")
async def merge_persons(req: MergeRequest):
    if len(req.person_ids) < 2:
        raise HTTPException(400, "Need at least 2 person_ids to merge")

    job = job_store.get(req.job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    if job.status not in (JobStatus.READY_FOR_SELECTION,):
        raise HTTPException(409, f"Cannot merge in state: {job.status}")

    cluster_map = _cluster_map_cache.get(req.job_id)
    track_fragments = _track_fragments_cache.get(req.job_id)
    if cluster_map is None:
        raise HTTPException(500, "Analysis data missing — re-upload")

    # Resolve cluster_ids for requested person_ids
    target_cids = set()
    for pid in req.person_ids:
        try:
            target_cids.add(int(pid.replace("person_", "")))
        except ValueError:
            raise HTTPException(400, f"Invalid person_id: {pid}")

    keep_cid = min(target_cids)  # canonical cluster after merge

    # Update cluster map in-place
    for tid in cluster_map:
        if cluster_map[tid] in target_cids:
            cluster_map[tid] = keep_cid

    # Rebuild persons list
    cluster_obs = defaultdict(list)
    cluster_track_ids = defaultdict(list)
    for tid, obs in track_fragments.items():
        cid = cluster_map[tid]
        cluster_obs[cid].extend(obs)
        cluster_track_ids[cid].append(tid)

    person_ids_map = {cid: f"person_{cid}" for cid in cluster_obs}

    # Re-generate thumbnail for merged cluster only
    video_path = settings.upload_dir / job.video_filename
    from pipeline.thumbnail_generator import generate_thumbnails
    import asyncio
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        lambda: generate_thumbnails(
            req.job_id, video_path,
            {keep_cid: cluster_obs[keep_cid]},
            {keep_cid: person_ids_map[keep_cid]},
        ),
    )

    persons = []
    for cid, tids in cluster_track_ids.items():
        all_obs = cluster_obs[cid]
        all_frames = [o[0] for o in all_obs]
        persons.append(
            Person(
                person_id=person_ids_map[cid],
                cluster_id=cid,
                track_ids=tids,
                thumbnail_file=f"{person_ids_map[cid]}.jpg",
                frame_count=len(all_obs),
                first_frame=min(all_frames),
                last_frame=max(all_frames),
            )
        )
    persons.sort(key=lambda p: p.frame_count, reverse=True)
    job_store.set_persons(req.job_id, persons)

    return JSONResponse({
        "job_id": req.job_id,
        "persons": [
            {
                "person_id": p.person_id,
                "thumbnail_url": f"/thumbnails/{req.job_id}/{p.thumbnail_file}",
                "frame_count": p.frame_count,
                "first_frame": p.first_frame,
                "last_frame": p.last_frame,
            }
            for p in persons
        ],
    })
