import type { ReactNode } from "react";
import type { AnalysisResponse } from "@/lib/api";

type Tone = "rose" | "emerald" | "amber" | "slate";
const palette: Record<Tone, { text: string; surface: string; bar: string }> = {
  rose: { text: "text-rose-300", surface: "border-rose-300/20 bg-rose-300/5", bar: "bg-rose-300" },
  emerald: { text: "text-emerald-300", surface: "border-emerald-300/20 bg-emerald-300/5", bar: "bg-emerald-300" },
  amber: { text: "text-amber-300", surface: "border-amber-300/20 bg-amber-300/5", bar: "bg-amber-300" },
  slate: { text: "text-slate-300", surface: "border-white/10 bg-white/[0.025]", bar: "bg-slate-400" },
};

function Icon({ kind }: { kind: "visual" | "audio" | "provenance" | "metadata" }) {
  const paths = {
    visual: <><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" /><circle cx="12" cy="12" r="3" /></>,
    audio: <><path d="M4 10v4m4-7v10m4-14v18m4-14v10m4-7v4" /></>,
    provenance: <><path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Z" /><path d="m8 12 3 3 5-6" /></>,
    metadata: <><rect x="4" y="3" width="16" height="18" rx="3" /><path d="M8 8h8M8 12h8M8 16h4" /></>,
  };
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5">{paths[kind]}</svg>;
}

function Card({ kind, title, label, description, tone, children }: {
  kind: "visual" | "audio" | "provenance" | "metadata";
  title: string; label: string; description: string; tone: Tone; children?: ReactNode;
}) {
  return <article className={`flex min-w-0 flex-col rounded-2xl border p-5 transition-colors hover:bg-white/[0.06] ${palette[tone].surface}`}>
    <div className="flex items-center justify-between gap-3">
      <h4 className="text-xs font-medium uppercase tracking-widest text-slate-400">{title}</h4>
      <span className={`rounded-xl bg-white/5 p-2.5 ${palette[tone].text}`}><Icon kind={kind} /></span>
    </div>
    <p className={`mt-4 text-lg font-semibold leading-snug ${palette[tone].text}`}>{label}</p>
    <p className="mt-2 text-sm leading-relaxed text-slate-400">{description}</p>
    {children && <div className="mt-auto pt-5">{children}</div>}
  </article>;
}

function Meter({ value, label, tone }: { value: number; label: string; tone: Tone }) {
  const percent = Math.max(0, Math.min(100, value * 100));
  return <div>
    <div className="mb-2 flex items-center justify-between gap-2 text-xs">
      <span className="text-slate-400">{label}</span><span className={`font-mono ${palette[tone].text}`}>{percent.toFixed(1)}%</span>
    </div>
    <div role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent} className="h-1.5 overflow-hidden rounded-full bg-white/10">
      <div className={`h-full rounded-full ${palette[tone].bar}`} style={{ width: `${percent}%` }} />
    </div>
  </div>;
}

