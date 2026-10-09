"""UniversalFakeDetect applied independently to prepared video frames."""
import logging
import hashlib
import math
import threading
from pathlib import Path

from PIL import Image

from app.analyzers.checkpoint_unifd import MODEL_ID, REVISION, HEAD_SHA256
from app.config import Settings
from app.schemas import AnalysisResponse, FrameScore, VisualResult

logger = logging.getLogger(__name__)
CONFIDENCE = "max(mean fake sigmoid, 1 - mean fake sigmoid); uncalibrated model certainty, not accuracy"
LIMITATIONS = [
    "UniFD is an AI-generated image detector applied to 12 sampled video frames; it does not assess motion, temporal consistency, or every frame.",
    "UniFD uses the central 224x224 crop of each frame; generated regions outside that crop can be missed.",
    "Performance on modern video generators, compression, and unseen content is not established by this integration.",
    "Scores are uncalibrated model outputs, not probabilities of real-world authenticity or forensic proof.",
]


def unavailable(reason: str) -> VisualResult:
    return VisualResult(status="unavailable", findings=[reason], model_id=MODEL_ID,
                        model_revision=REVISION, confidence_definition=CONFIDENCE, limitations=LIMITATIONS)


class UniFDAnalyzer:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._lock = threading.Lock()
        self._model = self._head = self._processor = self._torch = None
        self._device = "cpu"

    def _load(self):
        if self._model is not None:
            return
        directory = self.settings.unifd_model_dir
        if not (directory / "fc_weights.pth").is_file():
            raise RuntimeError("UniFD checkpoint missing; run python scripts/download_unifd_model.py from backend.")
        if hashlib.sha256((directory / "fc_weights.pth").read_bytes()).hexdigest() != HEAD_SHA256:
            raise RuntimeError("UniFD checkpoint checksum does not match the pinned official head.")
        import torch
        from transformers import CLIPImageProcessor, CLIPVisionModelWithProjection

        self._torch = torch
        # UniFD uses projected, UNNORMALIZED CLIP features and a single binary head.
        model = CLIPVisionModelWithProjection.from_pretrained(directory / "clip", local_files_only=True).float().eval()
        head = torch.nn.Linear(768, 1)
        head.load_state_dict(torch.load(directory / "fc_weights.pth", map_location="cpu", weights_only=True), strict=True)
        head.eval()
        # Match upstream validate.py: CenterCrop(224), tensor, CLIP normalization. No resize.
        processor = CLIPImageProcessor.from_pretrained(directory / "clip", local_files_only=True, do_resize=False)
        self._device = "cuda" if self.settings.unifd_device != "cpu" and torch.cuda.is_available() else "cpu"
        try:
            model.to(self._device)
            head.to(self._device)
        except RuntimeError:
            if self._device != "cuda":
                raise
            model.to("cpu")
            head.to("cpu")
            self._device = "cpu"
            torch.cuda.empty_cache()
        self._model, self._head, self._processor = model, head, processor

    def _predict(self, paths: list[Path]) -> list[float]:
        torch = self._torch
        values = []
        with torch.inference_mode():
            for offset in range(0, len(paths), self.settings.unifd_batch_size):
                images = []
                try:
                    for path in paths[offset:offset + self.settings.unifd_batch_size]:
                        with Image.open(path) as image:
                            images.append(image.convert("RGB"))
                    pixels = self._processor(images=images, return_tensors="pt")["pixel_values"].to(self._device)
                    features = self._model(pixel_values=pixels).image_embeds
                    logits = self._head(features)
                    if logits.shape != (len(images), 1) or not torch.isfinite(logits).all().item():
                        raise ValueError("UniFD returned invalid logits.")
                    values.extend(logits.sigmoid().flatten().cpu().tolist())
                finally:
                    for image in images:
                        image.close()
        return values

    def analyze(self, analysis: AnalysisResponse) -> VisualResult:
        if analysis.media_type != "video":
            return VisualResult(status="not_applicable", model_id=MODEL_ID)
        if not self.settings.unifd_enabled:
            return unavailable("UniFD is disabled by configuration.")
        try:
            with self._lock:
                frames = analysis.preprocessing.frames
                paths = [(self.settings.data_dir / frame.path).resolve() for frame in frames]
                if not paths or any(not p.is_relative_to(self.settings.data_dir.resolve()) for p in paths):
                    raise ValueError("Missing or invalid prepared video frames.")
                self._load()
                findings = []
                try:
                    values = self._predict(paths)
                except RuntimeError:
                    if self._device != "cuda":
                        raise
                    self._model.to("cpu")
                    self._head.to("cpu")
                    self._device = "cpu"
                    self._torch.cuda.empty_cache()
                    values = self._predict(paths)
                    findings.append("CUDA inference failed; UniFD retried successfully on CPU.")
                if len(values) != len(frames) or any(not math.isfinite(v) or not 0 <= v <= 1 for v in values):
                    raise ValueError("UniFD returned invalid frame scores.")
                score = sum(values) / len(values)
                scores = [FrameScore(**frame.model_dump(), synthetic_probability=v, confidence=max(v, 1-v))
                          for frame, v in zip(frames, values)]
                findings.extend([
                    f"UniFD assigned an AI-generation score of at least 0.5 to {sum(v >= 0.5 for v in values)} of {len(values)} sampled frames.",
                    "Visual score is the arithmetic mean of sampled-frame fake sigmoid scores; audio is analyzed separately.",
                    "Suspicious frames lists the five highest scores even when all are low; ranking does not establish generation.",
                ])
                if self._device == "cpu" and self.settings.unifd_device != "cpu":
                    findings.append("CUDA was unavailable or could not be used; UniFD ran on CPU.")
                return VisualResult(status="completed", synthetic_probability=score, confidence=max(score, 1-score),
                                    findings=findings, frame_scores=scores,
                                    suspicious_frames=sorted(scores, key=lambda f: (-f.synthetic_probability, f.index))[:5],
                                    model_id=MODEL_ID, model_revision=REVISION, device=self._device,
                                    confidence_definition=CONFIDENCE, limitations=LIMITATIONS)
        except Exception as exc:
            logger.warning("UniFD unavailable: %s", exc)
            return unavailable(f"UniFD unavailable ({type(exc).__name__}): {str(exc)[:500]}")
