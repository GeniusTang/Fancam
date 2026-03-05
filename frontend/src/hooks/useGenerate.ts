import { useAppStore } from "../store/appStore";
import { startGeneration } from "../api/generate";

export function useGenerate() {
  const jobId = useAppStore((s) => s.jobId);
  const setSelectedPerson = useAppStore((s) => s.setSelectedPerson);
  const setPhase = useAppStore((s) => s.setPhase);
  const setError = useAppStore((s) => s.setError);

  async function generate(personId: string) {
    if (!jobId) return;
    try {
      setSelectedPerson(personId);
      await startGeneration(jobId, personId);
      setPhase("generating");
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Generation failed";
      setError(msg);
    }
  }

  return { generate };
}