export default function EvidenceSummary({ result }: { result: AnalysisResponse }) {
  const visual = result.visual;
  const audio = result.audio;
  const apiVerdict = result.provider_used === "bitmind" && visual.status === "completed" && typeof visual.is_ai === "boolean";
  const visualScore = visual.status === "completed" && typeof visual.synthetic_probability === "number" ? visual.synthetic_probability : null;
  const audioScore = audio.status === "completed" && typeof audio.synthetic_probability === "number" ? audio.synthetic_probability : null;
  const visualElevated = apiVerdict ? visual.is_ai : visualScore !== null ? visualScore >= 0.5 : null;
  const visualTone: Tone = visualElevated === true ? "rose" : visualElevated === false ? "emerald" : visual.status === "not_applicable" ? "slate" : "amber";
  const audioTone: Tone = audioScore !== null ? audioScore >= 0.5 ? "rose" : "emerald" : audio.status === "not_applicable" ? "slate" : "amber";
  const visualLabel = visualElevated === true ? "AI indicators detected" : visualElevated === false ? "Low AI indicators" : visual.status === "not_applicable" ? "Not applicable" : "No visual verdict";
  const provenance = result.provenance;
  const verified = provenance.status === "verified" && provenance.verified;
  const provenanceTone: Tone = verified ? "emerald" : provenance.status === "invalid" ? "rose" : provenance.status === "not_present" ? "slate" : "amber";
  const frames = visual.status === "completed" ? visual.frame_scores ?? [] : [];
  const elevatedFrames = frames.filter(frame => frame.synthetic_probability >= 0.5).length;
  const confidence = visual.status === "completed" && typeof visual.confidence === "number" ? visual.confidence : null;

  return <section aria-labelledby="evidence-heading" className="overflow-hidden rounded-3xl border border-white/15 bg-gradient-to-br from-white/[0.06] via-white/[0.02] to-emerald-950/20">
    <div className="border-b border-white/10 px-6 py-6 sm:px-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.25em] text-emerald-300">The evidence at a glance</p>
          <h3 id="evidence-heading" className="text-2xl font-semibold tracking-tight">Key findings</h3>
        </div>
        <span className="rounded-full border border-white/15 bg-white/5 px-3 py-1.5 text-xs text-slate-300">
          {result.provider_used === "bitmind" ? "BitMind API + local checks" : "Local model analysis"}
        </span>
      </div>
      <p className="mt-3 max-w-2xl text-sm leading-relaxed text-slate-400">Four perspectives on your media. Detection signals, source credentials, and file information tell different parts of the story.</p>
    </div>

    <div className="space-y-5 p-6 sm:p-8">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Card kind="visual" title="Visual evidence" label={apiVerdict ? visual.is_ai ? "Flagged as AI-generated" : "Classified as not AI" : visualLabel} tone={visualTone}
          description={apiVerdict ? "BitMind’s whole-file verdict. This does not establish authenticity." : visualScore !== null ? "The local detector found visual patterns associated with synthetic media." : visual.status === "not_applicable" ? "This file has no visual content to assess." : "The visual detector could not produce a usable result."}>
          {apiVerdict && confidence !== null ? <Meter value={confidence} label="Vendor confidence" tone={visualTone} /> : visualScore !== null ? <Meter value={visualScore} label="Synthetic model score" tone={visualTone} /> : <p className="text-xs text-slate-500">No visual score available</p>}
        </Card>
        <Card kind="audio" title="Audio evidence" label={audioScore !== null ? audioScore >= 0.5 ? "Synthetic speech indicators" : "Low synthetic indicators" : audio.status === "not_applicable" ? "No applicable audio" : "Audio check unavailable"} tone={audioTone}
          description={audioScore !== null ? "Speech was assessed independently by the local audio model." : audio.status === "not_applicable" ? "No audio evidence contributes to this result. This is neutral." : "Audio could not be assessed; it is excluded from scoring."}>
          {audioScore !== null ? <Meter value={audioScore} label="Synthetic model score" tone={audioTone} /> : <span className="text-xs text-slate-500">Excluded from the score</span>}
        </Card>
        <Card kind="provenance" title="Source credentials" label={verified ? "Credentials verified" : provenance.status === "invalid" ? "Credential check failed" : provenance.status === "not_present" ? "No credentials found" : "Could not verify"} tone={provenanceTone}
          description={verified ? "Content Credentials passed verification. Provenance alone does not prove that content is real." : provenance.status === "invalid" ? "The available credentials failed verification. Review the source and original file." : "Missing or unverifiable credentials are neutral, not evidence of manipulation."}>
          <span className={`inline-flex rounded-full border border-current/20 px-2.5 py-1 text-[11px] ${palette[provenanceTone].text}`}>{verified ? "C2PA verified" : provenance.status === "invalid" ? "Needs review" : "Neutral evidence"}</span>
        </Card>
        <Card kind="metadata" title="File information" label={result.metadata.status === "completed" ? "File inspected" : "Details unavailable"} tone="slate"
          description={result.metadata.status === "completed" ? "Technical properties were read from the file. Metadata alone cannot establish authenticity." : "File information could not be fully read. Missing metadata is neutral."}>
          <div className="flex flex-wrap gap-2 text-[11px] text-slate-300">
            <span className="rounded-md bg-white/5 px-2 py-1 uppercase">{result.media_type}</span>
            <span className="rounded-md bg-white/5 px-2 py-1">{(result.size_bytes / 1024 / 1024).toFixed(2)} MB</span>
          </div>
        </Card>
      </div>

      {frames.length > 0 && <div className="rounded-2xl border border-white/10 bg-black/10 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div><h4 className="text-sm font-semibold">Visual signals across the clip</h4><p className="mt-1 text-xs text-slate-400">{elevatedFrames} of {frames.length} sampled frames scored at least 0.5.</p></div>
          <span className="text-xs text-slate-400">Synthetic model score · 0–100%</span>
        </div>
        <div className="mt-5 flex gap-1.5 sm:gap-3" role="list" aria-label="Sampled frame scores">
          {frames.map(frame => <div key={frame.index} role="listitem" className="min-w-0 flex-1 text-center" title={`Frame ${frame.index + 1} · target ${frame.sample_time_seconds.toFixed(1)}s · ${(frame.synthetic_probability * 100).toFixed(1)}%`}>
            <span className="sr-only">Frame {frame.index + 1}, target time {frame.sample_time_seconds.toFixed(1)} seconds, score {(frame.synthetic_probability * 100).toFixed(1)} percent.</span>
            <div aria-hidden="true" className="relative flex h-24 items-end overflow-hidden rounded-md bg-white/5">
              <div className={`w-full rounded-t-sm ${frame.synthetic_probability >= 0.5 ? "bg-rose-300/75" : "bg-emerald-300/60"}`} style={{ height: `${frame.synthetic_probability * 100}%` }} />
              <div className="absolute inset-x-0 top-1/2 border-t border-dashed border-white/25" />
            </div>
            <span aria-hidden="true" className="mt-2 block text-[10px] tabular-nums text-slate-500">{frame.index + 1}</span>
          </div>)}
        </div>
        <p className="mt-3 text-xs leading-relaxed text-slate-500">Dashed line: 0.5 threshold. Frames are sampled, not a continuous scan. Higher bars indicate stronger model signals, not proof of manipulation.</p>
      </div>}

      <div className="flex gap-3 rounded-xl bg-white/[0.035] p-4">
        <span className="mt-0.5 shrink-0 text-slate-400"><Icon kind="provenance" /></span>
        <p className="text-xs leading-relaxed text-slate-400">{apiVerdict ? "BitMind confidence is a vendor-reported metric, not a probability of authenticity. The API verdict is separate from the Digital Trust Score." : "Model scores are experimental and uncalibrated. Low signals do not guarantee authenticity, and missing evidence is never treated as proof of a fake."}</p>
      </div>

      <details className="group rounded-xl border border-white/10">
        <summary className="cursor-pointer rounded-xl px-5 py-4 text-sm font-medium text-slate-300 transition-colors hover:bg-white/5 focus-visible:outline-2 focus-visible:outline-emerald-300">Explore the full findings <span className="ml-2 text-xs font-normal text-slate-500">{result.findings.length} notes</span></summary>
        {result.findings.length > 0 ? <ol className="space-y-4 border-t border-white/10 p-5">
          {result.findings.map((finding, index) => <li key={index} className="flex gap-3 text-sm leading-relaxed text-slate-400"><span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-white/5 font-mono text-[10px] text-slate-500">{index + 1}</span><span>{finding}</span></li>)}
        </ol> : <p className="px-5 pb-5 text-sm text-slate-400">No additional findings reported.</p>}
      </details>
    </div>
  </section>;
}
