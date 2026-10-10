import type { AnalysisResponse } from "./api";

// Display convention: zero confidence is neutral; confidence moves the score
// toward the endpoint selected by the verdict. This is not a probability.
export function getBitMindScore(result: Pick<AnalysisResponse, "provider_used" | "visual">): number | null {
  const { visual } = result;
  if (result.provider_used !== "bitmind" || visual.status !== "completed" ||
      typeof visual.is_ai !== "boolean" || typeof visual.confidence !== "number" ||
      !Number.isFinite(visual.confidence) || visual.confidence < 0 || visual.confidence > 1) return null;
  return Math.round(50 + (visual.is_ai ? -1 : 1) * 50 * visual.confidence);
}
