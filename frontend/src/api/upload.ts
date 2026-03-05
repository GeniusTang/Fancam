import client from "./client";

export async function uploadVideo(
  file: File,
  onProgress?: (pct: number) => void
): Promise<string> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await client.post<{ job_id: string }>("/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
    onUploadProgress: (e) => {
      if (onProgress && e.total) {
        onProgress(e.loaded / e.total);
      }
    },
  });
  return data.job_id;
}
