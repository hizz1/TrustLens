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
    <div className="mx-auto flex min-h-screen max-w-6xl flex-col px-6 sm:px-10">
      <header className="flex items-center justify-between border-b border-white/10 py-7">
        <Link href="/" className="text-xl font-bold tracking-tight">Trust<span className="text-emerald-200">Lens</span><span className="sr-only"> home</span></Link>
        <span className="text-xs tracking-widest text-slate-400 uppercase">Local-first prototype</span>
      </header>

      <main className="flex-1 py-12">
        {view === "landing" && (
          <div className="grid items-center gap-12 lg:grid-cols-[1.3fr_1fr] lg:gap-20">
            <section>
              <p className="mb-6 text-xs font-semibold tracking-[0.22em] text-emerald-200 uppercase">Phase 07 / Dashboard</p>
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
