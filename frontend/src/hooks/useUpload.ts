import { useState } from "react";
import { fetchAnalysis } from "../api/analysis";
import { uploadVideo } from "../api/upload";
import { useAppStore } from "../store/appStore";

export function useUpload() {
  const [uploadProgress, setUploadProgress] = useState(0);
  const setJobId = useAppStore((s) => s.setJobId);
  const setPhase = useAppStore((s) => s.setPhase);
  const setPersons = useAppStore((s) => s.setPersons);
  const setTotalFrames = useAppStore((s) => s.setTotalFrames);
  const setError = useAppStore((s) => s.setError);

  async function upload(file: File) {
    try {
      setPhase("analyzing");
      const { jobId, cached } = await uploadVideo(file, setUploadProgress);
      setJobId(jobId);
      if (cached) {
        const result = await fetchAnalysis(jobId);
        setPersons(result.persons);
        if (result.total_frames) setTotalFrames(result.total_frames);
        setPhase("select_dancer");
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Upload failed";
      setError(msg);
    }
  }

  return { upload, uploadProgress };
}
