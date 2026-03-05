"""Score and save best thumbnail crop per person cluster."""
from pathlib import Path
from typing import Dict, List, Tuple

import cv2
import numpy as np

from storage.file_manager import thumbnail_path


def _sharpness(crop: np.ndarray) -> float:
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _score(crop: np.ndarray, conf: float, frame_w: int, frame_h: int, xyxy: np.ndarray) -> float:
    x1, y1, x2, y2 = xyxy
    area = (x2 - x1) * (y2 - y1) / (frame_w * frame_h)
    # Edge margin (0=touching edge, 1=fully inside)
    margin_x = min(x1 / frame_w, (frame_w - x2) / frame_w)
    margin_y = min(y1 / frame_h, (frame_h - y2) / frame_h)
    edge_score = max(0.0, min(margin_x, margin_y) * 4)  # normalize to ~1
    sharp = min(_sharpness(crop) / 500.0, 2.0)
    return sharp * 0.4 + area * 0.3 + conf * 0.2 + edge_score * 0.1


def generate_thumbnails(
    job_id: str,
    video_path: Path,
    cluster_observations: Dict[int, List[Tuple[int, np.ndarray, float]]],
    # {cluster_id: [(frame_idx, xyxy, conf), ...]}
    person_ids: Dict[int, str],
    # {cluster_id: person_id}
) -> Dict[str, str]:
    """Returns {person_id: thumbnail_file_path_str}."""
    cap = cv2.VideoCapture(str(video_path))
    frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    # Build frame→[(cluster_id, xyxy, conf)] index
    frame_index: Dict[int, List[Tuple[int, np.ndarray, float]]] = {}
    for cid, obs_list in cluster_observations.items():
        for fidx, xyxy, conf in obs_list:
            frame_index.setdefault(fidx, []).append((cid, xyxy, conf))

    best: Dict[int, Tuple[float, np.ndarray]] = {}  # cluster_id -> (score, crop)

    # Sequential pass — avoid slow random seeks on compressed video
    needed = set(frame_index.keys())
    frame_idx = 0
    while needed:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx in needed:
            needed.discard(frame_idx)
            h, w = frame.shape[:2]
            for cid, xyxy, conf in frame_index[frame_idx]:
                crop = _safe_crop(frame, xyxy, h, w)
                if crop is None or crop.size == 0:
                    continue
                s = _score(crop, conf, w, h, xyxy)
                if cid not in best or s > best[cid][0]:
                    best[cid] = (s, crop.copy())
        frame_idx += 1

    cap.release()

    result = {}
    for cid, (_, crop) in best.items():
        pid = person_ids.get(cid)
        if pid is None:
            continue
        out_path = thumbnail_path(job_id, pid)
        cv2.imwrite(str(out_path), crop)
        result[pid] = str(out_path)

    return result


def _safe_crop(frame: np.ndarray, xyxy: np.ndarray, h: int, w: int):
    x1, y1, x2, y2 = xyxy
    x1, y1 = max(0, int(x1)), max(0, int(y1))
    x2, y2 = min(w, int(x2)), min(h, int(y2))
    if x2 <= x1 or y2 <= y1:
        return None
    return frame[y1:y2, x1:x2]
