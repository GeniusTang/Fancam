"""Extract ReID embeddings using BoxMOT's built-in ReID backend (no torchreid needed)."""
from pathlib import Path
from typing import Dict, List, Tuple

import cv2
import numpy as np

from core.config import settings


class ReIDEmbedder:
    def __init__(self):
        from boxmot import ReID
        from boxmot.reid.core.auto_backend import ReidAutoBackend
        import inspect
        import torch

        # Use boxmot's own default cache path so it downloads once to the right place
        default_weights = inspect.signature(ReidAutoBackend.__init__).parameters["weights"].default
        print(f"[reid] loading weights from {default_weights} (downloading if absent)…")
        self._reid = ReID(
            weights=default_weights,
            device=settings.device,
            half=False,
        )
        print("[reid] ready")

    def embed_fragments(
        self,
        video_path: Path,
        fragments: Dict[int, List[Tuple[int, np.ndarray]]],
        sample_n: int = None,
    ) -> Dict[int, np.ndarray]:
        """
        fragments: {track_id: [(frame_idx, xyxy), ...]}
        Returns: {track_id: mean_embedding}

        Uses a single sequential video pass to avoid expensive random seeks.
        """
        if sample_n is None:
            sample_n = settings.embedding_sample_frames

        # Build frame_idx -> [(track_id, xyxy)] using uniformly sampled frames
        frame_index: Dict[int, List[Tuple[int, np.ndarray]]] = {}
        for tid, observations in fragments.items():
            for fidx, xyxy in _uniform_sample(observations, sample_n):
                frame_index.setdefault(fidx, []).append((tid, xyxy))

        if not frame_index:
            return {tid: np.zeros(512, dtype=np.float32) for tid in fragments}

        needed = set(frame_index.keys())
        embeddings_acc: Dict[int, List[np.ndarray]] = {tid: [] for tid in fragments}

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
                    for tid, xyxy in frame_index[frame_idx]:
                        x1, y1, x2, y2 = xyxy
                        x1, y1 = max(0.0, x1), max(0.0, y1)
                        x2, y2 = min(float(w), x2), min(float(h), y2)
                        if x2 > x1 and y2 > y1:
                            valid.append((tid, np.array([x1, y1, x2, y2], dtype=np.float32)))
                    if valid:
                        dets = np.array([[*xyxy, 1.0, 0.0] for _, xyxy in valid], dtype=np.float32)
                        embs = self._reid(frame, dets)
                        for i, (tid, _) in enumerate(valid):
                            if i < len(embs):
                                embeddings_acc[tid].append(embs[i])
                frame_idx += 1
        finally:
            cap.release()

        result = {}
        for tid, feats in embeddings_acc.items():
            if feats:
                result[tid] = np.mean(feats, axis=0).astype(np.float32)
            else:
                result[tid] = np.zeros(512, dtype=np.float32)
        return result


def _uniform_sample(observations: List, n: int) -> List:
    if len(observations) <= n:
        return observations
    indices = np.linspace(0, len(observations) - 1, n, dtype=int)
    return [observations[i] for i in indices]
