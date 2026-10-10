"use client";

import { type AnalysisResponse } from "@/lib/api";
import ScorePanel from "@/components/score-panel";
import EvidenceSummary from "@/components/evidence-summary";
import RealityDefenderResults from "@/components/reality-defender-results";

interface ResultsProps {
  result: AnalysisResponse;
  onReset: () => void;
}

export default function Results({ result, onReset }: ResultsProps) {
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
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-2xl font-semibold">TrustLens Analysis</h2>
        <button
          onClick={onReset}
          className="rounded-lg border border-white/20 px-4 py-2 text-sm font-medium transition hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-emerald-300"
        >
          Analyze another file
        </button>
      </div>

      <p className="text-sm text-slate-300">
        {result.provider_used === "reality_defender" ? "Reality Defender API detection with independent local analysis" : result.provider_used === "bitmind" ? "AI-generation check with BitMind API" : result.media_type === "video" ? (result.detection_mode === "ai_generated" ? "AI-generated video check (UniFD)" : "Facial deepfake video check") : "Media authenticity check"}
        {result.visual.model_id && <span className="block text-xs text-slate-400">Visual model: {result.visual.model_id}</span>}
      </p>
      {result.fallback_reason && <p role="status" className="rounded-lg border border-amber-300/30 bg-amber-300/10 p-4 text-sm text-amber-200">
        Offline fallback: {result.fallback_reason}
      </p>}
      {result.provider_used === "bitmind" && typeof result.visual.is_ai === "boolean" && <div className="rounded-2xl border border-emerald-300/30 bg-emerald-300/5 p-6">
        <h3 className="text-sm text-slate-300">BitMind API verdict</h3>
        <p className="mt-2 text-2xl font-semibold">{result.visual.is_ai ? "AI-generated indicators detected" : "Classified as not AI-generated"}</p>
        {result.visual.confidence != null && <p className="mt-2 text-sm text-slate-300">BitMind-reported confidence: {(result.visual.confidence * 100).toFixed(1)}%</p>}
        <p className="mt-2 text-xs text-slate-400">The indicator below maps this verdict and confidence onto a 0–100 display scale. It is separate from the local Digital Trust Score and is not forensic proof.</p>
      </div>}
      {result.reality_defender && <RealityDefenderResults result={result.reality_defender} />}
      {result.reality_defender && <h2 className="text-xl font-semibold">Independent local evidence & provenance</h2>}
      <ScorePanel result={result} />

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
            <p className="mt-1 font-mono text-slate-200 break-all">{result.filename}</p>
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

