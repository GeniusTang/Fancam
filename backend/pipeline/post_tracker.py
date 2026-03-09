"""Single-pass post-tracking: ReID embeddings, face embeddings, and thumbnails.

Merges three separate video passes into one sequential read, saving ~2x I/O time.
"""
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from core.config import settings
from storage.file_manager import thumbnail_path


def _uniform_sample(observations: List, n: int) -> List:
    if len(observations) <= n:
        return observations
    indices = np.linspace(0, len(observations) - 1, n, dtype=int)
    return [observations[i] for i in indices]


def _sharpness(crop: np.ndarray) -> float:
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _thumb_score(crop: np.ndarray, conf: float, fw: int, fh: int, xyxy: np.ndarray) -> float:
    x1, y1, x2, y2 = xyxy
    area = (x2 - x1) * (y2 - y1) / (fw * fh)
    margin_x = min(x1 / fw, (fw - x2) / fw)
    margin_y = min(y1 / fh, (fh - y2) / fh)
    edge_score = max(0.0, min(margin_x, margin_y) * 4)
    sharp = min(_sharpness(crop) / 500.0, 2.0)
    return sharp * 0.4 + area * 0.3 + conf * 0.2 + edge_score * 0.1


def _safe_crop(frame: np.ndarray, xyxy: np.ndarray, h: int, w: int):
    x1, y1, x2, y2 = xyxy
    x1, y1 = max(0, int(x1)), max(0, int(y1))
    x2, y2 = min(w, int(x2)), min(h, int(y2))
    if x2 <= x1 or y2 <= y1:
        return None
    return frame[y1:y2, x1:x2]


