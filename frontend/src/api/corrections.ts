import client from "./client";
import type {
  BboxCorrection,
  FrameBbox,
  RedirectResponse,
  TrackDataResponse,
} from "../types";

export async function fetchTrackData(
  jobId: string,
  personId: string
): Promise<TrackDataResponse> {
  const { data } = await client.get<TrackDataResponse>(
    `/corrections/${jobId}/${personId}/track-data`
  );
  return data;
}

export async function submitCorrections(
  jobId: string,
  personId: string,
  corrections: BboxCorrection[]
): Promise<void> {
  await client.post(`/corrections/${jobId}`, {
    person_id: personId,
    corrections,
  });
}

export async function clearCorrections(jobId: string): Promise<void> {
  await client.delete(`/corrections/${jobId}`);
}

export function frameSrc(jobId: string, frameIdx: number): string {
  return `/correction-frame/${jobId}/${frameIdx}`;
}

export async function fetchFrameBboxes(
  jobId: string,
  frameIdx: number
): Promise<FrameBbox[]> {
  const { data } = await client.get<{ bboxes: FrameBbox[] }>(
    `/corrections/${jobId}/frame-bboxes/${frameIdx}`
  );
  return data.bboxes;
}

export async function redirectTracking(
  jobId: string,
  personId: string,
  fromFrame: number,
  toTrackId: number
): Promise<RedirectResponse> {
  const { data } = await client.post<RedirectResponse>(
    `/corrections/${jobId}/redirect`,
    { person_id: personId, from_frame: fromFrame, to_track_id: toTrackId }
  );
  return data;
}

export async function undoRedirect(
  jobId: string,
  personId: string
): Promise<RedirectResponse & { ok: boolean }> {
  const { data } = await client.post<RedirectResponse & { ok: boolean }>(
    `/corrections/${jobId}/undo-redirect`,
    null,
    { params: { person_id: personId } }
  );
  return data;
}
