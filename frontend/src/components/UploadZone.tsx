import React from "react";
import { useDropzone } from "react-dropzone";
import { useUpload } from "../hooks/useUpload";

const styles: Record<string, React.CSSProperties> = {
  wrapper: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    minHeight: "100vh",
    gap: 24,
  },
  title: { fontSize: 32, fontWeight: 700, margin: 0, letterSpacing: -1 },
  subtitle: { fontSize: 16, color: "#888", margin: 0 },
  zone: {
    border: "2px dashed #444",
    borderRadius: 16,
    padding: "60px 80px",
    cursor: "pointer",
    transition: "border-color 0.2s, background 0.2s",
    textAlign: "center",
  },
  zoneActive: {
    border: "2px dashed #7c6aff",
    background: "#1a1830",
  },
  icon: { fontSize: 48, marginBottom: 16 },
  hint: { color: "#666", fontSize: 14, marginTop: 8 },
};

export function UploadZone() {
  const { upload, uploadProgress } = useUpload();

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: { "video/*": [".mp4", ".mov", ".avi", ".webm"] },
    maxFiles: 1,
    onDropAccepted: ([file]) => upload(file),
  });

  return (
    <div style={styles.wrapper}>
      <h1 style={styles.title}>Fancam Generator</h1>
      <p style={styles.subtitle}>Upload a video, pick a dancer, get a fancam</p>
      <div
        {...getRootProps()}
        style={{ ...styles.zone, ...(isDragActive ? styles.zoneActive : {}) }}
      >
        <input {...getInputProps()} />
        <div style={styles.icon}>{isDragActive ? "🎯" : "🎬"}</div>
        <p style={{ margin: 0, fontWeight: 600 }}>
          {isDragActive ? "Drop it!" : "Drag & drop a video here"}
        </p>
        <p style={styles.hint}>or click to browse — MP4, MOV, AVI, WebM</p>
      </div>
      {uploadProgress > 0 && uploadProgress < 1 && (
        <ProgressBar value={uploadProgress} label="Uploading..." />
      )}
    </div>
  );
}

function ProgressBar({ value, label }: { value: number; label: string }) {
  return (
    <div style={{ width: 320, textAlign: "center" }}>
      <p style={{ margin: "0 0 8px", fontSize: 13, color: "#888" }}>{label}</p>
      <div style={{ background: "#222", borderRadius: 8, height: 8 }}>
        <div
          style={{
            background: "#7c6aff",
            width: `${Math.round(value * 100)}%`,
            height: "100%",
            borderRadius: 8,
            transition: "width 0.3s",
          }}
        />
      </div>
    </div>
  );
}
