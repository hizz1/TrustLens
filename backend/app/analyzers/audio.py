"""Phase 4 — Audio Deepfake Inference.

Uses Vansh180/deepfake-audio-wav2vec2 (Wav2Vec2ForSequenceClassification,
MIT license, trained on ASVspoof 2021 PA).  Input: mono 16 kHz WAV produced
by Phase 2 preprocessing.  Long files are split into overlapping windows;
window scores are averaged.

Label contract (from config.json id2label):
    index 0 → "real"
    index 1 → "fake"   ← synthetic_probability = softmax[:,1]
"""
import logging
import threading
from pathlib import Path

from app.analyzers.audio_checkpoint import (
    FAKE_INDEX,
    MODEL_ID,
    REVISION,
    SAMPLE_RATE,
    WEIGHTS_SHA256,
    WINDOW_SECONDS,
)
from app.config import Settings
from app.schemas import AnalysisResponse, AnalyzerResult

logger = logging.getLogger(__name__)

LIMITATIONS = [
    "The checkpoint was trained on ASVspoof 2021 PA (physical-access replay attacks);"
    " performance on text-to-speech or VC deepfakes may differ.",
    "Long audio is split into 30-second windows; scores are averaged across windows.",
    "Softmax scores are uncalibrated model outputs, not forensic proof.",
    "Audio analysis does not assess visual content or lip synchronisation.",
]


def unavailable(reason: str) -> AnalyzerResult:
    return AnalyzerResult(status="unavailable", findings=[reason])


