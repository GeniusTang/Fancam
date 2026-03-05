import React from "react";
import { useAppStore } from "../store/appStore";

const STAGE_LABELS: Record<string, string> = {
  detecting: "Detecting people",
  tracking: "Tracking across frames",
  clustering: "Identifying unique dancers",
  thumbnailing: "Generating previews",
  rendering: "Rendering fancam",
  encoding: "Encoding video",
};

function formatEta(seconds: number): string {
  if (seconds < 60) return `~${Math.round(seconds)}s remaining`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return `~${mins}m ${secs}s remaining`;
}

const styles: Record<string, React.CSSProperties> = {
  wrapper: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    minHeight: "100vh",
    gap: 24,
    padding: "0 24px",
  },
  spinner: {
    width: 48,
    height: 48,
    border: "4px solid #222",
    borderTop: "4px solid #7c6aff",
    borderRadius: "50%",
    animation: "spin 0.8s linear infinite",
  },
  stage: { fontSize: 20, fontWeight: 600, margin: 0 },
  pct: { fontSize: 14, color: "#888", margin: 0 },
  eta: { fontSize: 13, color: "#666", margin: 0 },
  bar: { width: 320, background: "#222", borderRadius: 8, height: 8 },
  fill: {
    background: "linear-gradient(90deg, #7c6aff, #ff6af0)",
    height: "100%",
    borderRadius: 8,
    transition: "width 0.4s ease",
  },
};

export function ProgressPanel() {
  const sseEvent = useAppStore((s) => s.sseEvent);
  const phase = useAppStore((s) => s.phase);

  const stage = sseEvent?.stage ?? null;
  const progress = sseEvent?.progress ?? 0;
  const eta = sseEvent?.eta ?? null;
  const label =
    phase === "generating"
      ? STAGE_LABELS[stage ?? "rendering"] ?? "Processing"
      : STAGE_LABELS[stage ?? "detecting"] ?? "Analyzing video";

  const pct = Math.round(progress * 100);

  return (
    <div style={styles.wrapper}>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      <div style={styles.spinner} />
      <p style={styles.stage}>{label}</p>
      <p style={styles.pct}>{pct}%</p>
      <div style={styles.bar}>
        <div style={{ ...styles.fill, width: `${pct}%` }} />
      </div>
      {eta != null && eta > 0 && (
        <p style={styles.eta}>{formatEta(eta)}</p>
      )}
    </div>
  );
}
