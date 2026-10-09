"use client";

import { type AnalysisResponse } from "@/lib/api";
import EvidenceSummary from "@/components/evidence-summary";

interface ResultsProps {
  result: AnalysisResponse;
  onReset: () => void;
}

export default function Results({ result, onReset }: ResultsProps) {
  const getRiskColor = (level: string) => {
    switch (level) {
      case "high":
        return "text-red-300";
      case "review":
        return "text-amber-300";
      case "low":
        return "text-emerald-300";
      default:
        return "text-slate-300";
    }
  };

  const getRiskBg = (level: string) => {
    switch (level) {
      case "high":
        return "bg-red-300/15 border-red-300/30";
      case "review":
        return "bg-amber-300/15 border-amber-300/30";
      case "low":
        return "bg-emerald-300/15 border-emerald-300/30";
      default:
        return "bg-white/10 border-white/20";
    }
  };

  const getScoreColor = (score: number | null) => {
    if (score === null) return "text-slate-300";
    if (score >= 70) return "text-emerald-300";
    if (score >= 40) return "text-amber-300";
    return "text-red-300";
  };

  const getStatusBadge = (status: string) => {
    const colors: Record<string, string> = {
      completed: "bg-emerald-300/15 text-emerald-200",
      not_applicable: "bg-slate-300/15 text-slate-300",
      unavailable: "bg-amber-300/15 text-amber-200",
      error: "bg-red-300/15 text-red-200",
      verified: "bg-emerald-300/15 text-emerald-200",
      invalid: "bg-red-300/15 text-red-200",
      not_present: "bg-slate-300/15 text-slate-300",
    };
    return colors[status] || "bg-slate-300/15 text-slate-300";
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-semibold">TrustLens Analysis</h2>
        <button
          onClick={onReset}
          className="rounded-lg border border-white/20 px-4 py-2 text-sm font-medium transition hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-emerald-300"
        >
          Analyze another file
        </button>
      </div>

      <p className="text-sm text-slate-300">
        {result.provider_used === "bitmind" ? "AI-generation check with BitMind API" : result.media_type === "video" ? (result.detection_mode === "ai_generated" ? "AI-generated video check (UniFD)" : "Facial deepfake video check") : "Media authenticity check"}
        {result.visual.model_id && <span className="block text-xs text-slate-400">Visual model: {result.visual.model_id}</span>}
      </p>
      {result.fallback_reason && <p role="status" className="rounded-lg border border-amber-300/30 bg-amber-300/10 p-4 text-sm text-amber-200">
        Offline fallback: {result.fallback_reason}
      </p>}
      {result.provider_used === "bitmind" && typeof result.visual.is_ai === "boolean" && <div className="rounded-2xl border border-emerald-300/30 bg-emerald-300/5 p-6">
        <h3 className="text-sm text-slate-300">BitMind API verdict</h3>
        <p className="mt-2 text-2xl font-semibold">{result.visual.is_ai ? "AI-generated indicators detected" : "Classified as not AI-generated"}</p>
        {result.visual.confidence != null && <p className="mt-2 text-sm text-slate-300">BitMind-reported confidence: {(result.visual.confidence * 100).toFixed(1)}%</p>}
        <p className="mt-2 text-xs text-slate-400">This vendor verdict is not forensic proof. The Digital Trust Score below excludes this verdict and uses only available local audio and provenance evidence.</p>
      </div>}
      <div className="rounded-2xl border border-white/15 bg-white/5 p-8 sm:p-10">
        <div className="grid gap-8 lg:grid-cols-2">
          <div>
            <p className="mb-2 text-sm font-medium text-slate-400 uppercase tracking-wider">Digital Trust Score</p>
            <div className="flex items-baseline gap-3">
              <span className={`text-7xl font-bold tracking-tight ${getScoreColor(result.trust_score)}`}>
                {result.trust_score ?? "N/A"}
              </span>
              {result.trust_score !== null && <span className="text-2xl text-slate-400">/ 100</span>}
            </div>
            <div className="mt-4">
              <span className={`inline-block rounded-full px-4 py-1.5 text-sm font-semibold ${getRiskBg(result.risk_level)} ${getRiskColor(result.risk_level)}`}>
                {result.risk_level === "unavailable" ? "Score Unavailable" : result.risk_level.toUpperCase() + " RISK"}
              </span>
            </div>
          </div>

          <div className="space-y-3">
            <p className="text-sm font-medium text-slate-400 uppercase tracking-wider">Analysis Summary</p>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div className="rounded-lg border border-white/15 bg-white/5 p-3">
                <p className="text-xs text-slate-400">Visual Analysis</p>
                <p className="mt-1 font-medium text-slate-200">
                  {result.visual.status === "completed"
                    ? typeof result.visual.is_ai === "boolean"
                      ? result.visual.is_ai ? "AI-generated indicators" : "Not AI-generated (API)"
                      : result.visual.synthetic_probability !== undefined
                      ? result.visual.synthetic_probability > 0.5
                        ? "Elevated Risk"
                        : "Lower Risk"
                      : "Completed"
                    : result.visual.status === "not_applicable"
                    ? "Not Applicable"
                    : "Unavailable"}
                </p>
              </div>
              <div className="rounded-lg border border-white/15 bg-white/5 p-3">
                <p className="text-xs text-slate-400">Audio Analysis</p>
                <p className="mt-1 font-medium text-slate-200">
                  {result.audio.status === "completed"
                    ? result.audio.synthetic_probability !== undefined
                      ? result.audio.synthetic_probability > 0.5
                        ? "Elevated Risk"
                        : "Lower Risk"
                      : "Completed"
                    : result.audio.status === "not_applicable"
                    ? "Not Applicable"
                    : "Unavailable"}
                </p>
              </div>
              <div className="rounded-lg border border-white/15 bg-white/5 p-3">
                <p className="text-xs text-slate-400">Provenance</p>
                <p className="mt-1 font-medium text-slate-200 capitalize">{result.provenance.status === "not_present" ? "Not Present" : result.provenance.status}</p>
              </div>
              <div className="rounded-lg border border-white/15 bg-white/5 p-3">
                <p className="text-xs text-slate-400">Metadata</p>
                <p className="mt-1 font-medium text-slate-200 capitalize">{result.metadata.status}</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <EvidenceSummary result={result} />

      {result.visual.suspicious_frames && result.visual.suspicious_frames.length > 0 && (
        <div className="rounded-2xl border border-white/15 bg-white/5 p-6">
          <h3 className="mb-4 text-lg font-semibold">Suspicious Frames</h3>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {result.visual.suspicious_frames.map((frame, idx) => (
              <div key={idx} className="rounded-lg border border-white/15 bg-white/5 p-3">
                <div className="mb-2 flex items-center justify-between">
                  <span className="text-xs text-slate-400">Frame {frame.index + 1}</span>
                  <span className="rounded bg-red-300/15 px-2 py-0.5 text-xs font-medium text-red-300">
                    {(frame.synthetic_probability * 100).toFixed(0)}% synthetic
                  </span>
                </div>
                <p className="text-xs text-slate-400">Time: {frame.sample_time_seconds.toFixed(1)}s</p>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="rounded-2xl border border-white/15 bg-white/5 p-6">
        <h3 className="mb-4 text-lg font-semibold">Technical Details</h3>
        <div className="grid gap-4 text-sm sm:grid-cols-2">
          <div>
            <p className="text-xs text-slate-400">Filename</p>
            <p className="mt-1 font-mono text-slate-200">{result.filename}</p>
          </div>
          <div>
            <p className="text-xs text-slate-400">Media Type</p>
            <p className="mt-1 text-slate-200 capitalize">{result.media_type}</p>
          </div>
          <div>
            <p className="text-xs text-slate-400">SHA-256</p>
            <p className="mt-1 font-mono text-xs text-slate-200 break-all">{result.sha256}</p>
          </div>
          <div>
            <p className="text-xs text-slate-400">File Size</p>
            <p className="mt-1 text-slate-200">{(result.size_bytes /1024 /1024).toFixed(2)} MB</p>
          </div>
          <div>
            <p className="text-xs text-slate-400">Visual Status</p>
            <p className="mt-1">
              <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${getStatusBadge(result.visual.status)}`}>
                {result.visual.status}
              </span>
              {result.visual.device && <span className="ml-2 text-xs text-slate-400">({result.visual.device})</span>}
            </p>
          </div>
          <div>
            <p className="text-xs text-slate-400">Audio Status</p>
            <p className="mt-1">
              <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${getStatusBadge(result.audio.status)}`}>
                {result.audio.status}
              </span>
              {result.audio.device && <span className="ml-2 text-xs text-slate-400">({result.audio.device})</span>}
            </p>
          </div>
        </div>
      </div>

      <div className="rounded-2xl border border-amber-300/20 bg-amber-300/5 p-6">
        <h3 className="mb-3 text-sm font-semibold text-amber-200">Limitations & Disclaimer</h3>
        <ul className="space-y-2 text-xs text-slate-300">
          {result.limitations.map((limitation, idx) => (
            <li key={idx} className="flex items-start gap-2">
              <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-amber-300" />
              {limitation}
            </li>
          ))}
          <li className="flex items-start gap-2">
            <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-amber-300" />
            Higher scores indicate that available evidence is more consistent with authentic media. The Digital Trust Score is an experimental decision-support metric and is not forensic proof.
          </li>
        </ul>
      </div>
    </div>
  );
}

