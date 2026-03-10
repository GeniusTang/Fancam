import client from "./client";

export async function uploadVideo(
  file: File,
  onProgress?: (pct: number) => void
): Promise<{ jobId: string; cached: boolean }> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await client.post<{ job_id: string; cached?: boolean }>("/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
    onUploadProgress: (e) => {
      if (onProgress && e.total) {
        onProgress(e.loaded / e.total);
      }
    },
  });
  return { jobId: data.job_id, cached: !!data.cached };
}
