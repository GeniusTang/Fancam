export type AppPhase =
  | "upload"
  | "analyzing"
  | "select_dancer"
  | "previewing"
  | "generating"
  | "complete"
  | "error";

export type JobStatus =
  | "pending"
  | "analyzing"
  | "ready_for_selection"
  | "previewing"
  | "generating"
  | "complete"
  | "error";

export interface SSEEvent {
  status: JobStatus;
  stage: string | null;
  progress: number;
  error?: string;
  eta?: number | null;
}

export interface TrackSpan {
  start: number;
  end: number;
}

export interface Person {
  person_id: string;
  thumbnail_url: string;
  frame_count: number;
  first_frame: number;
  last_frame: number;
  track_spans?: TrackSpan[];
}

export interface AnalysisResult {
  job_id: string;
  total_frames?: number;
  persons: Person[];
}
