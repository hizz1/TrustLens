"use client";

import { useState } from "react";
import HealthCheck from "@/components/health-check";
import Upload from "@/components/upload";
import Results from "@/components/results";
import { type AnalysisResponse } from "@/lib/api";
import Link from "next/link";

type ViewState = "landing" | "upload" | "results";

export default function Home() {
  const [view, setView] = useState<ViewState>("landing");
  const [analysisResult, setAnalysisResult] = useState<AnalysisResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleAnalysisComplete = (result: AnalysisResponse) => {
    setAnalysisResult(result);
    setView("results");
    setError(null);
  };

  const handleError = (message: string) => {
    setError(message);
  };

  const handleReset = () => {
    setView("upload");
    setAnalysisResult(null);
    setError(null);
  };

  return (
    <div className="mx-auto flex min-h-screen max-w-6xl flex-col px-4 sm:px-8">
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-white/10 py-4">
        <Link href="/" className="flex items-center gap-3">
          <span className="brand-icon"><svg aria-hidden="true" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Z"/><path d="m8 12 3 3 5-6"/></svg></span>
          <span><span className="flex items-center gap-2 text-lg font-bold tracking-tight">TrustLens <span className="rounded-full border border-teal-300/15 bg-teal-300/5 px-2 py-0.5 text-[9px] font-medium tracking-normal text-teal-300">MVP v0.1</span></span><span className="block text-[10px] text-teal-400/80">Multimodal Deepfake & Provenance Analysis</span></span>
        </Link>
        <div className="flex flex-wrap items-center gap-2"><span className="connection-pill text-slate-300">{analysisResult ? analysisResult.provider_used !== "offline" ? "API + local analysis" : "Local inference" : "Local workspace"}</span><HealthCheck compact /></div>
      </header>

      <main className="flex-1 py-8">
        {view === "landing" && (
          <div className="landing-panel grid items-center gap-10 lg:grid-cols-[1.3fr_1fr]">
            <section>
              <p className="mb-6 text-xs font-semibold tracking-[0.22em] text-emerald-200 uppercase">Media authenticity workspace</p>
              <h1 className="max-w-xl text-5xl leading-[1.08] font-semibold tracking-tight sm:text-6xl">A clearer view of<br /><span className="text-emerald-200">media authenticity.</span></h1>
              <p className="mt-7 max-w-lg text-lg leading-relaxed text-slate-300">TrustLens brings visual, audio, and provenance evidence into one explainable Digital Trust Score.</p>
              <div className="mt-8 flex gap-3 text-xs font-medium text-slate-300">
                {["Images", "Audio", "Video"].map((label) => <span key={label} className="rounded-md border border-white/15 px-3 py-2">{label}</span>)}
              </div>
              <button
                onClick={() => setView("upload")}
                className="mt-8 rounded-lg bg-emerald-300/15 px-6 py-3 text-sm font-semibold text-emerald-200 transition hover:bg-emerald-300/25 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-emerald-300"
              >
                Start Analysis
              </button>
            </section>
            <HealthCheck />
          </div>
        )}

        {view === "upload" && (
          <div className="mx-auto max-w-2xl">
            <div className="mb-8 text-center">
              <h1 className="text-3xl font-semibold">Analyze Media</h1>
              <p className="mt-2 text-slate-400">Upload a file to check for authenticity indicators</p>
            </div>
            {error && (
              <div className="mb-6 rounded-lg border border-red-300/30 bg-red-300/10 p-4 text-sm text-red-200">
                <p className="font-medium">Error</p>
                <p className="mt-1">{error}</p>
              </div>
            )}
            <Upload onAnalysisComplete={handleAnalysisComplete} onError={handleError} />
          </div>
        )}

        {view === "results" && analysisResult && (
          <Results result={analysisResult} onReset={handleReset} />
        )}
      </main>

      <footer className="flex flex-col justify-between gap-3 border-t border-white/10 py-6 text-xs leading-relaxed text-slate-400 sm:flex-row">
        <p>Designed to run on your laptop.</p>
        <p>Experimental decision support. Not forensic proof.</p>
      </footer>
    </div>
  );
}
