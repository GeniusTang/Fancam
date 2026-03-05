import { useEffect, useRef } from "react";
import { useAppStore } from "../store/appStore";
import { fetchAnalysis } from "../api/analysis";
import type { SSEEvent } from "../types";

const RECONNECT_DELAY = 2000; // ms

export function useJobStatus(jobId: string | null) {
  const setSseEvent = useAppStore((s) => s.setSseEvent);
  const setPhase = useAppStore((s) => s.setPhase);
  const setPersons = useAppStore((s) => s.setPersons);
  const setTotalFrames = useAppStore((s) => s.setTotalFrames);
  const setError = useAppStore((s) => s.setError);
  const esRef = useRef<EventSource | null>(null);
  const closedRef = useRef(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!jobId) return;
    closedRef.current = false;

    function connect() {
      if (closedRef.current) return;

      // Clean up previous connection
      esRef.current?.close();

      const es = new EventSource(`/sse/${jobId}`);
      esRef.current = es;

      es.onmessage = async (e) => {
        const evt: SSEEvent = JSON.parse(e.data);
        setSseEvent(evt);

        if (evt.status === "ready_for_selection") {
          shutdown();
          try {
            const result = await fetchAnalysis(jobId);
            setPersons(result.persons);
            if (result.total_frames) setTotalFrames(result.total_frames);
            setPhase("select_dancer");
          } catch {
            setError("Failed to load analysis results");
          }
        } else if (evt.status === "generating") {
          setPhase("generating");
        } else if (evt.status === "complete") {
          shutdown();
          setPhase("complete");
        } else if (evt.status === "error") {
          shutdown();
          setError(evt.error ?? "Unknown error");
        }
      };

      es.onerror = () => {
        // Don't treat as fatal — reconnect after delay
        es.close();
        if (!closedRef.current) {
          timerRef.current = setTimeout(connect, RECONNECT_DELAY);
        }
      };
    }

    function shutdown() {
      closedRef.current = true;
      esRef.current?.close();
      esRef.current = null;
      if (timerRef.current) clearTimeout(timerRef.current);
    }

    // Reconnect when tab becomes visible again (after screen lock/switch)
    function onVisibility() {
      if (document.visibilityState === "visible" && !closedRef.current) {
        connect();
      }
    }

    connect();
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      shutdown();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [jobId]);
}