class AudioAnalyzer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._lock = threading.Lock()
        self._model = None
        self._extractor = None
        self._torch = None
        self._device: str | None = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Lazy-load model on first use (inside lock)."""
        if self._model is not None:
            return
        directory = self.settings.audio_model_dir
        required = [directory / name for name in ("config.json", "preprocessor_config.json", "model.safetensors")]
        if not all(path.is_file() for path in required):
            raise RuntimeError(
                "Audio checkpoint files are missing; run "
                "python scripts/download_audio_model.py from backend/."
            )
        import json
        config = json.loads(required[0].read_text(encoding="utf-8"))
        if config.get("id2label") != {"0": "real", "1": "fake"} or config.get("model_type") != "wav2vec2":
            raise RuntimeError(
                "Audio checkpoint configuration does not match the verified labels/architecture."
            )
        preprocessor = json.loads(required[1].read_text(encoding="utf-8"))
        if preprocessor.get("sampling_rate") != SAMPLE_RATE:
            raise RuntimeError(
                f"Audio checkpoint expects {preprocessor.get('sampling_rate')} Hz; "
                f"TrustLens preprocessing targets {SAMPLE_RATE} Hz."
            )
        if WEIGHTS_SHA256 is not None:
            import hashlib
            with required[2].open("rb") as fh:
                actual = hashlib.file_digest(fh, "sha256").hexdigest()
            if actual != WEIGHTS_SHA256:
                raise RuntimeError("Audio checkpoint integrity check failed; re-download pinned weights.")

        import torch
        from transformers import AutoFeatureExtractor, AutoModelForAudioClassification

        self._torch = torch
        wants_cuda = self.settings.audio_device != "cpu" and torch.cuda.is_available()
        self._device = "cuda" if wants_cuda else "cpu"
        extractor = AutoFeatureExtractor.from_pretrained(str(directory), local_files_only=True)
        model = AutoModelForAudioClassification.from_pretrained(
            str(directory), local_files_only=True, use_safetensors=True
        )
        model.eval()
        try:
            model.to(self._device)
        except RuntimeError:
            if self._device != "cuda":
                raise
            model.to("cpu")
            torch.cuda.empty_cache()
            self._device = "cpu"
        self._model = model
        self._extractor = extractor

    def _windows(self, waveform) -> list:
        """Split a 1-D float32 tensor into WINDOW_SECONDS chunks (no overlap)."""
        torch = self._torch
        window_samples = int(WINDOW_SECONDS * SAMPLE_RATE)
        if waveform.shape[0] <= window_samples:
            return [waveform]
        parts = []
        for start in range(0, waveform.shape[0], window_samples):
            chunk = waveform[start: start + window_samples]
            if chunk.shape[0] < 400:
                # Skip sub-25 ms trailing fragments (model minimum receptive field)
                break
            parts.append(chunk)
        return parts or [waveform]

    def _infer_waveform(self, waveform) -> float:
        """Return mean fake-class softmax across all windows (0–1)."""
        torch = self._torch
        chunks = self._windows(waveform)
        fake_scores: list[float] = []
        with torch.inference_mode():
            for chunk in chunks:
                # extractor returns dict with input_values tensor
                inputs = self._extractor(
                    chunk.numpy(),
                    sampling_rate=SAMPLE_RATE,
                    return_tensors="pt",
                    padding=True,
                )
                inputs = {k: v.to(self._device) for k, v in inputs.items()}
                logits = self._model(**inputs).logits
                if logits.shape[-1] != 2 or not torch.isfinite(logits).all().item():
                    raise RuntimeError("Audio model returned invalid logits.")
                prob_fake = torch.softmax(logits.float(), dim=-1)[0, FAKE_INDEX].item()
                fake_scores.append(prob_fake)
        return sum(fake_scores) / len(fake_scores)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self, analysis: AnalysisResponse) -> AnalyzerResult:
        """Entry point called by routes.py for every request."""
        # Visual-only: no audio track
        if analysis.preprocessing.audio_status == "not_applicable":
            return AnalyzerResult(status="not_applicable")
        if analysis.preprocessing.audio_status != "completed" or not analysis.preprocessing.audio_path:
            return unavailable("Audio preparation did not complete successfully.")
        if not self.settings.audio_enabled:
            return unavailable("Audio analysis is disabled by configuration.")
        try:
            audio_path = (self.settings.data_dir / analysis.preprocessing.audio_path).resolve()
            if not audio_path.is_relative_to(self.settings.data_dir.resolve()):
                raise RuntimeError("Audio path escaped the configured data directory.")
            if not audio_path.is_file():
                raise RuntimeError(f"Prepared audio file not found: {audio_path}")

            with self._lock:
                self._load()
                findings: list[str] = []
                try:
                    waveform, sr = self._load_waveform(audio_path)
                    score = self._infer_waveform(waveform)
                except RuntimeError:
                    if self._device != "cuda":
                        raise
                    self._model.to("cpu")
                    self._torch.cuda.empty_cache()
                    self._device = "cpu"
                    waveform, sr = self._load_waveform(audio_path)
                    score = self._infer_waveform(waveform)
                    findings.append("CUDA inference failed; audio inference retried successfully on CPU.")
                if self._device == "cpu" and self.settings.audio_device != "cpu":
                    findings.append("CUDA was unavailable or could not be used; CPU audio inference was used.")
                duration_s = waveform.shape[0] / SAMPLE_RATE
                n_windows = max(1, int(duration_s / WINDOW_SECONDS + 0.5))
                findings.append(
                    f"Audio model analysed {duration_s:.1f} s of audio across "
                    f"{'1 window' if n_windows == 1 else f'{n_windows} windows'}; "
                    "synthetic_probability is the mean Fake softmax score."
                )
                return AnalyzerResult(
                    status="completed",
                    synthetic_probability=score,
                    confidence=max(score, 1.0 - score),
                    findings=findings,
                )
        except Exception as exc:
            logger.warning("Audio analysis unavailable: %s", exc)
            return unavailable(f"Audio analysis unavailable ({type(exc).__name__}): {str(exc)[:500]}")

    @staticmethod
    def _load_waveform(path: Path):
        """Load WAV as float32 mono 1-D tensor using torchaudio (preferred) or soundfile."""
        try:
            import torchaudio  # type: ignore[import]
            waveform, sr = torchaudio.load(str(path))
            # torchaudio returns (channels, samples); take mean across channels
            if waveform.shape[0] > 1:
                waveform = waveform.mean(dim=0)
            else:
                waveform = waveform.squeeze(0)
            return waveform, sr
        except ImportError:
            pass
        # Fallback: soundfile → numpy → torch
        import soundfile as sf  # type: ignore[import]
        import torch
        data, sr = sf.read(str(path), dtype="float32", always_2d=True)
        return torch.from_numpy(data.mean(axis=1)), sr
