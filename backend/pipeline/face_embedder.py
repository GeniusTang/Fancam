"""Extract face embeddings using InsightFace for improved person re-identification.

Produces a 512-dim face embedding per track fragment by:
  1. Cropping person bboxes from sampled frames
  2. Running InsightFace detection + recognition on each crop
  3. Confidence-weighted mean of all face embeddings found

Returns None for tracks where no face is detected (e.g. back-facing).
"""
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from core.config import settings


class FaceEmbedder:
    def __init__(self):
        from insightface.app import FaceAnalysis

        print("[face] loading InsightFace model…")
        self._app = FaceAnalysis(
            name="buffalo_l",
            providers=["CoreMLExecutionProvider", "CPUExecutionProvider"],
        )
        self._app.prepare(ctx_id=0, det_size=(160, 160))
        print("[face] ready")

    def embed_fragments(
        self,
        video_path: Path,
        fragments: Dict[int, List[Tuple[int, np.ndarray, float]]],
        sample_n: int = None,
    ) -> Dict[int, Optional[np.ndarray]]:
        """
        Returns: {track_id: 512-dim face embedding or None if no face found}
        """
        if sample_n is None:
            sample_n = settings.embedding_sample_frames

        # Build frame_idx -> [(track_id, xyxy, conf)]
        frame_index: Dict[int, List[Tuple[int, np.ndarray, float]]] = {}
        for tid, observations in fragments.items():
            for fidx, xyxy, conf in _uniform_sample(observations, sample_n):
                frame_index.setdefault(fidx, []).append((tid, xyxy, conf))

        if not frame_index:
            return {tid: None for tid in fragments}

        needed = set(frame_index.keys())
        embeddings_acc: Dict[int, List[Tuple[np.ndarray, float]]] = {tid: [] for tid in fragments}

        cap = cv2.VideoCapture(str(video_path))
        frame_idx = 0
        try:
            while needed:
                ret, frame = cap.read()
                if not ret:
                    break
                if frame_idx in needed:
                    needed.discard(frame_idx)
                    h, w = frame.shape[:2]
                    for tid, xyxy, conf in frame_index[frame_idx]:
                        x1 = max(0, int(xyxy[0]))
                        y1 = max(0, int(xyxy[1]))
                        x2 = min(w, int(xyxy[2]))
                        y2 = min(h, int(xyxy[3]))
                        if x2 <= x1 or y2 <= y1:
                            continue
                        crop = frame[y1:y2, x1:x2]
                        faces = self._app.get(crop)
                        if faces:
                            # Use the largest face (most likely the person in the bbox)
                            best = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
                            if best.embedding is not None:
                                emb = best.embedding / (np.linalg.norm(best.embedding) + 1e-8)
                                embeddings_acc[tid].append((emb.astype(np.float32), conf))
                frame_idx += 1
        finally:
            cap.release()

        result: Dict[int, Optional[np.ndarray]] = {}
        for tid, feats in embeddings_acc.items():
            if feats:
                vecs = np.array([f[0] for f in feats], dtype=np.float32)
                weights = np.array([f[1] for f in feats], dtype=np.float32)
                weights = weights / weights.sum()
                result[tid] = (vecs * weights[:, None]).sum(axis=0).astype(np.float32)
            else:
                result[tid] = None
        return result


def _uniform_sample(observations: List, n: int) -> List:
    if len(observations) <= n:
        return observations
    indices = np.linspace(0, len(observations) - 1, n, dtype=int)
    return [observations[i] for i in indices]
