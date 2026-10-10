"use client";

import { useEffect, useState } from "react";
import { API_BASE_URL, getHealth } from "@/lib/api";

type State = { status: "checking" | "connected" | "offline"; message: string };

export default function HealthCheck({ compact = false }: { compact?: boolean }) {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<State>({ status: "checking", message: "Contacting local backend…" });

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    const timeout = setTimeout(() => controller.abort(), 5000);
    getHealth(controller.signal)
      .then((health) => { if (active) setState({ status: "connected", message: `API v${health.version} is ready` }); })
      .catch(() => { if (active) setState({ status: "offline", message: "Could not reach the backend. Start the API and retry." }); })
      .finally(() => clearTimeout(timeout));
    return () => { active = false; clearTimeout(timeout); controller.abort(); };
  }, [attempt]);

  if (compact) return <button title={state.message} onClick={() => { setState({ status: "checking", message: "Contacting local backend…" }); setAttempt(value => value + 1); }} disabled={state.status === "checking"} className={`connection-pill ${state.status === "connected" ? "text-teal-300" : "text-amber-300"}`} aria-live="polite"><span aria-hidden="true">●</span> {state.status === "connected" ? `Backend online · ${state.message.replace("API ", "").replace(" is ready", "")}` : state.status === "checking" ? "Connecting…" : "Backend offline · Retry"}</button>;

  return (
    <section aria-labelledby="connection-heading" className="rounded-2xl border border-white/15 bg-white/5 p-6 sm:p-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h2 id="connection-heading" className="text-lg font-semibold">Local connection</h2>
        <span className={`rounded-full px-3 py-1 text-xs font-semibold ${state.status === "connected" ? "bg-emerald-300/15 text-emerald-200" : "bg-white/10 text-slate-200"}`}>
          {state.status === "connected" ? "Backend online" : state.status === "checking" ? "Checking" : "Backend offline"}
        </span>
      </div>
      <p role="status" aria-live="polite" className="mt-5 text-sm text-slate-300">{state.message}</p>
      <p className="mt-2 break-all font-mono text-xs text-slate-400">{API_BASE_URL}/api/health</p>
      <button disabled={state.status === "checking"} onClick={() => {
        setState({ status: "checking", message: "Contacting local backend…" });
        setAttempt((value) => value + 1);
      }} className="mt-6 rounded-lg border border-white/20 px-4 py-2 text-sm font-medium transition hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-emerald-300 disabled:opacity-50">
        Check connection
      </button>
    </section>
  );
}
