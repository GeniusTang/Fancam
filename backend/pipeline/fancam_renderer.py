"""Fancam renderer: crop + bidirectional Gaussian smoothing + H.264 encode with audio.

Two-pass architecture:
  1. Collect all bbox data for the selected person across all frames
  2. Apply scipy.ndimage.gaussian_filter1d on full cx/cy/w/h arrays — zero-lag,
     uses both past and future context for silky-smooth camera movement
  3. Pipe raw cropped frames directly to ffmpeg (single H.264 encode, no lossy intermediate)
"""
import platform
import subprocess
from pathlib import Path
from typing import Callable, Dict, Optional

import cv2
import numpy as np
from scipy.ndimage import gaussian_filter1d

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
        cuts: list | None = None,
    ) -> Path:
        cap = cv2.VideoCapture(str(video_path))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()

        # Build set of frames to skip (cuts)
        cut_frames: set[int] = set()
        for c in (cuts or []):
            for f in range(c["start"], c["end"] + 1):
                cut_frames.add(f)
        kept_count = total - len(cut_frames)
        if cuts:
            print(f"[render] {len(cut_frames)} frames cut, {kept_count} kept")

        # Scale output to match source quality (9:16 portrait)
        self.out_h = min(frame_h, max(self.out_h, frame_h))
        self.out_w = int(self.out_h * 9 / 16)
        self.out_w = self.out_w + (self.out_w % 2)
        self.out_h = self.out_h + (self.out_h % 2)
        print(f"[render] output resolution: {self.out_w}x{self.out_h} (source: {frame_w}x{frame_h})")

        # ── Pass 1: Build smoothed camera path ──────────────────────────
        cam_path = self._build_camera_path(frame_track_map, total, frame_w, frame_h)

        # ── Pass 2: Pipe raw frames to ffmpeg ────────────────────────────
        kept_segments = _compute_kept_segments(cuts or [], total) if cut_frames else None
        ffmpeg_cmd = _build_ffmpeg_cmd(
            output_path, self.out_w, self.out_h, fps, video_path,
            kept_segments=kept_segments,
        )
        print(f"[render] ffmpeg cmd: {' '.join(ffmpeg_cmd)}")

        proc = subprocess.Popen(
            ffmpeg_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        cap = cv2.VideoCapture(str(video_path))
        written = 0

        try:
            for frame_idx in range(total):
                ret, frame = cap.read()
                if not ret:
                    break

                if frame_idx in cut_frames:
                    continue

                cam = cam_path[frame_idx]
                if cam is not None:
                    out_frame = self._crop_frame(frame, cam, frame_w, frame_h)
                else:
                    out_frame = self._letterbox(frame)

                proc.stdin.write(out_frame.tobytes())
                written += 1

                if progress_cb and kept_count > 0:
                    progress_cb(written / kept_count)
        finally:
            cap.release()
            proc.stdin.close()
            proc.wait()

        if proc.returncode != 0:
            print(f"[render] ffmpeg failed (rc={proc.returncode}), retrying without audio")
            ffmpeg_cmd = _build_ffmpeg_cmd(
                output_path, self.out_w, self.out_h, fps, None,
            )
            proc = subprocess.Popen(
                ffmpeg_cmd, stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            cap = cv2.VideoCapture(str(video_path))
            try:
                for frame_idx in range(total):
                    ret, frame = cap.read()
                    if not ret:
                        break
                    if frame_idx in cut_frames:
                        continue
                    cam = cam_path[frame_idx]
                    if cam is not None:
                        out_frame = self._crop_frame(frame, cam, frame_w, frame_h)
                    else:
                        out_frame = self._letterbox(frame)
                    proc.stdin.write(out_frame.tobytes())
            finally:
                cap.release()
                proc.stdin.close()
                proc.wait()

        return output_path

    def _build_camera_path(
        self,
        frame_track_map: Dict[int, np.ndarray],
        total_frames: int,
        frame_w: int,
        frame_h: int,
    ) -> list:
        if not frame_track_map:
            return [None] * total_frames

        raw_cams = {}
        for fidx, xyxy in frame_track_map.items():
            raw_cams[fidx] = _xyxy_to_cam(xyxy, frame_w, frame_h, self.out_w, self.out_h)

        sorted_frames = sorted(raw_cams.keys())
        first_frame = sorted_frames[0]
        last_frame = sorted_frames[-1]
        span = last_frame - first_frame + 1

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

        for arr in [cx_arr, cy_arr, cw_arr, ch_arr]:
            _interpolate_nans(arr)

        sigma = self.sigma
        cx_smooth = gaussian_filter1d(cx_arr, sigma)
        cy_smooth = gaussian_filter1d(cy_arr, sigma)
        cw_smooth = gaussian_filter1d(cw_arr, sigma)
        ch_smooth = gaussian_filter1d(ch_arr, sigma)

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


_USE_VIDEOTOOLBOX = _has_videotoolbox()


def _probe_bitrate(video_path: Path) -> int:
    """Get source video bitrate in bits/s. Returns 0 on failure."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-select_streams", "v:0",
             "-show_entries", "format=bit_rate",
             "-of", "csv=p=0", str(video_path)],
            capture_output=True, text=True, timeout=10,
        )
        val = result.stdout.strip()
        if val and val != "N/A":
            return int(val)
    except Exception:
        pass
    return 0


def _compute_kept_segments(cuts: list, total_frames: int) -> list[tuple[int, int]]:
    """Given cut ranges, return sorted list of (start, end_inclusive) kept frame segments."""
    if not cuts:
        return [(0, total_frames - 1)]

    cut_frames: set[int] = set()
    for c in cuts:
        for f in range(c["start"], c["end"] + 1):
            cut_frames.add(f)

    segments = []
    in_seg = False
    seg_start = 0
    for f in range(total_frames):
        if f not in cut_frames:
            if not in_seg:
                seg_start = f
                in_seg = True
        else:
            if in_seg:
                segments.append((seg_start, f - 1))
                in_seg = False
    if in_seg:
        segments.append((seg_start, total_frames - 1))
    return segments


def _build_ffmpeg_cmd(
    output_path: Path,
    width: int,
    height: int,
    fps: float,
    source_video: Optional[Path],
    kept_segments: list[tuple[int, int]] | None = None,
) -> list:
    """Build ffmpeg command that reads raw BGR frames from stdin."""
    # Probe source bitrate to match quality
    source_bps = _probe_bitrate(source_video) if source_video else 0
    # Use at least source bitrate, minimum 15 Mbps
    target_bps = max(source_bps, 15_000_000)
    target_bitrate = f"{target_bps // 1_000_000}M"

    if _USE_VIDEOTOOLBOX:
        vcodec = "h264_videotoolbox"
        codec_args = ["-b:v", target_bitrate]
        print(f"[render] h264_videotoolbox, bitrate={target_bitrate} (source={source_bps // 1_000_000}M)")
    else:
        vcodec = "libx264"
        # CRF 15 = near-visually-lossless, with bitrate floor
        codec_args = ["-crf", "15", "-preset", "slow", "-bufsize", target_bitrate, "-maxrate", target_bitrate]
        print(f"[render] libx264 CRF 15, maxrate={target_bitrate} (source={source_bps // 1_000_000}M)")

    cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo",
        "-pix_fmt", "bgr24",
        "-s", f"{width}x{height}",
        "-r", str(fps),
        "-i", "pipe:0",
    ]

    if source_video:
        cmd += ["-i", str(source_video)]

    cmd += [
        "-vcodec", vcodec,
        *codec_args,
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
    ]

    if source_video and kept_segments and len(kept_segments) > 1:
        # Build audio filter to trim and concat matching segments
        filter_parts = []
        for i, (seg_start, seg_end) in enumerate(kept_segments):
            t0 = seg_start / fps
            t1 = (seg_end + 1) / fps
            filter_parts.append(
                f"[1:a]atrim=start={t0:.6f}:end={t1:.6f},asetpts=PTS-STARTPTS[a{i}]"
            )
        concat_inputs = "".join(f"[a{i}]" for i in range(len(kept_segments)))
        filter_parts.append(f"{concat_inputs}concat=n={len(kept_segments)}:v=0:a=1[aout]")
        filter_str = ";".join(filter_parts)
        cmd += [
            "-filter_complex", filter_str,
            "-map", "0:v:0",
            "-map", "[aout]",
            "-acodec", "aac",
            "-b:a", "256k",
        ]
    elif source_video:
        cmd += [
            "-map", "0:v:0",
            "-map", "1:a:0?",
            "-acodec", "aac",
            "-b:a", "256k",
            "-shortest",
        ]

    cmd.append(str(output_path))
    return cmd
