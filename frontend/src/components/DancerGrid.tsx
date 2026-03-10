import React, { useState } from "react";
import { reanalyze } from "../api/generate";
import { useAppStore } from "../store/appStore";
import type { Person, TrackSpan } from "../types";

// Color palette for track spans
const SPAN_COLORS = [
  "#7c6aff", "#ff6af0", "#6affb2", "#ffb26a", "#6abfff",
  "#ff6a6a", "#b26aff", "#6aff6a",
];

export function DancerGrid() {
  const persons = useAppStore((s) => s.persons);
  const totalFrames = useAppStore((s) => s.totalFrames);
  const jobId = useAppStore((s) => s.jobId);
  const setSelectedPerson = useAppStore((s) => s.setSelectedPerson);
  const setPhase = useAppStore((s) => s.setPhase);
  const setError = useAppStore((s) => s.setError);
  const [reanalyzing, setReanalyzing] = useState(false);

  function handleSelect(personId: string) {
    setSelectedPerson(personId);
    setPhase("correcting");
  }

  async function handleReanalyze() {
    if (!jobId || reanalyzing) return;
    if (!confirm("Clear cache and re-run analysis from scratch?")) return;
    setReanalyzing(true);
    try {
      await reanalyze(jobId);
      setPhase("analyzing");
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Re-analyze failed";
      setError(msg);
    }
  }

  return (
    <div style={styles.wrapper}>
      <h2 style={styles.title}>Select a Dancer</h2>
      <p style={styles.subtitle}>
        {persons.length} person{persons.length !== 1 ? "s" : ""} detected
        {" — click to select"}
      </p>

      <div style={styles.grid}>
        {persons.map((p) => (
          <PersonCard
            key={p.person_id}
            person={p}
            totalFrames={totalFrames}
            onSelect={handleSelect}
          />
        ))}
      </div>

      <button
        onClick={handleReanalyze}
        disabled={reanalyzing}
        style={styles.reanalyzeBtn}
      >
        {reanalyzing ? "Re-analyzing..." : "Clear cache & re-analyze"}
      </button>
    </div>
  );
}

function TimelineBar({ spans, totalFrames }: { spans: TrackSpan[]; totalFrames: number }) {
  if (!spans || spans.length === 0 || totalFrames <= 0) return null;

  return (
    <div style={styles.timelineContainer}>
      <div style={styles.timelineTrack}>
        {spans.map((span, i) => {
          const left = (span.start / totalFrames) * 100;
          const width = Math.max(((span.end - span.start) / totalFrames) * 100, 0.5);
          return (
            <div
              key={i}
              style={{
                position: "absolute",
                left: `${left}%`,
                width: `${width}%`,
                height: "100%",
                background: SPAN_COLORS[i % SPAN_COLORS.length],
                borderRadius: 2,
                minWidth: 2,
              }}
            />
          );
        })}
      </div>
    </div>
  );
}

function PersonCard({
  person,
  totalFrames,
  onSelect,
}: {
  person: Person;
  totalFrames: number;
  onSelect: (id: string) => void;
}) {
  return (
    <div
      style={styles.card}
      onClick={() => onSelect(person.person_id)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === "Enter" && onSelect(person.person_id)}
    >
      <img
        src={person.thumbnail_url}
        alt={`Dancer ${person.person_id}`}
        style={styles.img}
        loading="lazy"
      />
      <div style={styles.label}>
        {person.frame_count} frames · ~{Math.round((person.last_frame - person.first_frame) / 30)}s
      </div>
      <TimelineBar spans={person.track_spans ?? []} totalFrames={totalFrames} />
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  wrapper: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    padding: "48px 24px",
    gap: 24,
    minHeight: "100vh",
  },
  title: { fontSize: 28, fontWeight: 700, margin: 0 },
  subtitle: { fontSize: 15, color: "#888", margin: 0 },
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))",
    gap: 16,
    width: "100%",
    maxWidth: 900,
  },
  card: {
    position: "relative",
    background: "#1a1a1a",
    borderRadius: 12,
    overflow: "hidden",
    cursor: "pointer",
    border: "2px solid transparent",
    transition: "border-color 0.15s, transform 0.15s",
  },
  img: { width: "100%", aspectRatio: "9/16", objectFit: "cover", display: "block" },
  label: { padding: "8px 12px 4px", fontSize: 12, color: "#888" },
  timelineContainer: {
    padding: "0 12px 8px",
  },
  timelineTrack: {
    position: "relative",
    height: 6,
    background: "#2a2a2a",
    borderRadius: 3,
    overflow: "hidden",
  },
  reanalyzeBtn: {
    marginTop: 16,
    padding: "10px 24px",
    background: "transparent",
    color: "#888",
    border: "1px solid #444",
    borderRadius: 8,
    fontSize: 13,
    cursor: "pointer",
  },
};
