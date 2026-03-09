"""Correction endpoints: frame serving, track data, correction CRUD."""

import threading
from collections import OrderedDict
from pathlib import Path
from typing import Dict, List, Optional

import cv2
import numpy as np
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from core.corrections import (
    add_redirect,
    apply_corrections,
    apply_redirects,
    clear_corrections,
    clear_redirects,
    detect_jumps,
    get_corrections,
    get_redirects,
    set_corrections,
    undo_last_redirect,
)
from core.job_store import job_store
from core.worker import _cluster_map_cache, _frame_bbox_index, _track_fragments_cache
from storage.file_manager import upload_path

router = APIRouter()


# ── FrameReader: keeps VideoCapture open, sequential reads preferred ─────────

class FrameReader:
    """Caches an open VideoCapture and an LRU frame cache (~50 frames)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._caps: Dict[str, cv2.VideoCapture] = {}
        self._cache: OrderedDict = OrderedDict()
        self._max_cache = 50

    def _get_cap(self, video_path: str) -> cv2.VideoCapture:
        if video_path not in self._caps:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                raise RuntimeError(f"Cannot open video: {video_path}")
            self._caps[video_path] = cap
        return self._caps[video_path]

    def read_frame(self, video_path: str, frame_idx: int) -> np.ndarray:
        cache_key = (video_path, frame_idx)
        with self._lock:
            if cache_key in self._cache:
                self._cache.move_to_end(cache_key)
                return self._cache[cache_key]

        with self._lock:
            cap = self._get_cap(video_path)
            current_pos = int(cap.get(cv2.CAP_PROP_POS_FRAMES))

            # Sequential read is much faster than seeking
            if frame_idx != current_pos:
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)

            ret, frame = cap.read()
            if not ret:
                raise RuntimeError(f"Failed to read frame {frame_idx}")

            # LRU eviction
            self._cache[cache_key] = frame
            self._cache.move_to_end(cache_key)
            while len(self._cache) > self._max_cache:
                self._cache.popitem(last=False)

            return frame

    def get_info(self, video_path: str) -> dict:
        with self._lock:
            cap = self._get_cap(video_path)
            return {
                "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                "total_frames": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
                "fps": cap.get(cv2.CAP_PROP_FPS) or 30.0,
            }


_frame_reader = FrameReader()


# ── Helpers ──────────────────────────────────────────────────────────────────

def _video_path_for_job(job_id: str) -> Path:
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return upload_path(job_id, job.video_filename)


def _build_frame_track_map(job_id: str, person_id: str) -> Dict[int, np.ndarray]:
    cluster_map = _cluster_map_cache.get(job_id, {})
    track_fragments = _track_fragments_cache.get(job_id, {})
    if not cluster_map:
        raise HTTPException(404, "Analysis data not found")

    cluster_id = int(person_id.replace("person_", ""))
    frame_track_map: Dict[int, np.ndarray] = {}
    frame_conf_map: Dict[int, float] = {}
    for tid, cid in cluster_map.items():
        if cid == cluster_id and tid in track_fragments:
            for frame_idx, xyxy, conf in track_fragments[tid]:
                if frame_idx not in frame_track_map or conf > frame_conf_map[frame_idx]:
                    frame_track_map[frame_idx] = xyxy
                    frame_conf_map[frame_idx] = conf

    if not frame_track_map:
        raise HTTPException(404, f"No track data for {person_id}")
    return frame_track_map


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/correction-video/{job_id}")
async def get_correction_video(job_id: str):
    """Serve the source video file for playback."""
    vpath = _video_path_for_job(job_id)
    return FileResponse(str(vpath), media_type="video/mp4")


@router.get("/correction-frame/{job_id}/{frame_idx}")
async def get_correction_frame(job_id: str, frame_idx: int):
    """Serve a source video frame as JPEG."""
    vpath = _video_path_for_job(job_id)
    try:
        frame = _frame_reader.read_frame(str(vpath), frame_idx)
    except RuntimeError as e:
        raise HTTPException(400, str(e))

    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return Response(content=buf.tobytes(), media_type="image/jpeg")


@router.get("/corrections/{job_id}/{person_id}/track-data")
async def get_track_data(job_id: str, person_id: str):
    """Return frame_track_map (detection frames only) + detected jumps."""
    vpath = _video_path_for_job(job_id)
    frame_track_map = _build_frame_track_map(job_id, person_id, )

    # Apply redirect rules
    rules = get_redirects(job_id)
    if rules:
        track_fragments = _track_fragments_cache.get(job_id, {})
        cluster_map = _cluster_map_cache.get(job_id, {})
        frame_track_map = apply_redirects(frame_track_map, rules, track_fragments, cluster_map, person_id)

    # Apply existing corrections
    corrections = get_corrections(job_id)
    if corrections:
        merged = apply_corrections(frame_track_map, corrections)
    else:
        merged = frame_track_map

    info = _frame_reader.get_info(str(vpath))
    jumps = detect_jumps(merged, info["width"])

    # Serialize frame_track_map: { frame_idx: [x1, y1, x2, y2] }
    track_data = {
        str(f): [round(float(v), 1) for v in xyxy]
        for f, xyxy in sorted(merged.items())
    }

    # Serialize corrections
    corr_data = {
        str(f): entry.to_dict()
        for f, entry in sorted(corrections.items())
    }

    return {
        "frame_track_map": track_data,
        "corrections": corr_data,
        "jumps": jumps,
        "video_info": info,
    }


@router.get("/corrections/{job_id}/frame-bboxes/{frame_idx}")
async def get_frame_bboxes(job_id: str, frame_idx: int):
    """Return ALL tracked bboxes on this frame (all persons)."""
    _ = job_store.get(job_id)
    if not _:
        raise HTTPException(404, "Job not found")

    frame_index = _frame_bbox_index.get(job_id, {})
    cluster_map = _cluster_map_cache.get(job_id, {})

    entries = frame_index.get(frame_idx, [])
    bboxes = []
    for track_id, xyxy, conf in entries:
        cid = cluster_map.get(track_id)
        person_id = f"person_{cid}" if cid is not None else None
        bboxes.append({
            "track_id": track_id,
            "person_id": person_id,
            "xyxy": [round(float(v), 1) for v in xyxy],
            "conf": round(float(conf), 3),
        })

    return {"bboxes": bboxes}


class RedirectBody(BaseModel):
    person_id: str
    from_frame: int
    to_track_id: int


@router.post("/corrections/{job_id}/redirect")
async def post_redirect(job_id: str, body: RedirectBody):
    """Store a redirect rule and return updated track data."""
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    add_redirect(job_id, body.from_frame, body.to_track_id)

    # Return updated track data with redirects applied (detection frames only for UI)
    vpath = _video_path_for_job(job_id)
    base_map = _build_frame_track_map(job_id, body.person_id, )
    track_fragments = _track_fragments_cache.get(job_id, {})
    cluster_map = _cluster_map_cache.get(job_id, {})
    rules = get_redirects(job_id)

    merged = apply_redirects(base_map, rules, track_fragments, cluster_map, body.person_id)

    # Apply frame-level corrections on top
    corrections = get_corrections(job_id)
    if corrections:
        merged = apply_corrections(merged, corrections)

    info = _frame_reader.get_info(str(vpath))
    jumps = detect_jumps(merged, info["width"])

    track_data = {
        str(f): [round(float(v), 1) for v in xyxy]
        for f, xyxy in sorted(merged.items())
    }

    return {
        "frame_track_map": track_data,
        "jumps": jumps,
        "redirects": [{"from_frame": r.from_frame, "to_track_id": r.to_track_id} for r in rules],
    }


@router.post("/corrections/{job_id}/undo-redirect")
async def post_undo_redirect(job_id: str, person_id: str = ""):
    """Undo the last redirect rule."""
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    success = undo_last_redirect(job_id)
    if not success:
        return {"ok": False, "message": "No redirects to undo"}

    # If person_id provided, return updated track data
    if person_id:
        vpath = _video_path_for_job(job_id)
        base_map = _build_frame_track_map(job_id, person_id, )
        track_fragments = _track_fragments_cache.get(job_id, {})
        cluster_map = _cluster_map_cache.get(job_id, {})
        rules = get_redirects(job_id)

        merged = apply_redirects(base_map, rules, track_fragments, cluster_map, person_id)

        corrections = get_corrections(job_id)
        if corrections:
            merged = apply_corrections(merged, corrections)

        info = _frame_reader.get_info(str(vpath))
        jumps = detect_jumps(merged, info["width"])

        track_data = {
            str(f): [round(float(v), 1) for v in xyxy]
            for f, xyxy in sorted(merged.items())
        }

        return {
            "ok": True,
            "frame_track_map": track_data,
            "jumps": jumps,
            "redirects": [{"from_frame": r.from_frame, "to_track_id": r.to_track_id} for r in rules],
        }

    return {"ok": True}


class CorrectionItem(BaseModel):
    frame_idx: int
    action: str  # "set" or "delete"
    xyxy: Optional[List[float]] = None


class SubmitCorrectionsBody(BaseModel):
    person_id: str
    corrections: List[CorrectionItem]


@router.post("/corrections/{job_id}")
async def submit_corrections(job_id: str, body: SubmitCorrectionsBody):
    """Submit a batch of corrections."""
    _ = job_store.get(job_id)
    if not _:
        raise HTTPException(404, "Job not found")

    set_corrections(
        job_id,
        body.person_id,
        [c.model_dump() for c in body.corrections],
    )
    return {"ok": True, "count": len(body.corrections)}


@router.delete("/corrections/{job_id}")
async def delete_corrections(job_id: str):
    """Clear all corrections for a job."""
    clear_corrections(job_id)
    clear_redirects(job_id)
    return {"ok": True}
