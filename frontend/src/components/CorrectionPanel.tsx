import React, { useCallback, useEffect, useRef, useState } from "react";
import { useAppStore } from "../store/appStore";
import {
  fetchTrackData,
  frameSrc,
  fetchFrameBboxes,
  fetchAllBboxes,
  redirectTracking,
  undoRedirect,
} from "../api/corrections";
import { startGeneration } from "../api/generate";
import type {
  CutSection,
  FrameBbox,
  JumpInfo,
  TrackDataResponse,
  VideoInfo,
} from "../types";

// ── Types ───────────────────────────────────────────────────────────────────

type PlayState = "playing" | "paused";

// ── Component ───────────────────────────────────────────────────────────────

export function CorrectionPanel() {
  const jobId = useAppStore((s) => s.jobId)!;
  const personId = useAppStore((s) => s.selectedPersonId)!;
  const setPhase = useAppStore((s) => s.setPhase);
  const setError = useAppStore((s) => s.setError);

  // Track data
  const [trackMap, setTrackMap] = useState<
    Record<number, [number, number, number, number]>
  >({});
  const [jumps, setJumps] = useState<JumpInfo[]>([]);
  const [videoInfo, setVideoInfo] = useState<VideoInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [redirectCount, setRedirectCount] = useState(0);

  // Playback state
  const [playState, setPlayState] = useState<PlayState>("paused");
  const [currentFrame, setCurrentFrame] = useState(0);
  const [frameBboxes, setFrameBboxes] = useState<FrameBbox[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const [cuts, setCuts] = useState<CutSection[]>([]);
  const [cutStart, setCutStart] = useState<number | null>(null);

  // Canvas + Video
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const frameImgRef = useRef<HTMLImageElement | null>(null);

  // Playback refs (avoid stale closures)
  const playStateRef = useRef<PlayState>("paused");
  const currentFrameRef = useRef(0);
  const animFrameRef = useRef<number>(0);
  const bboxDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const trackMapRef = useRef(trackMap);
  trackMapRef.current = trackMap;

  // All bboxes for playback overlay
  const allBboxesRef = useRef<Record<number, FrameBbox[]>>({});


  // ── Load track data ─────────────────────────────────────────────────────

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data: TrackDataResponse = await fetchTrackData(jobId, personId);
        if (cancelled) return;
        const map: Record<number, [number, number, number, number]> = {};
        for (const [k, v] of Object.entries(data.frame_track_map)) {
          map[Number(k)] = v as [number, number, number, number];
        }
        setTrackMap(map);
        setJumps(data.jumps);
        setVideoInfo(data.video_info);
        setCurrentFrame(0);
        currentFrameRef.current = 0;
        // Load all bboxes for playback overlay
        fetchAllBboxes(jobId).then((all) => {
          allBboxesRef.current = all;
        }).catch(() => {});
        setLoading(false);
      } catch (e) {
        if (!cancelled)
          setError(e instanceof Error ? e.message : "Failed to load track data");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [jobId, personId]);

  // ── Canvas dimensions ──────────────────────────────────────────────────

  const dpr = window.devicePixelRatio || 1;
  const displayWidth = Math.min(960, window.innerWidth - 300);
  const displayHeight = videoInfo
    ? Math.round(displayWidth * (videoInfo.height / videoInfo.width))
    : 540;
  // Canvas pixel buffer at full resolution for sharpness
  const canvasWidth = Math.round(displayWidth * dpr);
  const canvasHeight = Math.round(displayHeight * dpr);

  // ── Draw helpers ──────────────────────────────────────────────────────

  const drawBboxOverlay = useCallback(
    (frame: number, bboxes?: FrameBbox[]) => {
      const canvas = canvasRef.current;
      if (!canvas || !videoInfo) return;

      const ctx = canvas.getContext("2d")!;
      const cw = canvas.width;
      const ch = canvas.height;
      const scaleX = cw / videoInfo.width;
      const scaleY = ch / videoInfo.height;

      if (playStateRef.current === "playing") {
        // Playing: show all dancers' boxes
        const tracked = trackMapRef.current[frame];
        const others = allBboxesRef.current[frame] || [];

        // Find which bbox matches the tracked position
        let trackedIdx = -1;
        if (tracked) {
          let bestDist = Infinity;
          const [tx1, ty1, tx2, ty2] = tracked;
          const tcx = (tx1 + tx2) / 2, tcy = (ty1 + ty2) / 2;
          for (let i = 0; i < others.length; i++) {
            const [bx1, by1, bx2, by2] = others[i].xyxy;
            const d = Math.hypot(tcx - (bx1 + bx2) / 2, tcy - (by1 + by2) / 2);
            if (d < bestDist) { bestDist = d; trackedIdx = i; }
          }
        }

        // Draw other dancers first (orange, thinner)
        for (let i = 0; i < others.length; i++) {
          if (i === trackedIdx) continue;
          const [x1, y1, x2, y2] = others[i].xyxy;
          ctx.lineWidth = 1.5;
          ctx.strokeStyle = "rgba(249,115,22,0.5)";
          ctx.strokeRect(
            x1 * scaleX, y1 * scaleY,
            (x2 - x1) * scaleX, (y2 - y1) * scaleY
          );
        }

        // Draw tracked person on top (green, thicker)
        if (tracked) {
          const [x1, y1, x2, y2] = tracked;
          ctx.lineWidth = 3;
          ctx.strokeStyle = "#22c55e";
          ctx.strokeRect(
            x1 * scaleX, y1 * scaleY,
            (x2 - x1) * scaleX, (y2 - y1) * scaleY
          );
        }
      } else {
        // Paused: show ALL bboxes, highlight the one matching trackMap
        const allBboxes = bboxes || frameBboxes;
        const tracked = trackMapRef.current[frame];

        // Find which bbox matches the tracked position (if any)
        let selectedIdx = -1;
        if (tracked) {
          let bestDist = Infinity;
          const [tx1, ty1, tx2, ty2] = tracked;
          const tcx = (tx1 + tx2) / 2, tcy = (ty1 + ty2) / 2;
          for (let i = 0; i < allBboxes.length; i++) {
            const [bx1, by1, bx2, by2] = allBboxes[i].xyxy;
            const bcx = (bx1 + bx2) / 2, bcy = (by1 + by2) / 2;
            const d = Math.hypot(tcx - bcx, tcy - bcy);
            if (d < bestDist) { bestDist = d; selectedIdx = i; }
          }
        }

        for (let i = 0; i < allBboxes.length; i++) {
          const bbox = allBboxes[i];
          const [x1, y1, x2, y2] = bbox.xyxy;
          const isSelected = i === selectedIdx;
          ctx.lineWidth = isSelected ? 3 : 2;
          ctx.strokeStyle = isSelected ? "#22c55e" : "#f97316";
          ctx.strokeRect(
            x1 * scaleX,
            y1 * scaleY,
            (x2 - x1) * scaleX,
            (y2 - y1) * scaleY
          );

          // Label
          const label = isSelected
            ? "tracking"
            : bbox.person_id || `track ${bbox.track_id}`;
          const labelX = x1 * scaleX;
          const labelY = y1 * scaleY - 4;
          ctx.font = "12px monospace";
          const metrics = ctx.measureText(label);
          ctx.fillStyle = isSelected
            ? "rgba(34,197,94,0.8)"
            : "rgba(249,115,22,0.8)";
          ctx.fillRect(labelX, labelY - 13, metrics.width + 8, 16);
          ctx.fillStyle = "#fff";
          ctx.fillText(label, labelX + 4, labelY);
        }
      }

      // Frame number overlay
      ctx.fillStyle = "rgba(0,0,0,0.6)";
      ctx.fillRect(0, 0, 160, 28);
      ctx.fillStyle = "#fff";
      ctx.font = "13px monospace";
      ctx.fillText(
        `Frame ${frame}${playStateRef.current === "paused" ? " (paused)" : ""}`,
        8,
        19
      );
    },
    [videoInfo, frameBboxes, personId]
  );

  // Draw a static image to canvas (used when paused)
  const drawImageFrame = useCallback(
    (img: HTMLImageElement, frame: number, bboxes?: FrameBbox[]) => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext("2d")!;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      drawBboxOverlay(frame, bboxes);
    },
    [drawBboxOverlay]
  );

  // ── Frame loading (only for pause/step — uses JPEG endpoint) ──────────

  const loadFrame = useCallback(
    (frameIdx: number): Promise<HTMLImageElement> => {
      return new Promise((resolve, reject) => {
        const img = new Image();
        img.crossOrigin = "anonymous";
        img.onload = () => resolve(img);
        img.onerror = reject;
        img.src = frameSrc(jobId, frameIdx);
      });
    },
    [jobId]
  );

  // Debounced bbox fetch
  const debouncedFetchBboxes = useCallback(
    (frame: number, img: HTMLImageElement) => {
      if (bboxDebounceRef.current) clearTimeout(bboxDebounceRef.current);
      bboxDebounceRef.current = setTimeout(async () => {
        try {
          const bboxes = await fetchFrameBboxes(jobId, frame);
          setFrameBboxes(bboxes);
          if (playStateRef.current === "paused") {
            drawImageFrame(img, frame, bboxes);
          }
        } catch {
          // best effort
        }
      }, 150);
    },
    [jobId, drawImageFrame]
  );

  // ── Video playback loop ────────────────────────────────────────────────

  const playLoop = useCallback(() => {
    if (playStateRef.current !== "playing" || !videoInfo) return;

    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return;

    const frame = Math.round(video.currentTime * videoInfo.fps);
    currentFrameRef.current = frame;
    setCurrentFrame(frame);

    const ctx = canvas.getContext("2d")!;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    drawBboxOverlay(frame);

    if (video.ended) {
      playStateRef.current = "paused";
      setPlayState("paused");
      return;
    }

    animFrameRef.current = requestAnimationFrame(playLoop);
  }, [videoInfo, drawBboxOverlay]);

  // ── Play / Pause ──────────────────────────────────────────────────────

  const play = useCallback(() => {
    const video = videoRef.current;
    if (!video || !videoInfo) return;
    playStateRef.current = "playing";
    setPlayState("playing");
    setFrameBboxes([]);
    video.playbackRate = playbackSpeed;
    video.play();
    animFrameRef.current = requestAnimationFrame(playLoop);
  }, [playLoop, videoInfo, playbackSpeed]);

  const pause = useCallback(() => {
    const video = videoRef.current;
    if (video) video.pause();
    playStateRef.current = "paused";
    setPlayState("paused");
    cancelAnimationFrame(animFrameRef.current);

    if (videoInfo) {
      const frame = currentFrameRef.current;
      loadFrame(frame).then((img) => {
        frameImgRef.current = img;
        debouncedFetchBboxes(frame, img);
      });
    }
  }, [videoInfo, loadFrame, debouncedFetchBboxes]);

  const togglePlay = useCallback(() => {
    if (playStateRef.current === "playing") {
      pause();
    } else {
      play();
    }
  }, [play, pause]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      cancelAnimationFrame(animFrameRef.current);
      if (bboxDebounceRef.current) clearTimeout(bboxDebounceRef.current);
    };
  }, []);

  // ── Load initial frame (once when videoInfo becomes available) ────────

  const initialLoadDone = useRef(false);
  useEffect(() => {
    if (!videoInfo || initialLoadDone.current) return;
    initialLoadDone.current = true;
    loadFrame(0).then((img) => {
      frameImgRef.current = img;
      drawImageFrame(img, 0);
    });
  }, [videoInfo, loadFrame, drawImageFrame]);

  // ── Redirect handler (shared by canvas click and sidebar click) ───────

  const handleRedirect = useCallback(
    async (bbox: FrameBbox) => {
      try {
        const result = await redirectTracking(
          jobId,
          personId,
          currentFrameRef.current,
          bbox.track_id
        );
        const map: Record<number, [number, number, number, number]> = {};
        for (const [k, v] of Object.entries(result.frame_track_map)) {
          map[Number(k)] = v as [number, number, number, number];
        }
        setTrackMap(map);
        setJumps(result.jumps);
        setRedirectCount(result.redirects.length);
        // Resume playback
        play();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to redirect");
      }
    },
    [jobId, personId, play, setError]
  );

  // ── Handle canvas click ───────────────────────────────────────────────

  const handleCanvasClick = useCallback(
    async (e: React.MouseEvent<HTMLCanvasElement>) => {
      if (playState === "playing") {
        pause();
        return;
      }

      if (!videoInfo || frameBboxes.length === 0) return;

      const canvas = canvasRef.current!;
      const rect = canvas.getBoundingClientRect();
      const cx = e.clientX - rect.left;
      const cy = e.clientY - rect.top;

      // Use CSS display size for hit testing (not canvas pixel buffer)
      const scaleX = rect.width / videoInfo.width;
      const scaleY = rect.height / videoInfo.height;

      // Find currently tracked bbox to skip it
      const tracked = trackMap[currentFrame];
      let trackedTrackId: number | null = null;
      if (tracked) {
        let bestDist = Infinity;
        const [tx1, ty1, tx2, ty2] = tracked;
        const tcx = (tx1 + tx2) / 2, tcy = (ty1 + ty2) / 2;
        for (const b of frameBboxes) {
          const [bx1, by1, bx2, by2] = b.xyxy;
          const d = Math.hypot(tcx - (bx1+bx2)/2, tcy - (by1+by2)/2);
          if (d < bestDist) { bestDist = d; trackedTrackId = b.track_id; }
        }
      }

      for (const bbox of frameBboxes) {
        if (bbox.track_id === trackedTrackId) continue;

        const [x1, y1, x2, y2] = bbox.xyxy;
        const sx1 = x1 * scaleX;
        const sy1 = y1 * scaleY;
        const sx2 = x2 * scaleX;
        const sy2 = y2 * scaleY;

        if (cx >= sx1 && cx <= sx2 && cy >= sy1 && cy <= sy2) {
          await handleRedirect(bbox);
          return;
        }
      }
    },
    [playState, pause, videoInfo, frameBboxes, personId, handleRedirect]
  );

  // ── Cut helpers ─────────────────────────────────────────────────────

  const handleMarkCutStart = useCallback(() => {
    setCutStart(currentFrameRef.current);
  }, []);

  const handleMarkCutEnd = useCallback(() => {
    if (cutStart === null) return;
    const end = currentFrameRef.current;
    const start = Math.min(cutStart, end);
    const endFrame = Math.max(cutStart, end);
    setCuts((prev) => {
      const merged = [...prev, { start, end: endFrame }].sort((a, b) => a.start - b.start);
      // Merge overlapping
      const result: CutSection[] = [];
      for (const c of merged) {
        if (result.length > 0 && c.start <= result[result.length - 1].end + 1) {
          result[result.length - 1] = {
            start: result[result.length - 1].start,
            end: Math.max(result[result.length - 1].end, c.end),
          };
        } else {
          result.push(c);
        }
      }
      return result;
    });
    setCutStart(null);
  }, [cutStart]);

  const handleRemoveCut = useCallback((index: number) => {
    setCuts((prev) => prev.filter((_, i) => i !== index));
  }, []);

  // ── Keyboard ──────────────────────────────────────────────────────────

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === " ") {
        e.preventDefault();
        togglePlay();
      } else if (e.key === "ArrowLeft" && playStateRef.current === "paused") {
        e.preventDefault();
        const prev = Math.max(0, currentFrameRef.current - 1);
        currentFrameRef.current = prev;
        setCurrentFrame(prev);
        if (videoRef.current && videoInfo) {
          videoRef.current.currentTime = prev / videoInfo.fps;
        }
        loadFrame(prev).then((img) => {
          frameImgRef.current = img;
          drawImageFrame(img, prev);
          debouncedFetchBboxes(prev, img);
        });
      } else if (
        e.key === "ArrowRight" &&
        playStateRef.current === "paused" &&
        videoInfo
      ) {
        e.preventDefault();
        const next = Math.min(videoInfo.total_frames - 1, currentFrameRef.current + 1);
        currentFrameRef.current = next;
        setCurrentFrame(next);
        if (videoRef.current) {
          videoRef.current.currentTime = next / videoInfo.fps;
        }
        loadFrame(next).then((img) => {
          frameImgRef.current = img;
          drawImageFrame(img, next);
          debouncedFetchBboxes(next, img);
        });
      } else if (e.key === "z" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        handleUndo();
      } else if (e.key === "i" && playStateRef.current === "paused") {
        e.preventDefault();
        handleMarkCutStart();
      } else if (e.key === "o" && playStateRef.current === "paused") {
        e.preventDefault();
        handleMarkCutEnd();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [togglePlay, videoInfo, drawImageFrame, loadFrame, debouncedFetchBboxes, handleMarkCutStart, handleMarkCutEnd]);

  // ── Navigation helpers ────────────────────────────────────────────────

  const jumpToFrame = useCallback(
    async (frame: number) => {
      const video = videoRef.current;
      if (video) video.pause();
      playStateRef.current = "paused";
      setPlayState("paused");
      cancelAnimationFrame(animFrameRef.current);
      currentFrameRef.current = frame;
      setCurrentFrame(frame);
      if (video && videoInfo) {
        video.currentTime = frame / videoInfo.fps;
      }
      try {
        const img = await loadFrame(frame);
        frameImgRef.current = img;
        drawImageFrame(img, frame);
        debouncedFetchBboxes(frame, img);
      } catch {
        // best effort
      }
    },
    [videoInfo, loadFrame, drawImageFrame, debouncedFetchBboxes]
  );

  const jumpToNextIssue = useCallback(() => {
    const upcoming = jumps.filter((j) => j.frame > currentFrame);
    const target = upcoming.length > 0 ? upcoming[0].frame : jumps[0]?.frame;
    if (target !== undefined) jumpToFrame(target);
  }, [jumps, currentFrame, jumpToFrame]);

  // ── Undo redirect ────────────────────────────────────────────────────

  const handleUndo = useCallback(async () => {
    try {
      const result = await undoRedirect(jobId, personId);
      if (result.frame_track_map) {
        const map: Record<number, [number, number, number, number]> = {};
        for (const [k, v] of Object.entries(result.frame_track_map)) {
          map[Number(k)] = v as [number, number, number, number];
        }
        setTrackMap(map);
        setJumps(result.jumps);
        setRedirectCount(result.redirects?.length ?? 0);
        if (frameImgRef.current) {
          drawImageFrame(frameImgRef.current, currentFrameRef.current);
        }
      }
    } catch {
      // silently fail
    }
  }, [jobId, personId, drawImageFrame]);

  // ── Submit & actions ──────────────────────────────────────────────────

  const handleGenerate = useCallback(async () => {
    setSubmitting(true);
    try {
      await startGeneration(jobId, personId, cuts);
      setPhase("generating");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start generation");
    } finally {
      setSubmitting(false);
    }
  }, [jobId, personId, cuts, setPhase, setError]);

  // ── Timeline click ────────────────────────────────────────────────────

  const handleTimelineClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (!videoInfo) return;
      const rect = e.currentTarget.getBoundingClientRect();
      const ratio = (e.clientX - rect.left) / rect.width;
      const frame = Math.round(ratio * (videoInfo.total_frames - 1));
      jumpToFrame(Math.max(0, Math.min(videoInfo.total_frames - 1, frame)));
    },
    [videoInfo, jumpToFrame]
  );

  // ── Loading state ─────────────────────────────────────────────────────

  if (loading || !videoInfo) {
    return (
      <div style={styles.wrapper}>
        <div style={styles.spinner} />
        <p style={styles.label}>Loading track data...</p>
      </div>
    );
  }

  const totalFrames = videoInfo.total_frames;
  const trackedFrames = Object.keys(trackMap).map(Number);

  // ── Render ────────────────────────────────────────────────────────────

  return (
    <div style={styles.wrapper}>
      <h2 style={styles.title}>Fix Tracking</h2>
      <p style={styles.subtitle}>
        Watch playback. Pause when tracking goes wrong. Click the correct
        person to redirect tracking.
      </p>

      {/* Hidden video element for playback */}
      <video
        ref={videoRef}
        src={`/correction-video/${jobId}`}
        style={{ display: "none" }}
        preload="auto"
        playsInline
        muted
      />

      {/* Toolbar */}
      <div style={styles.toolbar}>
        <button
          style={playState === "playing" ? styles.toolActive : styles.toolBtn}
          onClick={togglePlay}
        >
          {playState === "playing" ? "Pause" : "Play"} (Space)
        </button>
        <button
          style={styles.toolBtn}
          onClick={jumpToNextIssue}
          disabled={jumps.length === 0}
        >
          Next issue ({jumps.length})
        </button>
        <button
          style={styles.toolBtn}
          onClick={handleUndo}
          disabled={redirectCount === 0}
        >
          Undo redirect ({redirectCount})
        </button>
        <div style={styles.toolSep} />
        <button
          style={cutStart !== null ? styles.toolActive : styles.toolBtn}
          onClick={cutStart === null ? handleMarkCutStart : handleMarkCutEnd}
        >
          {cutStart !== null ? `Cut end (O) — from ${cutStart}` : `Cut start (I)`}
        </button>
        {cutStart !== null && (
          <button
            style={styles.toolBtn}
            onClick={() => setCutStart(null)}
          >
            Cancel
          </button>
        )}
        {cuts.length > 0 && (
          <span style={{ fontSize: 12, color: "#ef4444" }}>
            {cuts.length} cut{cuts.length !== 1 ? "s" : ""}
          </span>
        )}
        <div style={styles.toolSep} />
        <select
          style={styles.speedSelect}
          value={playbackSpeed}
          onChange={(e) => {
            const speed = Number(e.target.value);
            setPlaybackSpeed(speed);
            if (videoRef.current) videoRef.current.playbackRate = speed;
          }}
        >
          {[1, 1.5, 2, 3, 4, 5, 8, 10].map((s) => (
            <option key={s} value={s}>{s}x</option>
          ))}
        </select>
        <div style={styles.toolSep} />
        <button
          style={styles.generateBtn}
          onClick={handleGenerate}
          disabled={submitting}
        >
          {submitting ? "..." : "Done \u2014 Generate"}
        </button>
      </div>

      <div style={styles.mainArea}>
        {/* Canvas */}
        <div style={styles.canvasContainer}>
          <canvas
            ref={canvasRef}
            width={canvasWidth}
            height={canvasHeight}
            style={{
              ...styles.canvas,
              width: displayWidth,
              height: displayHeight,
              cursor: playState === "paused" ? "pointer" : "default",
            }}
            onClick={handleCanvasClick}
          />

          {/* Timeline */}
          <div style={styles.timeline} onClick={handleTimelineClick}>
            {/* Tracked segments */}
            {trackedFrames.length > 0 &&
              (() => {
                const segments: { start: number; end: number }[] = [];
                const sorted = [...trackedFrames].sort((a, b) => a - b);
                let segStart = sorted[0];
                let segEnd = sorted[0];
                for (let i = 1; i < sorted.length; i++) {
                  if (sorted[i] - segEnd <= 3) {
                    segEnd = sorted[i];
                  } else {
                    segments.push({ start: segStart, end: segEnd });
                    segStart = sorted[i];
                    segEnd = sorted[i];
                  }
                }
                segments.push({ start: segStart, end: segEnd });

                return segments.map((seg, i) => (
                  <div
                    key={`seg-${i}`}
                    style={{
                      position: "absolute",
                      left: `${(seg.start / totalFrames) * 100}%`,
                      width: `${(Math.max(1, seg.end - seg.start) / totalFrames) * 100}%`,
                      height: "100%",
                      background: "#22c55e33",
                      borderRadius: 2,
                    }}
                  />
                ));
              })()}

            {/* Cut sections */}
            {cuts.map((c, i) => (
              <div
                key={`cut-${i}`}
                style={{
                  position: "absolute",
                  left: `${(c.start / totalFrames) * 100}%`,
                  width: `${(Math.max(1, c.end - c.start + 1) / totalFrames) * 100}%`,
                  height: "100%",
                  background: "rgba(239, 68, 68, 0.35)",
                  borderLeft: "1px solid #ef4444",
                  borderRight: "1px solid #ef4444",
                }}
              />
            ))}

            {/* Pending cut start marker */}
            {cutStart !== null && (
              <div
                style={{
                  position: "absolute",
                  left: `${(cutStart / totalFrames) * 100}%`,
                  width: `${(Math.max(1, (currentFrame >= cutStart ? currentFrame - cutStart + 1 : cutStart - currentFrame + 1)) / totalFrames) * 100}%`,
                  marginLeft: currentFrame < cutStart ? `${((currentFrame - cutStart) / totalFrames) * 100}%` : undefined,
                  height: "100%",
                  background: "rgba(239, 68, 68, 0.2)",
                  border: "1px dashed #ef4444",
                }}
              />
            )}

            {/* Jump markers */}
            {jumps.map((j, i) => (
              <div
                key={`jump-${i}`}
                style={{
                  position: "absolute",
                  left: `${(j.frame / totalFrames) * 100}%`,
                  width: 2,
                  height: "100%",
                  background: "#ef4444",
                  opacity: 0.7,
                }}
              />
            ))}

            {/* Playhead */}
            <div
              style={{
                position: "absolute",
                left: `${(currentFrame / totalFrames) * 100}%`,
                width: 2,
                height: "100%",
                background: "#fff",
                boxShadow: "0 0 4px rgba(0,0,0,0.5)",
              }}
            />
          </div>

          <div style={styles.frameInfo}>
            <span>
              Frame {currentFrame} / {totalFrames - 1}
            </span>
            <span>
              {redirectCount > 0
                ? `${redirectCount} redirect${redirectCount !== 1 ? "s" : ""}`
                : ""}
            </span>
          </div>
        </div>

        {/* Sidebar */}
        <div style={styles.sidebar}>
          <h3 style={styles.sidebarTitle}>How to use</h3>
          <ul style={styles.helpList}>
            <li>Space — play/pause</li>
            <li>Pause when tracking is wrong</li>
            <li>Click the correct person to redirect</li>
            <li>Arrow keys — step frame-by-frame</li>
            <li>I — mark cut start, O — mark cut end</li>
          </ul>

          <h3 style={{ ...styles.sidebarTitle, marginTop: 24 }}>
            Detected Issues
          </h3>
          <div style={styles.jumpList}>
            {jumps.length === 0 && (
              <p style={styles.noIssues}>No jumps detected</p>
            )}
            {jumps.map((j, i) => (
              <button
                key={i}
                style={{
                  ...styles.jumpItem,
                  background: j.frame === currentFrame ? "#333" : "transparent",
                }}
                onClick={() => jumpToFrame(j.frame)}
              >
                <span>Frame {j.frame}</span>
                <span style={styles.jumpDist}>
                  {Math.round(j.distance)}px jump
                </span>
              </button>
            ))}
          </div>

          {cuts.length > 0 && (
            <>
              <h3 style={{ ...styles.sidebarTitle, marginTop: 24 }}>
                Cut Sections
              </h3>
              <div style={styles.jumpList}>
                {cuts.map((c, i) => (
                  <div
                    key={`cut-${i}`}
                    style={{
                      ...styles.jumpItem,
                      borderLeft: "3px solid #ef4444",
                    }}
                  >
                    <span
                      style={{ cursor: "pointer" }}
                      onClick={() => jumpToFrame(c.start)}
                    >
                      {c.start}–{c.end} ({c.end - c.start + 1}f)
                    </span>
                    <button
                      style={{
                        background: "none",
                        border: "none",
                        color: "#888",
                        cursor: "pointer",
                        fontSize: 14,
                        padding: "0 4px",
                      }}
                      onClick={() => handleRemoveCut(i)}
                      title="Remove cut"
                    >
                      x
                    </button>
                  </div>
                ))}
              </div>
            </>
          )}

          {playState === "paused" && frameBboxes.length > 0 && (() => {
            // Determine which bbox is currently tracked by matching trackMap position
            const tracked = trackMap[currentFrame];
            let selectedTrackId: number | null = null;
            if (tracked) {
              let bestDist = Infinity;
              const [tx1, ty1, tx2, ty2] = tracked;
              const tcx = (tx1 + tx2) / 2, tcy = (ty1 + ty2) / 2;
              for (const b of frameBboxes) {
                const [bx1, by1, bx2, by2] = b.xyxy;
                const bcx = (bx1 + bx2) / 2, bcy = (by1 + by2) / 2;
                const d = Math.hypot(tcx - bcx, tcy - bcy);
                if (d < bestDist) { bestDist = d; selectedTrackId = b.track_id; }
              }
            }
            return (
            <>
              <h3 style={{ ...styles.sidebarTitle, marginTop: 24 }}>
                People on frame
              </h3>
              <div style={styles.jumpList}>
                {frameBboxes.map((b) => {
                  const isSelected = b.track_id === selectedTrackId;
                  return (
                    <button
                      key={b.track_id}
                      style={{
                        ...styles.bboxItemBtn,
                        borderLeft: `3px solid ${isSelected ? "#22c55e" : "#f97316"}`,
                        opacity: isSelected ? 0.6 : 1,
                      }}
                      disabled={isSelected}
                      onClick={() => handleRedirect(b)}
                    >
                      <span>
                        {isSelected
                          ? "Tracking"
                          : b.person_id || `track ${b.track_id}`}
                      </span>
                      <span style={{ fontSize: 11, color: "#888" }}>
                        {(b.conf * 100).toFixed(0)}%
                      </span>
                    </button>
                  );
                })}
              </div>
            </>
          );
          })()}
        </div>
      </div>
    </div>
  );
}

