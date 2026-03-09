import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { AppPhase, Person, SSEEvent } from "../types";

interface AppState {
  phase: AppPhase;
  jobId: string | null;
  sseEvent: SSEEvent | null;
  persons: Person[];
  totalFrames: number;
  selectedPersonId: string | null;
  error: string | null;

  setPhase: (phase: AppPhase) => void;
  setJobId: (id: string) => void;
  setSseEvent: (evt: SSEEvent) => void;
  setPersons: (persons: Person[]) => void;
  setTotalFrames: (n: number) => void;
  setSelectedPerson: (id: string) => void;
  setError: (msg: string) => void;
  reset: () => void;
}

const initial = {
  phase: "upload" as AppPhase,
  jobId: null as string | null,
  sseEvent: null as SSEEvent | null,
  persons: [] as Person[],
  totalFrames: 1,
  selectedPersonId: null as string | null,
  error: null as string | null,
};

// Phases worth persisting: only in-progress phases where losing state
// means losing minutes of work. The backend is in-memory so terminal
// states (complete) and interactive states (select_dancer, correcting)
// can't be resumed after a backend restart anyway.
const PERSIST_PHASES: AppPhase[] = ["analyzing", "generating"];

// On startup, validate persisted state is still resumable.
// Check synchronously first, then verify the job still exists on the backend.
const stored = localStorage.getItem("fancam-app-state");
if (stored) {
  try {
    const parsed = JSON.parse(stored);
    const phase = parsed?.state?.phase;
    const jobId = parsed?.state?.jobId;
    if (!jobId || !PERSIST_PHASES.includes(phase)) {
      localStorage.removeItem("fancam-app-state");
    } else {
      // Verify job still exists on backend (in-memory store lost on restart)
      fetch(`/analysis/${jobId}`)
        .then((r) => {
          if (!r.ok) {
            localStorage.removeItem("fancam-app-state");
            window.location.reload();
          }
        })
        .catch(() => {
          // Backend not reachable yet — clear stale state
          localStorage.removeItem("fancam-app-state");
          window.location.reload();
        });
    }
  } catch {
    localStorage.removeItem("fancam-app-state");
  }
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      ...initial,
      setPhase: (phase) => set({ phase }),
      setJobId: (jobId) => set({ jobId }),
      setSseEvent: (sseEvent) => set({ sseEvent }),
      setPersons: (persons) => set({ persons }),
      setTotalFrames: (totalFrames) => set({ totalFrames }),
      setSelectedPerson: (selectedPersonId) => set({ selectedPersonId }),
      setError: (error) => set({ error, phase: "error" }),
      reset: () => set(initial),
    }),
    {
      name: "fancam-app-state",
      partialize: (state) => {
        if (!PERSIST_PHASES.includes(state.phase)) return {};
        return {
          phase: state.phase,
          jobId: state.jobId,
          selectedPersonId: state.selectedPersonId,
        };
      },
    }
  )
);
