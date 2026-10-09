import logging
import threading
from pathlib import Path

from PIL import Image, ImageOps

from app.analyzers.checkpoint_aide import MODEL_ID, REVISION, WEIGHTS_SHA256
from app.config import Settings
from app.schemas import AnalysisResponse, FrameScore, VisualResult

logger = logging.getLogger(__name__)
LIMITATIONS = [
    "The AIDE model is trained for AI-generated image detection; it may not detect traditional deepfakes or partial manipulations.",
    "The model combines frequency-forensic evidence and high-level semantic cues; results are experimental decision support.",
    "Video analysis samples 12 frames independently; it does not assess motion, lip synchronization, or every frame.",
    "Softmax scores and confidence are uncalibrated model outputs, not forensic proof or probabilities of real-world authenticity.",
]


def unavailable(reason: str) -> VisualResult:
    return VisualResult(status="unavailable", findings=[reason], model_id=MODEL_ID,
                        model_revision=REVISION, limitations=LIMITATIONS)


class AIDEAnalyzer:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._lock = threading.Lock()
        self._model = None
        self._processor = None
        self._torch = None
        self._device = None

    def _load(self):
        if self._model is not None:
            return
        directory = self.settings.aide_model_dir
        model_path = directory / "model.safetensors"
        config_path = directory / "config.json"
        if not model_path.is_file() or not config_path.is_file():
            raise RuntimeError("AIDE checkpoint files are missing; run python scripts/download_aide_model.py from backend.")
        
        import torch
        from transformers import AutoConfig

        self._torch = torch
        wants_cuda = self.settings.aide_device != "cpu" and torch.cuda.is_available()
        self._device = "cuda" if wants_cuda else "cpu"

        # Load config
        config = AutoConfig.from_pretrained(directory, local_files_only=True)
        
        # For now, use a simple approach: load as a standard image classifier
        # This is a simplified integration - full AIDE architecture requires custom modules
        try:
            from transformers import AutoModelForImageClassification
            model = AutoModelForImageClassification.from_pretrained(directory, local_files_only=True)
            from transformers import AutoImageProcessor
            processor = AutoImageProcessor.from_pretrained(directory, local_files_only=True)
        except Exception as exc:
            raise RuntimeError('AIDE architecture is unavailable; no fallback scores are produced.') from exc

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
        self._processor = processor

    def _predict(self, paths: list[Path]) -> list[float]:
        torch = self._torch
        probabilities = []
        with torch.inference_mode():
            for offset in range(0, len(paths), self.settings.aide_batch_size):
                images = []
                try:
                    for path in paths[offset:offset + self.settings.aide_batch_size]:
                        with Image.open(path) as image:
                            images.append(ImageOps.exif_transpose(image).convert("RGB"))
                    inputs = self._processor(images=images, return_tensors="pt")
                    inputs = {key: value.to(self._device) for key, value in inputs.items()}
                    outputs = self._model(**inputs)
                    if hasattr(outputs, 'logits'):
                        logits = outputs.logits
                    else:
                        logits = outputs
                    if logits.shape != (len(images), 2) or not torch.isfinite(logits).all().item():
                        raise RuntimeError("Model returned invalid logits.")
                    probabilities.extend(torch.softmax(logits.float(), dim=-1)[:, 1].cpu().tolist())
                finally:
                    for image in images:
                        image.close()
        return probabilities

    def analyze(self, analysis: AnalysisResponse) -> VisualResult:
        if analysis.media_type == "audio":
            return VisualResult(status="not_applicable")
        if not self.settings.aide_enabled:
            return unavailable("AIDE analysis is disabled by configuration.")
        try:
            with self._lock:
                self._load()
                relative_paths = ([frame.path for frame in analysis.preprocessing.frames]
                                  if analysis.media_type == "video" else [analysis.preprocessing.source_path])
                if not relative_paths:
                    raise RuntimeError("No prepared visual inputs are available.")
                paths = [(self.settings.data_dir / path).resolve() for path in relative_paths]
                if any(not path.is_relative_to(self.settings.data_dir.resolve()) for path in paths):
                    raise RuntimeError("Visual input escaped the configured data directory.")
                findings = []
                try:
                    values = self._predict(paths)
                except RuntimeError:
                    if self._device != "cuda":
                        raise
                    self._model.to("cpu")
                    self._torch.cuda.empty_cache()
                    self._device = "cpu"
                    values = self._predict(paths)
                    findings.append("CUDA inference failed; inference was retried successfully on CPU.")
                if self._device == "cpu" and self.settings.aide_device != "cpu":
                    findings.append("CUDA was unavailable or could not be used; CPU inference was used.")
                score = sum(values) / len(values)
                frame_scores = [FrameScore(**frame.model_dump(), synthetic_probability=value,
                                           confidence=max(value, 1 - value))
                                for frame, value in zip(analysis.preprocessing.frames, values)]
                if frame_scores:
                    findings.append(f"AIDE model assigned a Fake score of at least 0.5 to {sum(value >= 0.5 for value in values)} of {len(values)} sampled frames.")
                    findings.append("Aggregate AIDE score is the arithmetic mean of all sampled-frame Fake softmax scores.")
                    findings.append("Suspicious frames lists the five highest model scores, even when all are low; ranking alone does not establish manipulation.")
                else:
                    findings.append("AIDE model evaluated one image; synthetic_probability is the Fake-class softmax score.")
                return VisualResult(status="completed", synthetic_probability=score, confidence=max(score, 1 - score),
                                    findings=findings, frame_scores=frame_scores,
                                    suspicious_frames=sorted(frame_scores, key=lambda item: (-item.synthetic_probability, item.index))[:5],
                                    device=self._device, model_id=MODEL_ID, model_revision=REVISION, limitations=LIMITATIONS)
        except Exception as exc:
            logger.warning("AIDE analysis unavailable: %s", exc)
            return unavailable(f"AIDE analysis unavailable ({type(exc).__name__}): {str(exc)[:500]}")

