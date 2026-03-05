import React from "react";
import { useAppStore } from "../store/appStore";
import { useGenerate } from "../hooks/useGenerate";
import { mergePersons } from "../api/merge";
import type { Person } from "../types";

export function DancerGrid() {
  const persons = useAppStore((s) => s.persons);
  const jobId = useAppStore((s) => s.jobId);
  const setPersons = useAppStore((s) => s.setPersons);
  const setError = useAppStore((s) => s.setError);
  const { generate } = useGenerate();

  const [selected, setSelected] = React.useState<Set<string>>(new Set());
  const [merging, setMerging] = React.useState(false);

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
            {merging ? "Merging…" : `Merge ${selected.size} into one`}
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
            isSelected={selected.has(p.person_id)}
            onToggle={toggleSelect}
          />
        ))}
      </div>
    </div>
  );
}

function PersonCard({
  person,
  isSelected,
  onToggle,
}: {
  person: Person;
  isSelected: boolean;
  onToggle: (id: string) => void;
}) {
  function handleClick() {
    onToggle(person.person_id);
  }

  return (
    <div
      style={{
        ...styles.card,
        borderColor: isSelected ? "#7c6aff" : "transparent",
        transform: isSelected ? "scale(1.03)" : "scale(1)",
      }}
      onClick={handleClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === "Enter" && handleClick()}
      title="Click to select"
    >
      {isSelected && <div style={styles.checkmark}>✓</div>}
      <img
        src={person.thumbnail_url}
        alt={`Dancer ${person.person_id}`}
        style={styles.img}
        loading="lazy"
      />
      <div style={styles.label}>
        {person.frame_count} frames · ~{Math.round((person.last_frame - person.first_frame) / 30)}s
      </div>
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
    zIndex: 1,
  },
  img: { width: "100%", aspectRatio: "9/16", objectFit: "cover", display: "block" },
  label: { padding: "8px 12px", fontSize: 12, color: "#888" },
};
