import client from "./client";

export async function startGeneration(jobId: string, personId: string): Promise<void> {
  await client.post("/generate", { job_id: jobId, person_id: personId });
}
