"""Background worker: runs analysis, preview, and generation pipelines."""
import asyncio
import time
import traceback
from collections import defaultdict
from pathlib import Path
from typing import Callable, Dict, List, Tuple

import cv2
import numpy as np

from core.job_store import job_store
from models.job import JobStatus, AnalysisStage, GenerationStage
from models.person import Person
from storage.file_manager import output_path


# ── In-memory caches (MVP — lost on restart) ──────────────────────────────────
_track_fragments_cache: Dict[str, Dict] = {}
_cluster_map_cache: Dict[str, Dict] = {}
# job_id → frame_idx → [(track_id, xyxy, conf), ...]
_frame_bbox_index: Dict[str, Dict[int, List[Tuple[int, np.ndarray, float]]]] = {}


# ── Async entry points ────────────────────────────────────────────────────────

async def run_analysis(job_id: str, video_path: Path):
    loop = asyncio.get_running_loop()

    def push(**kwargs):
        """Thread-safe progress push to the event loop."""
        loop.call_soon_threadsafe(
            lambda kw=kwargs: asyncio.ensure_future(_set(job_id, **kw))
        )

    try:
        await _set(job_id, status=JobStatus.ANALYZING, stage=AnalysisStage.DETECTING, progress=0.0)

        cap = cv2.VideoCapture(str(video_path))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        cap.release()
        await _set(job_id, total_frames=total_frames, fps=fps)

        # ── Phase 1: detect + track (runs in thread — blocks CPU freely) ──
        push(stage=AnalysisStage.TRACKING, progress=0.02)
        t0 = time.monotonic()
        track_fragments = await loop.run_in_executor(
            None, lambda: _sync_detect_track(video_path, total_frames, push)
        )

        if not track_fragments:
            await _set(job_id, status=JobStatus.ERROR, error="No persons detected in video")
            return

        # Drop tracks shorter than 1 second — usually false positives
        min_frames = max(5, int((job_store.get(job_id).fps or 30) * 1.0))
        track_fragments = {tid: obs for tid, obs in track_fragments.items() if len(obs) >= min_frames}
        if not track_fragments:
            await _set(job_id, status=JobStatus.ERROR, error="No stable person tracks found (try a longer video)")
            return
        print(f"[worker] {len(track_fragments)} track fragments after filtering:")
        for tid, obs in sorted(track_fragments.items(), key=lambda x: -len(x[1])):
            frames = [o[0] for o in obs]
            print(f"  track {tid:3d}: {len(obs):4d} frames  span={min(frames)}–{max(frames)}")

        await _set(job_id, stage=AnalysisStage.CLUSTERING, progress=0.5)

        # ── Phase 2: embed (body + face) + thumbnails in single video pass ──
        spans = {
            tid: (min(o[0] for o in obs), max(o[0] for o in obs))
            for tid, obs in track_fragments.items()
        }

        # Build cluster info early so thumbnails can be done in the same pass
        # Use a temporary 1:1 cluster map (each track = own cluster) for the pass,
        # then re-do with real clustering. But we need cluster_obs for thumbnails
        # which requires cluster_map... So we do a 2-step:
        #   Step 1: single pass for embeddings (body + face)
        #   Step 2: cluster
        #   Step 3: single pass for thumbnails only
        # Actually, thumbnails need cluster_obs which depends on cluster_map.
        # But we can pre-build cluster_obs using ALL track observations and
        # just pick best per cluster after clustering. Let's do it in 2 passes:
        #   Pass 1: body + face embeddings (sampled frames only)
        #   Then cluster
        #   Pass 2: thumbnails (needs cluster info)
        # This is still better: we merged 2 video passes (body + face) into 1.

        embeddings, face_embeddings = await loop.run_in_executor(
            None, lambda: _sync_embed_all(video_path, track_fragments)
        )

        print(f"[worker] embeddings: {len(embeddings)} body, "
              f"{sum(1 for v in face_embeddings.values() if v is not None)} faces")

        from pipeline.person_clusterer import cluster_persons
        track_ids = list(track_fragments.keys())
        cluster_map = cluster_persons(track_ids, embeddings, spans, face_embeddings=face_embeddings)

        unique_clusters = set(cluster_map.values())
        print(f"[worker] clustering → {len(unique_clusters)} clusters: {dict(sorted(cluster_map.items()))}")

        await _set(job_id, stage=AnalysisStage.THUMBNAILING, progress=0.7)

        # ── Phase 3: thumbnails (in thread) ──
        cluster_obs: Dict[int, List[Tuple[int, np.ndarray, float]]] = defaultdict(list)
        cluster_track_ids: Dict[int, List[int]] = defaultdict(list)
        for tid, obs in track_fragments.items():
            cid = cluster_map[tid]
            cluster_obs[cid].extend(obs)
            cluster_track_ids[cid].append(tid)

        person_ids = {cid: f"person_{cid}" for cid in cluster_obs}
        await loop.run_in_executor(
            None,
            lambda: _sync_thumbnails(job_id, video_path, cluster_obs, person_ids),
        )

        # ── Build Person models ──
        persons = []
        for cid, tids in cluster_track_ids.items():
            all_obs = cluster_obs[cid]
            all_frames = [o[0] for o in all_obs]
            persons.append(
                Person(
                    person_id=person_ids[cid],
                    cluster_id=cid,
                    track_ids=tids,
                    thumbnail_file=f"{person_ids[cid]}.jpg",
                    frame_count=len(all_obs),
                    first_frame=min(all_frames),
                    last_frame=max(all_frames),
                )
            )
        persons.sort(key=lambda p: p.frame_count, reverse=True)

        job_store.set_persons(job_id, persons)
        _track_fragments_cache[job_id] = dict(track_fragments)
        _cluster_map_cache[job_id] = cluster_map

        # Build frame-indexed bbox lookup for correction UI
        frame_index: Dict[int, List[Tuple[int, np.ndarray, float]]] = defaultdict(list)
        for tid, obs in track_fragments.items():
            for frame_idx, xyxy, conf in obs:
                frame_index[frame_idx].append((tid, xyxy, conf))
        _frame_bbox_index[job_id] = dict(frame_index)

        elapsed = time.monotonic() - t0
        print(f"[worker] analysis complete in {elapsed:.1f}s")
        await _set(job_id, status=JobStatus.READY_FOR_SELECTION, stage=None, progress=1.0)

    except Exception as e:
        await _set(job_id, status=JobStatus.ERROR, error=str(e))
        print(f"[worker] analysis error for {job_id}:\n{traceback.format_exc()}")


