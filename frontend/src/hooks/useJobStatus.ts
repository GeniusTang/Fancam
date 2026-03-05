import { useEffect, useRef } from "react";
import { useAppStore } from "../store/appStore";
import { fetchAnalysis } from "../api/analysis";
import type { SSEEvent } from "../types";

export function useJobStatus(jobId: string | null) {
  const setSseEvent = useAppStore((s) => s.setSseEvent);
  const setPhase = useAppStore((s) => s.setPhase);
  const setPersons = useAppStore((s) => s.setPersons);
  const setError = useAppStore((s) => s.setError);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!jobId) return;

    const es = new EventSource(`/sse/${jobId}`);
    esRef.current = es;

    es.onmessage = async (e) => {
      const evt: SSEEvent = JSON.parse(e.data);
      setSseEvent(evt);

      if (evt.status === "ready_for_selection") {
        es.close();
        try {
          const result = await fetchAnalysis(jobId);
          setPersons(result.persons);
          setPhase("select_dancer");
        } catch {
          setError("Failed to load analysis results");
        }
      } else if (evt.status === "generating") {
        setPhase("generating");
      } else if (evt.status === "complete") {
        es.close();
        setPhase("complete");
      } else if (evt.status === "error") {
        es.close();
        setError(evt.error ?? "Unknown error");
      }
    };

    es.onerror = () => {
      es.close();
    };

    return () => {
      es.close();
    };
  }, [jobId]);
}
