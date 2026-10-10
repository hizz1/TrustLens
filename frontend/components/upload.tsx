"use client";

import { useCallback, useState } from "react";
import { analyzeFile, type AnalysisResponse } from "@/lib/api";

type UploadState = "idle" | "uploading" | "analyzing" | "complete" | "error";
type DetectionMode = "deepfake" | "ai_generated";

interface UploadProps {
  onAnalysisComplete: (result: AnalysisResponse) => void;
  onError: (error: string) => void;
}

export default function Upload({ onAnalysisComplete, onError }: UploadProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [state, setState] = useState<UploadState>("idle");
  const [stage, setStage] = useState<string>("");
  const [dragActive, setDragActive] = useState(false);
  const [detectionMode, setDetectionMode] = useState<DetectionMode>("deepfake");
  const [detectionProvider, setDetectionProvider] = useState<"bitmind" | "offline" | "reality_defender">("bitmind");
  const isVideo = selectedFile ? /\.mp4$/i.test(selectedFile.name) : false;
  const isAudio = selectedFile ? /\.(wav|mp3)$/i.test(selectedFile.name) : false;

  const processFile = useCallback(async (file: File) => {
    const validExtensions = [".jpg", ".jpeg", ".png", ".mp4", ".wav", ".mp3"];
    const fileExt = "." + file.name.split(".").pop()?.toLowerCase();

    if (!validExtensions.includes(fileExt)) {
      onError(`Unsupported file type: ${fileExt}. Supported: JPG, JPEG, PNG, MP4, WAV, MP3`);
      return;
    }

    setState("uploading");
    setStage("Uploading and analyzing media...");

    const controller = new AbortController();

    try {
      const result = await analyzeFile(file, controller.signal, fileExt === ".mp4" ? detectionMode : "deepfake", detectionProvider);
      setState("complete");
      onAnalysisComplete(result);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Analysis failed";
      onError(message);
      setState("error");
    }
  }, [onError, onAnalysisComplete, detectionMode, detectionProvider]);

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0];
      setSelectedFile(file);
    }
  }, []);

  const handleChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    e.preventDefault();
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      setSelectedFile(file);
      e.target.value = "";
    }
  }, []);

  if (state === "uploading" || state === "analyzing") {
    return (
      <div className="rounded-2xl border border-white/15 bg-white/5 p-8 sm:p-10">
        <div className="flex flex-col items-center gap-6 text-center">
          <div className="h-12 w-12 animate-spin rounded-full border-4 border-emerald-300/30 border-t-emerald-200" />
          <div>
            <h2 className="text-xl font-semibold">Processing media</h2>
            <p className="mt-2 text-sm text-slate-300">{stage}</p>
          </div>
          <div className="mt-4 space-y-2 text-left text-sm text-slate-400">
            <p className="flex items-center gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-300" />
              Preparing media
            </p>
            <p className="flex items-center gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-300" />
              Visual analysis
            </p>
            <p className="flex items-center gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-300" />
              Audio analysis
            </p>
            <p className="flex items-center gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-300" />
              Metadata inspection
            </p>
            <p className="flex items-center gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-300" />
              Evidence fusion
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-white/15 bg-white/5 p-8 sm:p-10">
      <div className="mb-6">
        <h2 className="text-xl font-semibold">Analyze media</h2>
        <p className="mt-2 text-sm text-slate-300">
          Upload an image, audio, or video file to check for authenticity indicators
        </p>
      </div>

      <fieldset className="mb-6">
        <legend className="mb-2 text-sm font-medium text-slate-200">Detection provider</legend>
        <div className="flex flex-wrap gap-4">
          <label className="flex cursor-pointer items-center gap-2 rounded-lg border border-white/20 p-4">
            <input type="radio" name="provider" value="bitmind" checked={detectionProvider === "bitmind"} onChange={() => setDetectionProvider("bitmind")} />
            BitMind API (primary)
          </label>
          <label className="flex cursor-pointer items-center gap-2 rounded-lg border border-white/20 p-4">
            <input type="radio" name="provider" value="reality_defender" checked={detectionProvider === "reality_defender"} onChange={() => setDetectionProvider("reality_defender")} />
            Reality Defender API + local checks
          </label>
          <label className="flex cursor-pointer items-center gap-2 rounded-lg border border-white/20 p-4">
            <input type="radio" name="provider" value="offline" checked={detectionProvider === "offline"} onChange={() => setDetectionProvider("offline")} />
            Offline models
          </label>
        </div>
        <p className="mt-3 text-sm text-slate-300">
          {detectionProvider === "reality_defender" ? "Sends this image, video, or audio to Reality Defender for deepfake and manipulation analysis. Results include the vendor verdict and available model scores. Video access depends on your plan. Independent local checks also run." : detectionProvider === "bitmind"
            ? "Images and videos are sent to BitMind for AI-generation detection. If the API fails or the file exceeds 10 MB, local models are used automatically. Audio detection stays local."
            : "Detection runs on this machine using installed models. Media is not sent to detection APIs."}
        </p>
      </fieldset>

      {isVideo && <div className="mb-6">
        <p className="mb-2 text-sm font-medium text-slate-200">{detectionProvider === "reality_defender" ? "Independent local video check" : detectionProvider === "bitmind" ? "Offline fallback for this video" : "Video detection mode"}</p>
        <div className="flex gap-4">
          <button
            type="button"
            aria-pressed={detectionMode === "deepfake"}
            onClick={() => setDetectionMode("deepfake")}
            className={`flex-1 rounded-lg px-4 py-3 text-sm font-medium transition ${
              detectionMode === "deepfake"
                ? "bg-emerald-500/20 text-emerald-200 border border-emerald-500/30"
                : "bg-white/5 text-slate-300 border border-white/10 hover:bg-white/10"
            }`}
          >
            Deepfake Detection
            <span className="mt-1 block text-xs opacity-70">CLIP ViT-L/14 - Facial manipulation</span>
          </button>
          <button
            type="button"
            aria-pressed={detectionMode === "ai_generated"}
            onClick={() => setDetectionMode("ai_generated")}
            className={`flex-1 rounded-lg px-4 py-3 text-sm font-medium transition ${
              detectionMode === "ai_generated"
                ? "bg-emerald-500/20 text-emerald-200 border border-emerald-500/30"
                : "bg-white/5 text-slate-300 border border-white/10 hover:bg-white/10"
            }`}
          >
            AI-Generated Detection
            <span className="mt-1 block text-xs opacity-70">UniFD - AI-generated video frames</span>
          </button>
        </div>
        <p className="mt-2 text-xs text-slate-400">Both options check sampled frames, not motion. Audio is analyzed separately. Results are experimental, not proof.</p>
      </div>}

      {selectedFile && <div className="mb-6">
        <p className="text-sm text-slate-300">Selected: {selectedFile.name}</p>
        {isAudio && detectionProvider === "bitmind" && <p className="mt-2 text-xs text-slate-400">BitMind does not support audio. This file will be analyzed locally.</p>}
        <button type="button" onClick={() => processFile(selectedFile)} className="mt-4 rounded-lg bg-emerald-400 px-5 py-3 text-sm font-semibold text-slate-950">
          {detectionProvider === "reality_defender" ? "Send to Reality Defender and analyze" : detectionProvider === "bitmind" && !isAudio && selectedFile.size <= 10_000_000 ? "Send to BitMind and analyze" : "Analyze locally"}
        </button>
      </div>}

      <div
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
        className={`relative flex min-h-[200px] flex-col items-center justify-center rounded-xl border-2 border-dashed transition ${
          dragActive
            ? "border-emerald-300 bg-emerald-300/5"
            : "border-white/20 hover:border-white/30 hover:bg-white/5"
        }`}
      >
        <input
          type="file"
          id="file-upload"
          className="absolute inset-0 cursor-pointer opacity-0"
          onChange={handleChange}
          accept=".jpg,.jpeg,.png,.mp4,.wav,.mp3"
          disabled={state === "complete"}
        />
        <label htmlFor="file-upload" className="flex cursor-pointer flex-col items-center gap-4 p-6">
          <div className="rounded-full bg-white/10 p-4">
            <svg className="h-8 w-8 text-slate-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
          </div>
          <div className="text-center">
            <p className="text-sm font-medium text-slate-200">
              {dragActive ? "Drop file here" : "Drag and drop or click to upload"}
            </p>
            <p className="mt-1 text-xs text-slate-400">JPG, JPEG, PNG, MP4, WAV, MP3</p>
          </div>
        </label>
      </div>

      <div className="mt-6 rounded-lg bg-white/5 p-4 text-xs text-slate-400">
        <p className="flex items-start gap-2">
          <svg className="mt-0.5 h-4 w-4 shrink-0 text-emerald-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
          </svg>
          <span>{detectionProvider === "offline" ? "Offline mode keeps detection on this machine." : detectionProvider === "reality_defender" ? "Reality Defender mode uploads the original file to its storage for analysis under its data handling policies and scan quota. The API key stays on the backend. Failed requests do not undo an upload." : "API mode sends media to BitMind under its data handling policies. Your API key stays on the backend. Fallback does not undo an upload already sent."}</span>
        </p>
      </div>
    </div>
  );
}

