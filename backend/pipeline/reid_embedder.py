"""Extract ReID embeddings using BoxMOT's built-in ReID backend.

Uses confidence-weighted mean: detections with higher YOLO confidence
contribute more to the final embedding (they're likely better crops).
"""
from pathlib import Path
from typing import Dict, List, Tuple

import cv2
import numpy as np

from core.config import settings


class ReIDEmbedder:
    def __init__(self):
        from boxmot import ReID
        import torch

        print(f"[reid] loading weights from {settings.reid_model}…")
        self._reid = ReID(
            weights=settings.reid_model,
            device=settings.device,
            half=False,
        )
        print("[reid] ready")

    def embed_fragments(
        self,
        video_path: Path,
        fragments: Dict[int, List[Tuple[int, np.ndarray, float]]],
        sample_n: int = None,
    ) -> Dict[int, np.ndarray]:
        """
        fragments: {track_id: [(frame_idx, xyxy, conf), ...]}
        Returns: {track_id: confidence-weighted mean embedding}

        Uses a single sequential video pass to avoid expensive random seeks.
        """
        if sample_n is None:
            sample_n = settings.embedding_sample_frames

        # Build frame_idx -> [(track_id, xyxy, conf)] using uniformly sampled frames
        frame_index: Dict[int, List[Tuple[int, np.ndarray, float]]] = {}
        for tid, observations in fragments.items():
            for fidx, xyxy, conf in _uniform_sample(observations, sample_n):
                frame_index.setdefault(fidx, []).append((tid, xyxy, conf))

        if not frame_index:
            return {tid: np.zeros(512, dtype=np.float32) for tid in fragments}

        needed = set(frame_index.keys())
        embeddings_acc: Dict[int, List[Tuple[np.ndarray, float]]] = {tid: [] for tid in fragments}

        # Sequential pass — no seeking
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
                    valid = []
                    for tid, xyxy, conf in frame_index[frame_idx]:
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
                                embeddings_acc[tid].append((embs[i], conf))
                frame_idx += 1
        finally:
            cap.release()

        result = {}
        for tid, feats in embeddings_acc.items():
            if feats:
                vecs = np.array([f[0] for f in feats], dtype=np.float32)
                weights = np.array([f[1] for f in feats], dtype=np.float32)
                weights = weights / weights.sum()  # normalize
                result[tid] = (vecs * weights[:, None]).sum(axis=0).astype(np.float32)
            else:
                result[tid] = np.zeros(512, dtype=np.float32)
        return result


def _uniform_sample(observations: List, n: int) -> List:
    if len(observations) <= n:
        return observations
    indices = np.linspace(0, len(observations) - 1, n, dtype=int)
    return [observations[i] for i in indices]
