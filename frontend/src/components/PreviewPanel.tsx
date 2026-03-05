import React from "react";
import { useAppStore } from "../store/appStore";
import { startGeneration } from "../api/generate";

export function PreviewPanel() {
  const jobId = useAppStore((s) => s.jobId);
  const previewUrl = useAppStore((s) => s.previewUrl);
  const selectedPersonId = useAppStore((s) => s.selectedPersonId);
  const setPhase = useAppStore((s) => s.setPhase);
  const setPreviewUrl = useAppStore((s) => s.setPreviewUrl);
  const setError = useAppStore((s) => s.setError);
  const [starting, setStarting] = React.useState(false);

  async function handleApprove() {
    if (!jobId || !selectedPersonId) return;
    setStarting(true);
    try {
      await startGeneration(jobId, selectedPersonId);
      setPhase("generating");
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Generation failed";
      setError(msg);
    } finally {
      setStarting(false);
    }
  }

  function handleGoBack() {
    setPreviewUrl(null);
    setPhase("select_dancer");
  }

  if (!previewUrl) {
    return (
      <div style={styles.wrapper}>
        <div style={styles.spinner} />
        <p style={styles.label}>Generating preview...</p>
      </div>
    );
  }

  return (
    <div style={styles.wrapper}>
      <h2 style={styles.title}>Preview</h2>
      <p style={styles.subtitle}>
        5-second clip with bbox overlay — does this look like the right person?
      </p>

      <div style={styles.videoContainer}>
        <video
          src={previewUrl}
          controls
          autoPlay
          loop
          muted
          playsInline
          style={styles.video}
        />
      </div>

      <div style={styles.actions}>
        <button style={styles.backBtn} onClick={handleGoBack}>
          Go back
        </button>
        <button
          style={styles.approveBtn}
          onClick={handleApprove}
          disabled={starting}
        >
          {starting ? "Starting..." : "Looks good — Render full"}
        </button>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  wrapper: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    minHeight: "100vh",
    gap: 24,
    padding: "48px 24px",
  },
  spinner: {
    width: 48,
    height: 48,
    border: "4px solid #222",
    borderTop: "4px solid #7c6aff",
    borderRadius: "50%",
    animation: "spin 0.8s linear infinite",
  },
  title: { fontSize: 28, fontWeight: 700, margin: 0 },
  subtitle: { fontSize: 15, color: "#888", margin: 0 },
  label: { fontSize: 16, color: "#888" },
  videoContainer: {
    width: "100%",
    maxWidth: 720,
    borderRadius: 12,
    overflow: "hidden",
    background: "#111",
  },
  video: {
    width: "100%",
    display: "block",
  },
  actions: {
    display: "flex",
    gap: 12,
  },
  backBtn: {
    padding: "12px 24px",
    background: "transparent",
    color: "#888",
    border: "1px solid #333",
    borderRadius: 10,
    fontSize: 15,
    cursor: "pointer",
  },
  approveBtn: {
    padding: "12px 28px",
    background: "#7c6aff",
    color: "#fff",
    border: "none",
    borderRadius: 10,
    fontSize: 15,
    fontWeight: 600,
    cursor: "pointer",
  },
};
