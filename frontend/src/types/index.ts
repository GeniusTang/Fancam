export type AppPhase =
  | "upload"
  | "analyzing"
  | "select_dancer"
  | "correcting"
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

export interface BboxCorrection {
  frame_idx: number;
  action: "set" | "delete";
  xyxy?: [number, number, number, number];
}

export interface JumpInfo {
  frame: number;
  distance: number;
}

export interface VideoInfo {
  width: number;
  height: number;
  total_frames: number;
  fps: number;
}

export interface TrackDataResponse {
  frame_track_map: Record<string, [number, number, number, number]>;
  corrections: Record<string, BboxCorrection>;
  jumps: JumpInfo[];
  video_info: VideoInfo;
}

export interface FrameBbox {
  track_id: number;
  person_id: string | null;
  xyxy: [number, number, number, number];
  conf: number;
}

export interface RedirectInfo {
  from_frame: number;
  to_track_id: number;
}

export interface RedirectResponse {
  frame_track_map: Record<string, [number, number, number, number]>;
  jumps: JumpInfo[];
  redirects: RedirectInfo[];
}

export interface CutSection {
  start: number;  // first frame to cut (inclusive)
  end: number;    // last frame to cut (inclusive)
}
