import client from "./client";

export async function requestPreview(
  jobId: string,
  personId: string
): Promise<{ preview_url: string }> {
  const res = await client.post("/preview", {
    job_id: jobId,
    person_id: personId,
  });
  return res.data;
}
