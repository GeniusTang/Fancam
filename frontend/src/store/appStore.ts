import { create } from "zustand";
import type { AppPhase, Person, SSEEvent } from "../types";

interface AppState {
  phase: AppPhase;
  jobId: string | null;
  sseEvent: SSEEvent | null;
  persons: Person[];
  selectedPersonId: string | null;
  error: string | null;

  setPhase: (phase: AppPhase) => void;
  setJobId: (id: string) => void;
  setSseEvent: (evt: SSEEvent) => void;
  setPersons: (persons: Person[]) => void;
  setSelectedPerson: (id: string) => void;
  setError: (msg: string) => void;
  reset: () => void;
}

const initial = {
  phase: "upload" as AppPhase,
  jobId: null,
  sseEvent: null,
  persons: [],
  selectedPersonId: null,
  error: null,
};

export const useAppStore = create<AppState>((set) => ({
  ...initial,
  setPhase: (phase) => set({ phase }),
  setJobId: (jobId) => set({ jobId }),
  setSseEvent: (sseEvent) => set({ sseEvent }),
  setPersons: (persons) => set({ persons }),
  setSelectedPerson: (selectedPersonId) => set({ selectedPersonId }),
  setError: (error) => set({ error, phase: "error" }),
  reset: () => set(initial),
}));
