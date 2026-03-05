export type AppPhase =
  | "upload"
  | "analyzing"
  | "select_dancer"
  | "generating"
  | "complete"
  | "error";

export type JobStatus =
  | "pending"
  | "analyzing"
  | "ready_for_selection"
  | "generating"
  | "complete"
  | "error";

export interface SSEEvent {
  status: JobStatus;
  stage: string | null;
  progress: number;
  error?: string;
}

export interface Person {
  person_id: string;
  thumbnail_url: string;
  frame_count: number;
  first_frame: number;
  last_frame: number;
}

export interface AnalysisResult {
  job_id: string;
  persons: Person[];
}
