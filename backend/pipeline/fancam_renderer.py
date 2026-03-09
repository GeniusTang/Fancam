"""Fancam renderer: crop + bidirectional Gaussian smoothing + H.264 encode with audio.

Two-pass architecture:
  1. Collect all bbox data for the selected person across all frames
  2. Apply scipy.ndimage.gaussian_filter1d on full cx/cy/w/h arrays — zero-lag,
     uses both past and future context for silky-smooth camera movement
  3. Render cropped frames using the smoothed camera path

No Kalman filter, no EMA, no velocity clamping — the Gaussian filter handles
everything in a single non-causal pass.
"""
import platform
import subprocess
from pathlib import Path
from typing import Callable, Dict, Optional

import cv2
import numpy as np
from scipy.ndimage import gaussian_filter1d
import ffmpeg

from core.config import settings


class FancamRenderer:
    def __init__(self):
        self.out_w = settings.fancam_width
        self.out_h = settings.fancam_height
        self.sigma = settings.gaussian_sigma

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
        cap.release()

        # Scale output to match source quality (9:16 portrait)
        # Use source height as the output height, capped at source dimensions
        self.out_h = min(frame_h, max(self.out_h, frame_h))
        self.out_w = int(self.out_h * 9 / 16)
        # Ensure even dimensions for H.264
        self.out_w = self.out_w + (self.out_w % 2)
        self.out_h = self.out_h + (self.out_h % 2)
        print(f"[render] output resolution: {self.out_w}x{self.out_h} (source: {frame_w}x{frame_h})")

        # ── Pass 1: Build smoothed camera path ──────────────────────────
        cam_path = self._build_camera_path(frame_track_map, total, frame_w, frame_h)

        # ── Pass 2: Render frames using smoothed camera ─────────────────
        cap = cv2.VideoCapture(str(video_path))
        temp_path = output_path.with_suffix(".raw.mp4")
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(temp_path), fourcc, fps, (self.out_w, self.out_h))

        for frame_idx in range(total):
            ret, frame = cap.read()
            if not ret:
                break

            cam = cam_path[frame_idx]
            if cam is not None:
                writer.write(self._crop_frame(frame, cam, frame_w, frame_h))
            else:
                writer.write(self._letterbox(frame))

            if progress_cb and total > 0:
                progress_cb(frame_idx / total)

        cap.release()
        writer.release()

        _reencode(temp_path, output_path, fps, video_path)
        temp_path.unlink(missing_ok=True)
        return output_path

    def _build_camera_path(
        self,
        frame_track_map: Dict[int, np.ndarray],
        total_frames: int,
        frame_w: int,
        frame_h: int,
    ) -> list:
        """Build a smoothed camera path for all frames.

        Returns a list of length total_frames where each element is either
        a np.ndarray [cx, cy, cw, ch] or None (no person visible).
        """
        if not frame_track_map:
            return [None] * total_frames

        # Convert all detections to camera targets [cx, cy, cw, ch]
        raw_cams = {}
        for fidx, xyxy in frame_track_map.items():
            raw_cams[fidx] = _xyxy_to_cam(xyxy, frame_w, frame_h, self.out_w, self.out_h)

        # Find contiguous segments where the person is visible
        sorted_frames = sorted(raw_cams.keys())
        first_frame = sorted_frames[0]
        last_frame = sorted_frames[-1]
        span = last_frame - first_frame + 1

        # Build dense arrays for the active span, interpolating gaps
        cx_arr = np.full(span, np.nan, dtype=np.float64)
        cy_arr = np.full(span, np.nan, dtype=np.float64)
        cw_arr = np.full(span, np.nan, dtype=np.float64)
        ch_arr = np.full(span, np.nan, dtype=np.float64)

        for fidx, cam in raw_cams.items():
            i = fidx - first_frame
            cx_arr[i] = cam[0]
            cy_arr[i] = cam[1]
            cw_arr[i] = cam[2]
            ch_arr[i] = cam[3]

        # Interpolate gaps (occlusion periods)
        for arr in [cx_arr, cy_arr, cw_arr, ch_arr]:
            _interpolate_nans(arr)

        # Apply Gaussian smoothing — zero-lag bidirectional filter
        sigma = self.sigma
        cx_smooth = gaussian_filter1d(cx_arr, sigma)
        cy_smooth = gaussian_filter1d(cy_arr, sigma)
        cw_smooth = gaussian_filter1d(cw_arr, sigma)
        ch_smooth = gaussian_filter1d(ch_arr, sigma)

        # Build output camera path
        cam_path: list = [None] * total_frames
        for i in range(span):
            fidx = first_frame + i
            if fidx < total_frames:
                cam_path[fidx] = np.array(
                    [cx_smooth[i], cy_smooth[i], cw_smooth[i], ch_smooth[i]],
                    dtype=np.float32,
                )

        return cam_path

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

        return cv2.resize(crop, (self.out_w, self.out_h), interpolation=cv2.INTER_LANCZOS4)

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


def _interpolate_nans(arr: np.ndarray):
    """In-place linear interpolation of NaN gaps in a 1D array."""
    nans = np.isnan(arr)
    if not nans.any():
        return
    if nans.all():
        arr[:] = 0
        return
    not_nan = ~nans
    indices = np.arange(len(arr))
    arr[nans] = np.interp(indices[nans], indices[not_nan], arr[not_nan])


def _xyxy_to_cam(xyxy: np.ndarray, fw: int, fh: int, out_w: int, out_h: int) -> np.ndarray:
    x1, y1, x2, y2 = xyxy
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    pw, ph = x2 - x1, y2 - y1
    ratio = out_w / out_h

    raw_w = pw * 1.5
    raw_h = ph * 1.5
    if raw_w / max(raw_h, 1) > ratio:
        raw_h = raw_w / ratio
    else:
        raw_w = raw_h * ratio

    return np.array([cx, cy, raw_w, raw_h], dtype=np.float32)


def _has_videotoolbox() -> bool:
    """Check if h264_videotoolbox encoder is available."""
    if platform.system() != "Darwin":
        return False
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=5,
        )
        return "h264_videotoolbox" in result.stdout
    except Exception:
        return False


# Cache the check at module load
_USE_VIDEOTOOLBOX = _has_videotoolbox()


def _reencode(src: Path, dst: Path, fps: float, source_video: Path):
    """Re-encode to H.264 (hardware-accelerated on macOS) and mux original audio."""
    if _USE_VIDEOTOOLBOX:
        vcodec = "h264_videotoolbox"
        codec_opts = {"q:v": "65"}  # videotoolbox quality (lower = better, 1-100)
        print("[render] using h264_videotoolbox (hardware encoder)")
    else:
        vcodec = "libx264"
        codec_opts = {"crf": "23", "preset": "fast"}
        print("[render] using libx264 (software encoder)")

    try:
        video_in = ffmpeg.input(str(src))
        audio_in = ffmpeg.input(str(source_video))
        (
            ffmpeg
            .output(
                video_in.video,
                audio_in.audio,
                str(dst),
                vcodec=vcodec,
                acodec="aac",
                audio_bitrate="192k",
                movflags="+faststart",
                r=fps,
                shortest=None,
                **codec_opts,
            )
            .overwrite_output()
            .run(quiet=True)
        )
    except ffmpeg.Error:
        # Fallback: try without audio
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
