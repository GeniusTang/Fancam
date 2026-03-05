import React from "react";
import { useAppStore } from "../store/appStore";

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
  title: { fontSize: 28, fontWeight: 700, margin: 0 },
  subtitle: { fontSize: 15, color: "#888", margin: 0 },
  btn: {
    padding: "14px 32px",
    background: "#7c6aff",
    color: "#fff",
    border: "none",
    borderRadius: 10,
    fontSize: 16,
    fontWeight: 600,
    cursor: "pointer",
    textDecoration: "none",
    display: "inline-block",
  },
  secondary: {
    background: "transparent",
    border: "2px solid #333",
    color: "#aaa",
    padding: "12px 28px",
    borderRadius: 10,
    fontSize: 15,
    cursor: "pointer",
  },
  row: { display: "flex", gap: 16, flexWrap: "wrap", justifyContent: "center" },
};

export function ResultPanel() {
  const jobId = useAppStore((s) => s.jobId);
  const reset = useAppStore((s) => s.reset);

  return (
    <div style={styles.wrapper}>
      <div style={{ fontSize: 64 }}>🎉</div>
      <h2 style={styles.title}>Your fancam is ready!</h2>
      <p style={styles.subtitle}>Download the cropped, tracked video below</p>
      <div style={styles.row}>
        <a href={`/download/${jobId}`} download style={styles.btn}>
          Download Fancam
        </a>
        <button style={styles.secondary} onClick={reset}>
          Make another
        </button>
      </div>
    </div>
  );
}
