import client from "./client";
import type { CutSection } from "../types";

export async function startGeneration(
  jobId: string,
  personId: string,
  cuts: CutSection[] = [],
): Promise<void> {
  await client.post("/generate", { job_id: jobId, person_id: personId, cuts });
}

export async function reanalyze(jobId: string): Promise<void> {
  await client.post(`/reanalyze/${jobId}`);
}
