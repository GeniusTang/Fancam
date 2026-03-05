import React from "react";
import { fetchFragments, reassignFragment, type Fragment } from "../api/frames";
import { useAppStore } from "../store/appStore";
import type { Person } from "../types";

interface Props {
  person: Person;
  allPersons: Person[];
  onClose: () => void;
  onPersonsUpdated: (persons: Person[]) => void;
}

export function FragmentPanel({ person, allPersons, onClose, onPersonsUpdated }: Props) {
  const jobId = useAppStore((s) => s.jobId)!;
  const [fragments, setFragments] = React.useState<Fragment[] | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [reassigning, setReassigning] = React.useState<number | null>(null);
  const [dragOverPerson, setDragOverPerson] = React.useState<string | null>(null);

  React.useEffect(() => {
    setLoading(true);
    fetchFragments(jobId, person.person_id)
      .then((r) => setFragments(r.fragments))
      .catch(() => setFragments([]))
      .finally(() => setLoading(false));
  }, [jobId, person.person_id]);

  async function handleReassign(trackId: number, toPersonId: string) {
    setReassigning(trackId);
    try {
      const result = await reassignFragment(jobId, trackId, toPersonId);
      onPersonsUpdated(result.persons);
      const updated = await fetchFragments(jobId, person.person_id);
      setFragments(updated.fragments);
    } catch {
      /* ignore */
    } finally {
      setReassigning(null);
    }
  }

  function handleDragStart(e: React.DragEvent, trackId: number) {
    e.dataTransfer.setData("text/plain", String(trackId));
    e.dataTransfer.effectAllowed = "move";
  }

  function handleDragOver(e: React.DragEvent, personId: string) {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    setDragOverPerson(personId);
  }

  function handleDragLeave() {
    setDragOverPerson(null);
  }

  function handleDrop(e: React.DragEvent, toPersonId: string) {
    e.preventDefault();
    setDragOverPerson(null);
    const trackId = parseInt(e.dataTransfer.getData("text/plain"), 10);
    if (!isNaN(trackId)) {
      handleReassign(trackId, toPersonId);
    }
  }

  const others = allPersons.filter((p) => p.person_id !== person.person_id);

  return (
    <div style={s.overlay} onClick={onClose}>
      <div style={s.panel} onClick={(e) => e.stopPropagation()}>
        <div style={s.header}>
          <span style={s.title}>Track fragments — {person.person_id}</span>
          <button style={s.closeBtn} onClick={onClose}>✕</button>
        </div>

        <div style={s.body}>
          {/* Main fragments column */}
          <div style={s.mainCol}>
            <div style={s.colHeader}>Fragments (drag to reassign)</div>
            {loading && <div style={s.empty}>Loading frames...</div>}
            {!loading && fragments?.length === 0 && (
              <div style={s.empty}>No fragments found.</div>
            )}
            <div style={s.fragmentList}>
              {fragments?.map((frag) => (
                <div
                  key={frag.track_id}
                  style={s.fragRow}
                  draggable
                  onDragStart={(e) => handleDragStart(e, frag.track_id)}
                >
                  <div style={s.dragHandle}>⠿</div>
                  <div style={s.fragContent}>
                    <div style={s.fragMeta}>
                      <span style={s.trackId}>Track {frag.track_id}</span>
                      <span style={s.frameMeta}>
                        {frag.frame_count} frames · {Math.round((frag.last_frame - frag.first_frame) / 30)}s
                      </span>
                    </div>
                    <div style={s.stripScroll}>
                      <div style={s.strip}>
                        {frag.sample_urls.map((url, i) => (
                          <img key={i} src={url} alt="" style={s.thumb} loading="lazy" />
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Drop targets for other persons */}
          {others.length > 0 && (
            <div style={s.dropZones}>
              <div style={s.colHeader}>Drop onto person</div>
              {others.map((p) => (
                <div
                  key={p.person_id}
                  style={{
                    ...s.dropTarget,
                    borderColor: dragOverPerson === p.person_id ? "#7c6aff" : "#333",
                    background: dragOverPerson === p.person_id ? "rgba(124,106,255,0.15)" : "#111",
                  }}
                  onDragOver={(e) => handleDragOver(e, p.person_id)}
                  onDragLeave={handleDragLeave}
                  onDrop={(e) => handleDrop(e, p.person_id)}
                >
                  <img
                    src={p.thumbnail_url}
                    alt={p.person_id}
                    style={s.dropThumb}
                  />
                  <div style={s.dropLabel}>
                    <div style={s.dropName}>{p.person_id}</div>
                    <div style={s.dropMeta}>{p.frame_count} frames</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {reassigning !== null && (
          <div style={s.reassigningBar}>
            Moving track {reassigning}...
          </div>
        )}
      </div>
    </div>
  );
}

const s: Record<string, React.CSSProperties> = {
  overlay: {
    position: "fixed", inset: 0,
    background: "rgba(0,0,0,0.7)",
    display: "flex", alignItems: "center", justifyContent: "center",
    zIndex: 100,
  },
  panel: {
    background: "#1a1a1a",
    borderRadius: 16,
    width: "min(1000px, 95vw)",
    maxHeight: "85vh",
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
  },
  header: {
    display: "flex", alignItems: "center", justifyContent: "space-between",
    padding: "16px 20px",
    borderBottom: "1px solid #2a2a2a",
  },
  title: { fontWeight: 700, fontSize: 16 },
  closeBtn: {
    background: "none", border: "none", color: "#888",
    fontSize: 18, cursor: "pointer", padding: "0 4px",
  },
  body: {
    display: "flex",
    gap: 16,
    padding: "12px 20px",
    overflowY: "auto",
    flex: 1,
  },
  mainCol: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    gap: 8,
    minWidth: 0,
  },
  colHeader: {
    fontSize: 12,
    color: "#666",
    fontWeight: 600,
    textTransform: "uppercase" as const,
    letterSpacing: 0.5,
    marginBottom: 4,
  },
  fragmentList: {
    display: "flex", flexDirection: "column", gap: 10,
  },
  fragRow: {
    background: "#111", borderRadius: 10, padding: 10,
    display: "flex", gap: 8,
    cursor: "grab",
    border: "1px solid #2a2a2a",
    transition: "border-color 0.15s",
  },
  dragHandle: {
    display: "flex",
    alignItems: "center",
    color: "#555",
    fontSize: 16,
    cursor: "grab",
    userSelect: "none" as const,
    flexShrink: 0,
    paddingRight: 4,
  },
  fragContent: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    gap: 6,
    minWidth: 0,
  },
  fragMeta: { display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" },
  trackId: { fontWeight: 700, fontSize: 13, color: "#ccc" },
  frameMeta: { fontSize: 12, color: "#666" },
  stripScroll: { overflowX: "auto" },
  strip: { display: "flex", gap: 4, minWidth: "max-content" },
  thumb: { height: 100, width: "auto", borderRadius: 4, objectFit: "cover", flexShrink: 0 },
  dropZones: {
    width: 180,
    flexShrink: 0,
    display: "flex",
    flexDirection: "column",
    gap: 8,
  },
  dropTarget: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    padding: 10,
    borderRadius: 10,
    border: "2px dashed #333",
    transition: "border-color 0.15s, background 0.15s",
  },
  dropThumb: {
    width: 40,
    height: 56,
    borderRadius: 6,
    objectFit: "cover",
    flexShrink: 0,
  },
  dropLabel: {
    flex: 1,
    minWidth: 0,
  },
  dropName: {
    fontSize: 13,
    fontWeight: 600,
    color: "#ccc",
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis",
  },
  dropMeta: {
    fontSize: 11,
    color: "#666",
  },
  reassigningBar: {
    padding: "10px 20px",
    background: "#222",
    borderTop: "1px solid #2a2a2a",
    fontSize: 13,
    color: "#7c6aff",
    textAlign: "center",
  },
  empty: { padding: 32, textAlign: "center", color: "#666" },
};
