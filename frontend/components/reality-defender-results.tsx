import type { RealityDefenderResult } from "@/lib/api";

const verdictLabels: Record<string, string> = {
  AUTHENTIC: "Classified as authentic", FAKE: "Manipulation detected", SUSPICIOUS: "Suspicious · review recommended",
  NOT_APPLICABLE: "Detection not applicable", UNABLE_TO_EVALUATE: "Unable to evaluate",
  ANALYZING: "Still processing", DOWNLOADING: "Still processing", UNKNOWN: "Detection unavailable",
};

export default function RealityDefenderResults({ result }: { result: RealityDefenderResult }) {
  const score = result.indicator_score;
  const color = result.verdict === "FAKE" ? "#fb7185" : result.verdict === "AUTHENTIC" ? "#2dd4bf" : "#fbbf24";
  return <section aria-labelledby="reality-defender-heading" className="space-y-5">
    <div className="score-panel">
      <div className="score-ring" style={{ color }}>
        <svg viewBox="0 0 160 160" aria-hidden="true">
          <circle cx="80" cy="80" r="68" fill="none" stroke="currentColor" strokeOpacity="0.12" strokeWidth="11" />
          {score !== null && <circle cx="80" cy="80" r="68" fill="none" stroke="currentColor" strokeWidth="11" strokeLinecap="round" pathLength="100" strokeDasharray={`${score} 100`} transform="rotate(-90 80 80)" />}
        </svg>
        <div className="score-value"><strong>{score ?? "N/A"}</strong><span>{score === null ? "NO NUMERIC SCORE" : "/ 100 INDICATOR"}</span></div>
      </div>
      <div className="min-w-0 flex-1">
        <span className="risk-label" style={{ color }}>Reality Defender · {result.status.replaceAll("_", " ")}</span>
        <h2 id="reality-defender-heading" className="mt-3 text-2xl font-bold tracking-tight">{verdictLabels[result.verdict] ?? "Detection unavailable"}</h2>
        <p className="mt-2 text-sm leading-relaxed text-slate-300">{result.message}</p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <div className="score-stat"><span>Vendor manipulation score · higher is more suspicious</span><p>{result.manipulation_score !== null ? `${result.manipulation_score.toFixed(1)} / 100` : "Not supplied"}</p></div>
          <div className="score-stat"><span>Vendor verdict</span><p>{result.verdict === "FAKE" ? "MANIPULATED" : result.verdict.replaceAll("_", " ")}</p></div>
        </div>
        <p className="mt-3 text-xs leading-relaxed text-slate-400">{score === null
          ? "No numeric vendor score was returned. Independent local analysis and provenance results are shown below. An unavailable API result does not mean the media is authentic or manipulated."
          : "The ring shows 100 minus the vendor ensemble manipulation score, rounded. Higher values indicate weaker manipulation signals. It is separate from the local trust score and is not a probability or forensic proof."}</p>
      </div>
    </div>
    {result.models.length > 0 && <div className="grid gap-4 sm:grid-cols-2">
      {result.models.map((model, index) => <article key={`${model.name}-${index}`} className="assessment-card">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <h3 className="break-all text-sm font-semibold">{model.name}</h3>
          <span className="text-[10px] text-slate-400">{model.status === "FAKE" ? "MANIPULATED" : model.status.replaceAll("_", " ")}</span>
        </div>
        <p className="mt-3 text-xs text-slate-300">{model.manipulation_score !== null ? `Manipulation score: ${model.manipulation_score.toFixed(1)} / 100` : "No numeric model score returned."}</p>
        {model.manipulation_score !== null && <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/10" role="meter" aria-label={`${model.name} manipulation score`} aria-valuenow={model.manipulation_score} aria-valuemin={0} aria-valuemax={100}>
          <div className="h-full bg-cyan-300" style={{ width: `${model.manipulation_score}%` }} />
        </div>}
      </article>)}
    </div>}
    {result.request_id && <p className="break-all text-xs text-slate-400">Reality Defender request: <span className="font-mono">{result.request_id}</span></p>}
  </section>;
}
