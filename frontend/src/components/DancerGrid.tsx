import React from "react";
import { useAppStore } from "../store/appStore";
import { useGenerate } from "../hooks/useGenerate";
import { mergePersons } from "../api/merge";
import { FragmentPanel } from "./FragmentPanel";
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
  const setPersons = useAppStore((s) => s.setPersons);
  const setError = useAppStore((s) => s.setError);
  const { generate } = useGenerate();

  const [selected, setSelected] = React.useState<Set<string>>(new Set());
  const [merging, setMerging] = React.useState(false);
  const [inspecting, setInspecting] = React.useState<Person | null>(null);

  function toggleSelect(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  async function handleMerge() {
    if (!jobId || selected.size < 2) return;
    setMerging(true);
    try {
      const result = await mergePersons(jobId, [...selected]);
      setPersons(result.persons);
      setSelected(new Set());
    } catch {
      setError("Merge failed");
    } finally {
      setMerging(false);
    }
  }

  return (
    <div style={styles.wrapper}>
      <h2 style={styles.title}>Select a Dancer</h2>
      <p style={styles.subtitle}>
        {persons.length} person{persons.length !== 1 ? "s" : ""} detected
        {selected.size === 0 ? " — click to select" : ` — ${selected.size} selected`}
      </p>

      <div style={{ display: "flex", gap: 12, minHeight: 44 }}>
        {selected.size === 1 && (
          <button style={styles.generateBtn} onClick={() => generate([...selected][0])}>
            Generate fancam
          </button>
        )}
        {selected.size >= 2 && (
          <button style={styles.mergeBtn} onClick={handleMerge} disabled={merging}>
            {merging ? "Merging..." : `Merge ${selected.size} into one`}
          </button>
        )}
        {selected.size > 0 && (
          <button style={styles.clearBtn} onClick={() => setSelected(new Set())}>
            Clear
          </button>
        )}
      </div>

      <div style={styles.grid}>
        {persons.map((p) => (
          <PersonCard
            key={p.person_id}
            person={p}
            totalFrames={totalFrames}
            isSelected={selected.has(p.person_id)}
            onToggle={toggleSelect}
            onInspect={() => setInspecting(p)}
          />
        ))}
      </div>

      {inspecting && (
        <FragmentPanel
          person={inspecting}
          allPersons={persons}
          onClose={() => setInspecting(null)}
          onPersonsUpdated={(updated) => {
            setPersons(updated);
            const still = updated.find((p) => p.person_id === inspecting.person_id);
            setInspecting(still ?? null);
          }}
        />
      )}
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
  isSelected,
  onToggle,
  onInspect,
}: {
  person: Person;
  totalFrames: number;
  isSelected: boolean;
  onToggle: (id: string) => void;
  onInspect: () => void;
}) {
  return (
    <div
      style={{
        ...styles.card,
        borderColor: isSelected ? "#7c6aff" : "transparent",
        transform: isSelected ? "scale(1.03)" : "scale(1)",
      }}
      onClick={() => onToggle(person.person_id)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === "Enter" && onToggle(person.person_id)}
    >
      {isSelected && <div style={styles.checkmark}>✓</div>}
      <button
        style={styles.inspectBtn}
        title="Inspect track fragments"
        onClick={(e) => { e.stopPropagation(); onInspect(); }}
      >
        ⋯
      </button>
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
  generateBtn: {
    padding: "12px 28px",
    background: "#7c6aff",
    color: "#fff",
    border: "none",
    borderRadius: 10,
    fontSize: 15,
    fontWeight: 600,
    cursor: "pointer",
  },
  mergeBtn: {
    padding: "12px 28px",
    background: "#ff6af0",
    color: "#fff",
    border: "none",
    borderRadius: 10,
    fontSize: 15,
    fontWeight: 600,
    cursor: "pointer",
  },
  clearBtn: {
    padding: "12px 20px",
    background: "transparent",
    color: "#888",
    border: "1px solid #333",
    borderRadius: 10,
    fontSize: 15,
    cursor: "pointer",
  },
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
  checkmark: {
    position: "absolute",
    top: 8,
    right: 8,
    width: 24,
    height: 24,
    background: "#7c6aff",
    borderRadius: "50%",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 13,
    fontWeight: 700,
    color: "#fff",
    zIndex: 2,
  },
  inspectBtn: {
    position: "absolute",
    top: 8,
    left: 8,
    width: 24,
    height: 24,
    background: "rgba(0,0,0,0.6)",
    border: "none",
    borderRadius: "50%",
    color: "#fff",
    fontSize: 14,
    cursor: "pointer",
    zIndex: 2,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    lineHeight: 1,
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
};
