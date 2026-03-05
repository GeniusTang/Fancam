import React from "react";
import { useAppStore } from "./store/appStore";
import { useJobStatus } from "./hooks/useJobStatus";
import { UploadZone } from "./components/UploadZone";
import { ProgressPanel } from "./components/ProgressPanel";
import { DancerGrid } from "./components/DancerGrid";
import { PreviewPanel } from "./components/PreviewPanel";
import { ResultPanel } from "./components/ResultPanel";

const errorStyles: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  justifyContent: "center",
  minHeight: "100vh",
  gap: 16,
  padding: "0 24px",
};

export default function App() {
  const phase = useAppStore((s) => s.phase);
  const jobId = useAppStore((s) => s.jobId);
  const error = useAppStore((s) => s.error);
  const reset = useAppStore((s) => s.reset);

  // SSE connection — active whenever we have a jobId and are in analyzing/generating
  useJobStatus(
    phase === "analyzing" || phase === "generating" ? jobId : null
  );

  if (phase === "error") {
    return (
      <div style={errorStyles}>
        <div style={{ fontSize: 48 }}>⚠️</div>
        <h2 style={{ margin: 0 }}>Something went wrong</h2>
        <p style={{ color: "#888", margin: 0 }}>{error}</p>
        <button
          onClick={reset}
          style={{
            padding: "12px 28px",
            background: "#7c6aff",
            color: "#fff",
            border: "none",
            borderRadius: 10,
            fontSize: 15,
            cursor: "pointer",
          }}
        >
          Start over
        </button>
      </div>
    );
  }

  switch (phase) {
    case "upload":
      return <UploadZone />;
    case "analyzing":
    case "generating":
      return <ProgressPanel />;
    case "select_dancer":
      return <DancerGrid />;
    case "previewing":
      return <PreviewPanel />;
    case "complete":
      return <ResultPanel />;
    default:
      return <UploadZone />;
  }
}
