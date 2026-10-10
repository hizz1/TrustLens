import type { AnalysisResponse } from "@/lib/api";
import { getBitMindScore } from "@/lib/bitmind-score";

export default function ScorePanel({ result }: { result: AnalysisResponse }) {
  const bitmindScore = getBitMindScore(result);
  if (result.provider_used === "bitmind" && result.visual.status === "completed" && typeof result.visual.is_ai === "boolean") {
    const color = bitmindScore === null || bitmindScore === 50 ? "#94a3b8" : bitmindScore < 50 ? "#fb7185" : "#2dd4bf";
    return <section className="score-panel" aria-label="BitMind-derived indicator">
      <div className="score-ring" style={{ color }}>
        <svg viewBox="0 0 160 160" aria-hidden="true">
          <circle cx="80" cy="80" r="68" fill="none" stroke="currentColor" strokeOpacity="0.12" strokeWidth="11" />
          {bitmindScore !== null && <circle cx="80" cy="80" r="68" fill="none" stroke="currentColor" strokeWidth="11" strokeLinecap="round" pathLength="100" strokeDasharray={`${bitmindScore} 100`} transform="rotate(-90 80 80)" />}
        </svg>
        <div className="score-value"><strong>{bitmindScore ?? "N/A"}</strong><span>{bitmindScore !== null ? "/ 100 INDICATOR" : "NO CONFIDENCE"}</span></div>
      </div>
      <div className="min-w-0 flex-1">
        <span className="risk-label" style={{ color }}>BitMind-derived indicator</span>
        <h2 className="mt-3 text-2xl font-bold tracking-tight sm:text-3xl">{result.visual.is_ai ? "AI-generated indicators detected" : "Classified as not AI-generated"}</h2>
        <p className="mt-2 max-w-xl text-sm leading-relaxed text-slate-300">{bitmindScore === null ? "BitMind returned a verdict without usable confidence, so a numeric indicator cannot be calculated." : "Higher values align with a not-AI verdict; lower values align with an AI verdict. 50 is neutral. This display indicator is not a probability of authenticity or forensic proof."}</p>
        <div className="mt-5 grid max-w-lg grid-cols-3 gap-2 sm:gap-3">
          <div className="score-stat"><span>BitMind verdict</span><p className="text-sm">{result.visual.is_ai ? "AI-generated" : "Not AI-generated"}</p></div>
          <div className="score-stat"><span>Vendor confidence</span><p className="text-cyan-300">{bitmindScore !== null ? `${(result.visual.confidence! * 100).toFixed(1)}%` : "Unavailable"}</p></div>
          <div className="score-stat"><span>Local evidence score</span><p className="text-teal-300">{result.trust_score === null ? "Unavailable" : `${result.trust_score}/100`}</p></div>
        </div>
        <p className="mt-3 text-xs leading-relaxed text-slate-400">Calculated as 50 {result.visual.is_ai ? "−" : "+"} (50 × vendor confidence), rounded to a whole number. Audio and provenance remain separate from this indicator.</p>
      </div>
    </section>;
  }
  const visual = result.visual.status === "completed" && typeof result.visual.synthetic_probability === "number";
  const audio = result.audio.status === "completed" && typeof result.audio.synthetic_probability === "number";
  const adjustment = result.provenance.status === "verified" && result.provenance.verified ? 10 : result.provenance.status === "invalid" ? -20 : 0;
  const titles = { high: "Elevated Risk Detected", review: "Requires Manual Review", low: "Lower Risk Indicators", unavailable: "Insufficient Evidence to Score" };
  const labels = { high: "High risk", review: "Review · Moderate trust", low: "Low risk", unavailable: "Score unavailable" };
  const color = result.risk_level === "high" ? "#fb7185" : result.risk_level === "review" ? "#ffb51b" : result.risk_level === "low" ? "#2dd4bf" : "#94a3b8";
  return <section className="score-panel" aria-label="Digital Trust Score">
    <div className="score-ring" style={{ color }}>
      <svg viewBox="0 0 160 160" aria-hidden="true">
        <circle cx="80" cy="80" r="68" fill="none" stroke="currentColor" strokeOpacity="0.12" strokeWidth="11" />
        {result.trust_score !== null && <circle cx="80" cy="80" r="68" fill="none" stroke="currentColor" strokeWidth="11" strokeLinecap="round" pathLength="100" strokeDasharray={`${result.trust_score} 100`} transform="rotate(-90 80 80)" />}
      </svg>
      <div className="score-value"><strong>{result.trust_score ?? "N/A"}</strong><span>{result.trust_score !== null ? "/ 100 SCORE" : "UNAVAILABLE"}</span></div>
    </div>
    <div className="min-w-0 flex-1">
      <span className="risk-label" style={{ color }}><span aria-hidden="true">●</span> {labels[result.risk_level]}</span>
      <h2 className="mt-3 text-2xl font-bold tracking-tight sm:text-3xl">{titles[result.risk_level]}</h2>
      <p className="mt-2 max-w-xl text-sm leading-relaxed text-slate-300">Available visual and audio signals are combined with cryptographic provenance checks. Metadata provides context; missing evidence stays neutral.</p>
      <div className="mt-5 grid max-w-lg grid-cols-3 gap-2 sm:gap-3">
        <div className="score-stat"><span>Visual modality</span><p className="text-teal-300"><b>{visual ? audio ? 60 : 100 : 0}%</b> <small>weight</small></p></div>
        <div className="score-stat"><span>Audio modality</span><p className="text-cyan-300"><b>{audio ? visual ? 40 : 100 : 0}%</b> <small>weight</small></p></div>
        <div className="score-stat"><span>Provenance</span><p className="text-amber-300"><b>{result.trust_score === null ? "N/A" : adjustment > 0 ? `+${adjustment}` : adjustment}</b> <small>pts</small></p></div>
      </div>
    </div>
  </section>;
}
