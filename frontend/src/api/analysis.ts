import client from "./client";
import type { AnalysisResult } from "../types";

export async function fetchAnalysis(jobId: string): Promise<AnalysisResult> {
  const { data } = await client.get<AnalysisResult>(`/analysis/${jobId}`);
  return data;
}
