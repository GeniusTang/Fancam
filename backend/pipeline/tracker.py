"""Deep OC-SORT tracker with osnet_x1_0 ReID backbone.

Deep OC-SORT extends OC-SORT with deep appearance features (ReID) for
re-identification after occlusion, plus virtual trajectory prediction
to handle crossings.

Returns per-frame track data: {track_id: {"xyxy": np.ndarray, "conf": float}}
"""
from typing import Dict, List, Any

import numpy as np

from core.config import settings


class Tracker:
    def __init__(self):
        from boxmot import DeepOcSort
        import torch

        print(f"[tracker] loading Deep OC-SORT with {settings.reid_model}…")
        self._tracker = DeepOcSort(
            reid_weights=settings.reid_model,
            device=torch.device(settings.device),
            half=True,
        )
        print("[tracker] ready")

    def update(self, frame: np.ndarray, detections: List[Dict[str, Any]]) -> Dict[int, Dict]:
        """
        detections: list of {"xyxy": np.ndarray(4,), "conf": float}
        Returns: {track_id: {"xyxy": ..., "conf": ...}}
        """
        if not detections:
            dets_np = np.empty((0, 6), dtype=np.float32)
        else:
            rows = []
            for d in detections:
                x1, y1, x2, y2 = [float(v) for v in d["xyxy"]]
                rows.append([x1, y1, x2, y2, float(d["conf"]), 0])  # class=0
            dets_np = np.array(rows, dtype=np.float64)

        tracks = self._tracker.update(dets_np, frame)
        result = {}
        if tracks is not None and len(tracks) > 0:
            for t in tracks:
                # BoxMOT output: [x1, y1, x2, y2, track_id, conf, cls, ...]
                tid = int(t[4])
                result[tid] = {
                    "xyxy": t[:4].astype(np.float32),
                    "conf": float(t[5]),
                }
        return result
