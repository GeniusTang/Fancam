import { useState } from "react";
import { uploadVideo } from "../api/upload";
import { useAppStore } from "../store/appStore";

export function useUpload() {
  const [uploadProgress, setUploadProgress] = useState(0);
  const setJobId = useAppStore((s) => s.setJobId);
  const setPhase = useAppStore((s) => s.setPhase);
  const setError = useAppStore((s) => s.setError);

  async function upload(file: File) {
    try {
      setPhase("analyzing");
      const jobId = await uploadVideo(file, setUploadProgress);
      setJobId(jobId);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Upload failed";
      setError(msg);
    }
  }

  return { upload, uploadProgress };
}
