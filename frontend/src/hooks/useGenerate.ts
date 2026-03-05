import { useAppStore } from "../store/appStore";
import { requestPreview } from "../api/preview";

export function useGenerate() {
  const jobId = useAppStore((s) => s.jobId);
  const setSelectedPerson = useAppStore((s) => s.setSelectedPerson);
  const setPhase = useAppStore((s) => s.setPhase);
  const setPreviewUrl = useAppStore((s) => s.setPreviewUrl);
  const setError = useAppStore((s) => s.setError);

  async function generate(personId: string) {
    if (!jobId) return;
    try {
      setSelectedPerson(personId);
      setPhase("previewing");
      setPreviewUrl(null);

      const result = await requestPreview(jobId, personId);
      setPreviewUrl(result.preview_url);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Preview failed";
      setError(msg);
    }
  }

  return { generate };
}