async def run_generation(job_id: str, person_id: str, video_path: Path):
    loop = asyncio.get_running_loop()
    t0 = time.monotonic()

    def push(**kwargs):
        loop.call_soon_threadsafe(
            lambda kw=kwargs: asyncio.ensure_future(_set(job_id, **kw))
        )

    try:
        await _set(job_id, status=JobStatus.GENERATING, stage=GenerationStage.RENDERING, progress=0.0)

        cluster_map = _cluster_map_cache.get(job_id, {})
        track_fragments = _track_fragments_cache.get(job_id, {})
        if not cluster_map:
            await _set(job_id, status=JobStatus.ERROR, error="Analysis data not found — re-upload")
            return

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
            await _set(job_id, status=JobStatus.ERROR, error=f"No track data for {person_id}")
            return

        # Apply redirect rules if any
        from core.corrections import _redirect_rules, apply_redirects
        rules = _redirect_rules.get(job_id, [])
        if rules:
            frame_track_map = apply_redirects(frame_track_map, rules, track_fragments, cluster_map, person_id)

        # Apply user corrections if any
        from core.corrections import _corrections_cache, apply_corrections
        corrections = _corrections_cache.get(job_id, {})
        if corrections:
            frame_track_map = apply_corrections(frame_track_map, corrections)

        out_path = output_path(job_id)

        # Get total frames for ETA calculation
        cap = cv2.VideoCapture(str(video_path))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()

        frames_done = [0]

        def progress_with_eta(p: float):
            frames_done[0] = int(p * total_frames)
            elapsed = time.monotonic() - t0
            if p > 0.05:
                eta = elapsed / p * (1 - p)
            else:
                eta = -1  # not enough data
            push(progress=p * 0.9, eta=round(eta, 1) if eta > 0 else None)

        await loop.run_in_executor(
            None,
            lambda: _sync_render(video_path, out_path, frame_track_map, progress_with_eta),
        )

        elapsed = time.monotonic() - t0
        print(f"[worker] generation complete in {elapsed:.1f}s")
        await _set(job_id, status=JobStatus.COMPLETE, stage=None, progress=1.0,
                   output_filename=out_path.name, eta=None)

    except Exception as e:
        await _set(job_id, status=JobStatus.ERROR, error=str(e))
        print(f"[worker] generation error for {job_id}:\n{traceback.format_exc()}")


# ── Sync helpers (safe to run in thread pool) ─────────────────────────────────

def _sync_detect_track(
    video_path: Path,
    total_frames: int,
    push: Callable,
) -> Dict[int, List[Tuple[int, np.ndarray, float]]]:
    from pipeline.detector import Detector
    from pipeline.tracker import Tracker

    print("[worker] initialising detector + tracker (may download models)…")
    detector = Detector()
    tracker = Tracker()
    print("[worker] detector + tracker ready")

    track_fragments: Dict[int, List[Tuple[int, np.ndarray, float]]] = defaultdict(list)
    t0 = time.monotonic()

    total_dets = 0
    for frame_idx, total, frame, detections in detector.detect_video(video_path):
        total_dets += len(detections)
        track_result = tracker.update(frame, detections)
        for tid, data in track_result.items():
            track_fragments[tid].append((frame_idx, data["xyxy"], data["conf"]))

        if frame_idx % 30 == 0:
            progress = 0.02 + 0.45 * (frame_idx / max(total, 1))
            elapsed = time.monotonic() - t0
            if frame_idx > 0:
                eta = elapsed / frame_idx * (total - frame_idx)
            else:
                eta = -1
            push(progress=progress, eta=round(eta, 1) if eta > 0 else None)

    avg_dets = total_dets / max(total_frames, 1)
    print(f"[worker] detect+track done: {total_frames} frames, "
          f"avg {avg_dets:.1f} detections/frame, {len(track_fragments)} raw tracks")
    return dict(track_fragments)


def _sync_embed_all(video_path, track_fragments):
    """Single video pass: body ReID + face embeddings."""
    from pipeline.post_tracker import PostTracker
    pt = PostTracker()
    # Pass empty cluster_obs and person_ids — thumbnails done separately after clustering
    return pt.run(
        job_id="",
        video_path=video_path,
        track_fragments=track_fragments,
        cluster_obs={},
        person_ids={},
    )


def _sync_thumbnails(job_id, video_path, cluster_obs, person_ids):
    from pipeline.thumbnail_generator import generate_thumbnails
    generate_thumbnails(job_id, video_path, cluster_obs, person_ids)


def _sync_render(video_path, out_path, frame_track_map, push):
    from pipeline.fancam_renderer import FancamRenderer

    last = [0.0]

    def cb(p: float):
        if p - last[0] >= 0.02:
            last[0] = p
            push(p)

    FancamRenderer().render(video_path, out_path, frame_track_map, cb)


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _set(job_id: str, **kwargs):
    job_store.update(job_id, **kwargs)
    await asyncio.sleep(0)