class PostTracker:
    """Runs ReID, face embedding, and thumbnail selection in a single video pass."""

    def __init__(self):
        # Lazy-load models
        self._reid = None
        self._face_app = None

    def _init_reid(self):
        if self._reid is not None:
            return
        from boxmot import ReID
        print(f"[post-tracker] loading ReID {settings.reid_model}…")
        self._reid = ReID(
            weights=settings.reid_model,
            device=settings.device,
            half=True,
        )
        print("[post-tracker] ReID ready")

    def _init_face(self):
        if self._face_app is not None:
            return
        try:
            from insightface.app import FaceAnalysis
            print("[post-tracker] loading InsightFace…")
            self._face_app = FaceAnalysis(
                name="buffalo_l",
                providers=["CoreMLExecutionProvider", "CPUExecutionProvider"],
            )
            self._face_app.prepare(ctx_id=0, det_size=(160, 160))
            print("[post-tracker] InsightFace ready")
        except Exception as e:
            print(f"[post-tracker] InsightFace unavailable ({e}), skipping face features")
            self._face_app = False  # sentinel: tried and failed

    def run(
        self,
        job_id: str,
        video_path: Path,
        track_fragments: Dict[int, List[Tuple[int, np.ndarray, float]]],
        cluster_obs: Dict[int, List[Tuple[int, np.ndarray, float]]],
        person_ids: Dict[int, str],
        sample_n: int = None,
    ) -> Tuple[
        Dict[int, np.ndarray],              # body embeddings
        Dict[int, Optional[np.ndarray]],     # face embeddings
    ]:
        if sample_n is None:
            sample_n = settings.embedding_sample_frames

        self._init_reid()
        self._init_face()
        face_enabled = self._face_app and self._face_app is not False

        # ── Build frame indices for all three tasks ──────────────────────

        # ReID: sampled frames per track fragment
        reid_frame_index: Dict[int, List[Tuple[int, np.ndarray, float]]] = {}
        for tid, observations in track_fragments.items():
            for fidx, xyxy, conf in _uniform_sample(observations, sample_n):
                reid_frame_index.setdefault(fidx, []).append((tid, xyxy, conf))

        # Face: same sampled frames
        face_frame_index: Dict[int, List[Tuple[int, np.ndarray, float]]] = {}
        if face_enabled:
            for tid, observations in track_fragments.items():
                for fidx, xyxy, conf in _uniform_sample(observations, sample_n):
                    face_frame_index.setdefault(fidx, []).append((tid, xyxy, conf))

        # Thumbnails: all observation frames per cluster
        thumb_frame_index: Dict[int, List[Tuple[int, np.ndarray, float]]] = {}
        for cid, obs_list in cluster_obs.items():
            for fidx, xyxy, conf in obs_list:
                thumb_frame_index.setdefault(fidx, []).append((cid, xyxy, conf))

        # Union of all needed frames
        all_needed = set(reid_frame_index.keys()) | set(face_frame_index.keys()) | set(thumb_frame_index.keys())

        # ── Accumulators ─────────────────────────────────────────────────

        reid_acc: Dict[int, List[Tuple[np.ndarray, float]]] = {tid: [] for tid in track_fragments}
        face_acc: Dict[int, List[Tuple[np.ndarray, float]]] = {tid: [] for tid in track_fragments}
        thumb_best: Dict[int, Tuple[float, np.ndarray]] = {}

        # ── Single sequential video pass ─────────────────────────────────

        cap = cv2.VideoCapture(str(video_path))
        fw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        fh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        frame_idx = 0

        try:
            while all_needed:
                ret, frame = cap.read()
                if not ret:
                    break
                if frame_idx not in all_needed:
                    frame_idx += 1
                    continue
                all_needed.discard(frame_idx)
                h, w = frame.shape[:2]

                # ── ReID ──
                if frame_idx in reid_frame_index:
                    valid = []
                    for tid, xyxy, conf in reid_frame_index[frame_idx]:
                        x1, y1, x2, y2 = xyxy
                        x1, y1 = max(0.0, x1), max(0.0, y1)
                        x2, y2 = min(float(w), x2), min(float(h), y2)
                        if x2 > x1 and y2 > y1:
                            valid.append((tid, np.array([x1, y1, x2, y2], dtype=np.float32), conf))
                    if valid:
                        dets = np.array([[*xyxy, 1.0, 0.0] for _, xyxy, _ in valid], dtype=np.float32)
                        embs = self._reid(frame, dets)
                        for i, (tid, _, conf) in enumerate(valid):
                            if i < len(embs):
                                reid_acc[tid].append((embs[i], conf))

                # ── Face ──
                if face_enabled and frame_idx in face_frame_index:
                    for tid, xyxy, conf in face_frame_index[frame_idx]:
                        crop = _safe_crop(frame, xyxy, h, w)
                        if crop is None or crop.size == 0:
                            continue
                        faces = self._face_app.get(crop)
                        if faces:
                            best = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
                            if best.embedding is not None:
                                emb = best.embedding / (np.linalg.norm(best.embedding) + 1e-8)
                                face_acc[tid].append((emb.astype(np.float32), conf))

                # ── Thumbnails ──
                if frame_idx in thumb_frame_index:
                    for cid, xyxy, conf in thumb_frame_index[frame_idx]:
                        crop = _safe_crop(frame, xyxy, h, w)
                        if crop is None or crop.size == 0:
                            continue
                        s = _thumb_score(crop, conf, w, h, xyxy)
                        if cid not in thumb_best or s > thumb_best[cid][0]:
                            thumb_best[cid] = (s, crop.copy())

                frame_idx += 1
        finally:
            cap.release()

        # ── Aggregate ReID embeddings ────────────────────────────────────

        body_embeddings: Dict[int, np.ndarray] = {}
        for tid, feats in reid_acc.items():
            if feats:
                vecs = np.array([f[0] for f in feats], dtype=np.float32)
                weights = np.array([f[1] for f in feats], dtype=np.float32)
                weights = weights / weights.sum()
                body_embeddings[tid] = (vecs * weights[:, None]).sum(axis=0).astype(np.float32)
            else:
                body_embeddings[tid] = np.zeros(512, dtype=np.float32)

        # ── Aggregate face embeddings ────────────────────────────────────

        face_embeddings: Dict[int, Optional[np.ndarray]] = {}
        for tid, feats in face_acc.items():
            if feats:
                vecs = np.array([f[0] for f in feats], dtype=np.float32)
                weights = np.array([f[1] for f in feats], dtype=np.float32)
                weights = weights / weights.sum()
                face_embeddings[tid] = (vecs * weights[:, None]).sum(axis=0).astype(np.float32)
            else:
                face_embeddings[tid] = None

        # ── Save thumbnails ──────────────────────────────────────────────

        for cid, (_, crop) in thumb_best.items():
            pid = person_ids.get(cid)
            if pid is None:
                continue
            out_path = thumbnail_path(job_id, pid)
            cv2.imwrite(str(out_path), crop)

        print(f"[post-tracker] single pass complete: "
              f"{len(body_embeddings)} body embs, "
              f"{sum(1 for v in face_embeddings.values() if v is not None)} face embs, "
              f"{len(thumb_best)} thumbnails")

        return body_embeddings, face_embeddings
