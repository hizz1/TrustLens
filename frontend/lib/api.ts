export type HealthResponse = {
  status: "ok";
  service: "trustlens-api";
  version: string;
};

export type AnalysisResponse = {
  detection_provider: "offline" | "bitmind";
  provider_used: "offline" | "bitmind";
  fallback_reason: string | null;
  detection_mode: "deepfake" | "ai_generated";
  analysis_id: string;
  filename: string;
  media_type: "image" | "audio" | "video";
  sha256: string;
  size_bytes: number;
  metadata: {
    status: "completed" | "unavailable" | "error";
    format?: Record<string, unknown>;
    streams?: Array<Record<string, unknown>>;
  };
  preprocessing: {
    source_path: string;
    duration_seconds?: number;
    frames?: Array<{ frame_path: string; sample_time_seconds: number }>;
    audio_status: "completed" | "not_applicable" | "unavailable" | "error";
    audio_path?: string;
  };
  visual: {
    is_ai?: boolean | null;
    status: "completed" | "not_applicable" | "unavailable" | "error";
    synthetic_probability?: number;
    confidence?: number;
    findings?: string[];
    model_id?: string | null;
    frame_scores?: Array<{ index: number; path: string; synthetic_probability: number; confidence: number; sample_time_seconds: number }>;
    suspicious_frames?: Array<{ index: number; path: string; synthetic_probability: number; confidence: number; sample_time_seconds: number }>;
    device?: string;
  };
  audio: {
    status: "completed" | "not_applicable" | "unavailable" | "error";
    synthetic_probability?: number;
    confidence?: number;
    findings?: string[];
    device?: string;
  };
  provenance: {
    status: "verified" | "invalid" | "not_present" | "unavailable" | "error";
    verified: boolean;
    details?: string[];
  };
  findings: string[];
  limitations: string[];
  trust_score: number | null;
  risk_level: "high" | "review" | "low" | "unavailable";
};

export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000"
).replace(/\/+$/, "");

export async function getHealth(signal: AbortSignal): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE_URL}/api/health`, { signal, cache: "no-store" });
  if (!response.ok) throw new Error(`Backend returned HTTP ${response.status}.`);
  const data: unknown = await response.json();
  if (!data || typeof data !== "object" || !("status" in data) || data.status !== "ok" ||
      !("service" in data) || data.service !== "trustlens-api" ||
      !("version" in data) || typeof data.version !== "string") {
    throw new Error("Backend returned an unexpected health response.");
  }
  return data as HealthResponse;
}

export async function analyzeFile(file: File, signal: AbortSignal, detectionMode: "deepfake" | "ai_generated" = "deepfake", detectionProvider: "offline" | "bitmind" = "offline"): Promise<AnalysisResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const url = new URL(`${API_BASE_URL}/api/analyze`);
  url.searchParams.append("detection_mode", detectionMode);
  url.searchParams.append("detection_provider", detectionProvider);

  const response = await fetch(url.toString(), {
    method: "POST",
    body: formData,
    signal,
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Backend returned HTTP ${response.status}: ${errorText}`);
  }

  const data: unknown = await response.json();
  if (!data || typeof data !== "object") {
    throw new Error("Backend returned an invalid response.");
  }

  return data as AnalysisResponse;
}

