"""Fancam renderer: crop + smooth camera + H.264 encode with audio."""
from pathlib import Path
from typing import Callable, Dict, Optional

import cv2
import numpy as np
import ffmpeg

from core.config import settings
from pipeline.kalman_predictor import KalmanPredictor


class FancamRenderer:
    def __init__(self):
        self.out_w = settings.fancam_width
        self.out_h = settings.fancam_height
        self.ema_alpha = settings.ema_alpha
        self.occlusion_limit = settings.kalman_occlusion_limit

    def render(
        self,
        video_path: Path,
        output_path: Path,
        frame_track_map: Dict[int, np.ndarray],
        progress_cb: Optional[Callable[[float], None]] = None,
    ) -> Path:
        cap = cv2.VideoCapture(str(video_path))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        temp_path = output_path.with_suffix(".raw.mp4")
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(temp_path), fourcc, fps, (self.out_w, self.out_h))

        kalman = KalmanPredictor()
        cam: Optional[np.ndarray] = None
        occlusion_count = 0

        for frame_idx in range(total):
            ret, frame = cap.read()
            if not ret:
                break

            xyxy = frame_track_map.get(frame_idx)

            if xyxy is not None:
                smooth_xyxy = kalman.update(xyxy)
                occlusion_count = 0
            elif kalman.initialized and occlusion_count < self.occlusion_limit:
                smooth_xyxy = kalman.predict()
                occlusion_count += 1
            elif cam is not None:
                smooth_xyxy = _cam_to_xyxy(cam)
                occlusion_count += 1
            else:
                writer.write(self._letterbox(frame))
                if progress_cb and total > 0:
                    progress_cb(frame_idx / total)
                continue

            target_cam = _xyxy_to_cam(smooth_xyxy, frame_w, frame_h, self.out_w, self.out_h)
            cam = target_cam if cam is None else (
                self.ema_alpha * target_cam + (1 - self.ema_alpha) * cam
            )

            writer.write(self._crop_frame(frame, cam, frame_w, frame_h))

            if progress_cb and total > 0:
                progress_cb(frame_idx / total)

        cap.release()
        writer.release()

        _reencode(temp_path, output_path, fps, video_path)
        temp_path.unlink(missing_ok=True)
        return output_path

    def _crop_frame(self, frame: np.ndarray, cam: np.ndarray, fw: int, fh: int) -> np.ndarray:
        cx, cy, cw, ch = cam
        x1 = int(round(cx - cw / 2))
        y1 = int(round(cy - ch / 2))
        x2 = x1 + int(round(cw))
        y2 = y1 + int(round(ch))

        # Pad with black instead of clamping, so dancer stays centred
        pad_l = max(0, -x1)
        pad_t = max(0, -y1)
        pad_r = max(0, x2 - fw)
        pad_b = max(0, y2 - fh)

        cx1, cy1 = max(0, x1), max(0, y1)
        cx2, cy2 = min(fw, x2), min(fh, y2)

        crop = frame[cy1:cy2, cx1:cx2]
        if crop.size == 0:
            return self._letterbox(frame)

        if pad_l or pad_t or pad_r or pad_b:
            crop = cv2.copyMakeBorder(
                crop, pad_t, pad_b, pad_l, pad_r,
                cv2.BORDER_CONSTANT, value=(0, 0, 0)
            )

        return cv2.resize(crop, (self.out_w, self.out_h), interpolation=cv2.INTER_LINEAR)

    def _letterbox(self, frame: np.ndarray) -> np.ndarray:
        h, w = frame.shape[:2]
        ratio = self.out_w / self.out_h
        if w / h > ratio:
            nw = int(h * ratio)
            frame = frame[:, (w - nw) // 2:(w - nw) // 2 + nw]
        else:
            nh = int(w / ratio)
            frame = frame[(h - nh) // 2:(h - nh) // 2 + nh, :]
        return cv2.resize(frame, (self.out_w, self.out_h))


def _xyxy_to_cam(xyxy: np.ndarray, fw: int, fh: int, out_w: int, out_h: int) -> np.ndarray:
    x1, y1, x2, y2 = xyxy
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    pw, ph = x2 - x1, y2 - y1
    ratio = out_w / out_h

    raw_w = pw * 1.5
    raw_h = ph * 1.5
    # Enforce portrait aspect ratio
    if raw_w / max(raw_h, 1) > ratio:
        raw_h = raw_w / ratio
    else:
        raw_w = raw_h * ratio

    return np.array([cx, cy, raw_w, raw_h], dtype=np.float32)


def _cam_to_xyxy(cam: np.ndarray) -> np.ndarray:
    cx, cy, w, h = cam
    return np.array([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], dtype=np.float32)


def _reencode(src: Path, dst: Path, fps: float, source_video: Path):
    """Re-encode to H.264 and mux original audio."""
    try:
        video_in = ffmpeg.input(str(src))
        audio_in = ffmpeg.input(str(source_video))
        (
            ffmpeg
            .output(
                video_in.video,
                audio_in.audio,
                str(dst),
                vcodec="libx264",
                acodec="aac",
                audio_bitrate="192k",
                crf=23,
                preset="fast",
                movflags="+faststart",
                r=fps,
                shortest=None,
            )
            .overwrite_output()
            .run(quiet=True)
        )
    except ffmpeg.Error:
        # Fallback: video only
        try:
            (
                ffmpeg.input(str(src))
                .output(str(dst), vcodec="libx264", crf=23, preset="fast",
                        movflags="+faststart", r=fps)
                .overwrite_output()
                .run(quiet=True)
            )
        except ffmpeg.Error:
            import shutil
            shutil.copy2(src, dst)
