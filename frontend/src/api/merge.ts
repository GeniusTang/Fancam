import client from "./client";
import type { AnalysisResult } from "../types";

export async function mergePersons(jobId: string, personIds: string[]): Promise<AnalysisResult> {
  const { data } = await client.post<AnalysisResult>("/merge", {
    job_id: jobId,
    person_ids: personIds,
  });
  return data;
}