// ── Styles ──────────────────────────────────────────────────────────────────

const styles: Record<string, React.CSSProperties> = {
  wrapper: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    minHeight: "100vh",
    padding: "32px 24px",
    gap: 16,
  },
  spinner: {
    width: 48,
    height: 48,
    border: "4px solid #222",
    borderTop: "4px solid #7c6aff",
    borderRadius: "50%",
    animation: "spin 0.8s linear infinite",
    marginTop: 120,
  },
  label: { fontSize: 16, color: "#888" },
  title: { fontSize: 28, fontWeight: 700, margin: 0 },
  subtitle: {
    fontSize: 14,
    color: "#888",
    margin: 0,
    textAlign: "center" as const,
    maxWidth: 520,
  },

  toolbar: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    flexWrap: "wrap" as const,
    justifyContent: "center",
  },
  toolBtn: {
    padding: "8px 14px",
    background: "#1a1a1a",
    color: "#ccc",
    border: "1px solid #333",
    borderRadius: 8,
    fontSize: 13,
    cursor: "pointer",
  },
  toolActive: {
    padding: "8px 14px",
    background: "#7c6aff22",
    color: "#a78bfa",
    border: "1px solid #7c6aff",
    borderRadius: 8,
    fontSize: 13,
    cursor: "pointer",
  },
  speedSelect: {
    padding: "7px 8px",
    background: "#1a1a1a",
    color: "#ccc",
    border: "1px solid #333",
    borderRadius: 8,
    fontSize: 13,
    cursor: "pointer",
  },
  toolSep: {
    width: 1,
    height: 28,
    background: "#333",
  },
  generateBtn: {
    padding: "8px 20px",
    background: "#7c6aff",
    color: "#fff",
    border: "none",
    borderRadius: 8,
    fontSize: 13,
    fontWeight: 600,
    cursor: "pointer",
  },

  mainArea: {
    display: "flex",
    gap: 20,
    width: "100%",
    maxWidth: 1280,
    justifyContent: "center",
  },
  canvasContainer: {
    display: "flex",
    flexDirection: "column" as const,
    gap: 8,
    flex: 1,
    minWidth: 0,
  },
  canvas: {
    borderRadius: 8,
    background: "#111",
    maxWidth: "100%",
  },
  timeline: {
    position: "relative" as const,
    height: 32,
    background: "#1a1a1a",
    borderRadius: 6,
    cursor: "pointer",
    overflow: "hidden",
  },
  frameInfo: {
    display: "flex",
    justifyContent: "space-between",
    fontSize: 12,
    color: "#666",
  },

  sidebar: {
    width: 220,
    flexShrink: 0,
  },
  sidebarTitle: {
    fontSize: 14,
    fontWeight: 600,
    color: "#aaa",
    margin: "0 0 8px 0",
  },
  helpList: {
    fontSize: 12,
    color: "#888",
    margin: 0,
    paddingLeft: 16,
    lineHeight: 1.8,
  },
  jumpList: {
    display: "flex",
    flexDirection: "column" as const,
    gap: 2,
    maxHeight: 300,
    overflowY: "auto" as const,
  },
  jumpItem: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "6px 10px",
    border: "none",
    borderRadius: 6,
    color: "#ccc",
    fontSize: 12,
    cursor: "pointer",
    textAlign: "left" as const,
  },
  jumpDist: {
    fontSize: 11,
    color: "#ef4444",
  },
  noIssues: {
    fontSize: 12,
    color: "#555",
    margin: 0,
    padding: "8px 0",
  },
  bboxItemBtn: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "6px 10px",
    border: "none",
    borderRadius: 6,
    color: "#ccc",
    fontSize: 12,
    cursor: "pointer",
    textAlign: "left" as const,
    background: "transparent",
    width: "100%",
  },
};
