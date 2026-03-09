"""YOLO person detector — yields (frame_idx, total_frames, frame, detections) per frame."""
from pathlib import Path
from typing import Generator, List, Tuple

import cv2
import numpy as np
from ultralytics import YOLO

from core.config import settings


class Detector:
    def __init__(self):
        self._model = YOLO(settings.yolo_model)

    def detect_video(
        self, video_path: Path,
    ) -> Generator[Tuple[int, int, np.ndarray, List[dict]], None, None]:
        """Yields (frame_idx, total_frames, frame, [detection dicts]) for each frame."""
        cap = cv2.VideoCapture(str(video_path))
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        frame_idx = 0
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                h, w = frame.shape[:2]
                frame_area = h * w
                results = self._model(
                    frame, classes=[0], verbose=False,
                    device=settings.device, conf=settings.yolo_conf,
                    imgsz=960, half=True,
                )
                boxes = []
                for r in results:
                    if r.boxes is None:
                        continue
                    for box in r.boxes:
                        xyxy = box.xyxy[0].cpu().numpy()
                        x1, y1, x2, y2 = xyxy
                        box_area = (x2 - x1) * (y2 - y1)
                        rel_area = box_area / frame_area
                        if rel_area < settings.min_person_area or rel_area > settings.max_person_area:
                            continue
                        if (y2 - y1) < h * 0.10:
                            continue
                        boxes.append({"xyxy": xyxy, "conf": float(box.conf[0])})
                yield frame_idx, total, frame, boxes
                frame_idx += 1
        finally:
            cap.release()
