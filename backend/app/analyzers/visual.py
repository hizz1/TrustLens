import hashlib
import logging
import threading
from pathlib import Path

from PIL import Image, ImageOps

from app.analyzers.checkpoint import MODEL_ID, REVISION, WEIGHTS_SHA256
from app.config import Settings
from app.schemas import AnalysisResponse, FrameScore, VisualResult

logger = logging.getLogger(__name__)
LIMITATIONS = [
    "The CLIP ViT-L/14 model was trained on facial deepfake detection (FaceForensics++ dataset); non-facial images may be outside its training distribution.",
    "The model focuses on detecting partially manipulated facial deepfakes; fully synthetic non-facial content may not be detected reliably.",
    "Results are experimental decision support, not forensic proof or probabilities of real-world authenticity.",
    "Video analysis samples 12 frames independently; it does not assess motion, lip synchronization, or every frame.",
    "The model uses CLIP's standard preprocessing; custom preprocessing pipelines may yield different results.",
]


def unavailable(reason: str) -> VisualResult:
    return VisualResult(status="unavailable", findings=[reason], model_id=MODEL_ID,
                        model_revision=REVISION, limitations=LIMITATIONS)


class VisualAnalyzer:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._lock = threading.Lock()
        self._model = None
        self._processor = None
        self._torch = None
        self._device = None
        self._dtype = None

    def _load(self):
        if self._model is not None:
            return
        directory = self.settings.visual_model_dir
        model_path = directory / "model.torchscript"
        if not model_path.is_file():
            raise RuntimeError("Checkpoint file is missing; run python scripts/download_visual_model.py from backend.")
        import torch
        from transformers import CLIPProcessor

        self._torch = torch
        wants_cuda = self.settings.visual_device != "cpu" and torch.cuda.is_available()
        self._device = "cuda" if wants_cuda else "cpu"
        # The published TorchScript graph hard-codes bfloat16 input conversion.
        # Keep weights in that dtype on CPU too, otherwise convolution fails.
        self._dtype = torch.bfloat16

        # Load TorchScript model
        model = torch.jit.load(model_path, map_location="cpu")
        model.eval()

        # Load CLIP processor for preprocessing
        processor = CLIPProcessor.from_pretrained("openai/clip-vit-large-patch14", local_files_only=True)

        try:
            model = model.to(self._device).to(self._dtype)
        except RuntimeError:
            if self._device != "cuda":
                raise
            model = model.to("cpu").to(torch.bfloat16)
            torch.cuda.empty_cache()
            self._device = "cpu"
            self._dtype = torch.bfloat16

        self._model = model
        self._processor = processor

    def _predict(self, paths: list[Path]) -> list[float]:
        torch = self._torch
        probabilities = []
        with torch.inference_mode():
            for offset in range(0, len(paths), self.settings.visual_batch_size):
                images = []
                try:
                    for path in paths[offset:offset + self.settings.visual_batch_size]:
                        with Image.open(path) as image:
                            images.append(ImageOps.exif_transpose(image).convert("RGB"))
                    # Preprocess using CLIP processor
                    batch_images = torch.stack(
                        [self._processor(images=image, return_tensors="pt")["pixel_values"][0] for image in images]
                    )
                    batch_images = batch_images.to(self._device).to(self._dtype)

                    # Forward pass
                    with torch.autocast(device_type=self._device, dtype=self._dtype) if self._device == "cuda" else torch.no_grad():
                        output = self._model(batch_images)
                        softmax_output = output.softmax(dim=1).cpu()

                    if softmax_output.shape != (len(images), 2) or not torch.isfinite(softmax_output).all().item():
                        raise RuntimeError("Model returned invalid logits.")
                    # Extract fake probability (index 1)
                    probabilities.extend(softmax_output[:, 1].tolist())
                finally:
                    for image in images:
                        image.close()
        return probabilities

    def analyze(self, analysis: AnalysisResponse) -> VisualResult:
        if analysis.media_type == "audio":
            return VisualResult(status="not_applicable")
        if not self.settings.visual_enabled:
            return unavailable("Visual analysis is disabled by configuration.")
        try:
            # One lazy model instance per API process; concurrent requests cannot overfill VRAM.
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
                    self._model = self._model.to("cpu").to(self._torch.bfloat16)
                    self._torch.cuda.empty_cache()
                    self._device = "cpu"
                    self._dtype = self._torch.bfloat16
                    values = self._predict(paths)
                    findings.append("CUDA inference failed; inference was retried successfully on CPU.")
                if self._device == "cpu" and self.settings.visual_device != "cpu":
                    findings.append("CUDA was unavailable or could not be used; CPU inference was used.")
                score = sum(values) / len(values)
                frame_scores = [FrameScore(**frame.model_dump(), synthetic_probability=value,
                                           confidence=max(value, 1 - value))
                                for frame, value in zip(analysis.preprocessing.frames, values)]
                if frame_scores:
                    findings.append(f"Visual model assigned a Fake score of at least 0.5 to {sum(value >= 0.5 for value in values)} of {len(values)} sampled frames.")
                    findings.append("Aggregate visual score is the arithmetic mean of all sampled-frame Fake softmax scores.")
                    findings.append("Suspicious frames lists the five highest model scores, even when all are low; ranking alone does not establish manipulation.")
                else:
                    findings.append("Visual model evaluated one image; synthetic_probability is the Fake-class softmax score.")
                return VisualResult(status="completed", synthetic_probability=score, confidence=max(score, 1 - score),
                                    findings=findings, frame_scores=frame_scores,
                                    suspicious_frames=sorted(frame_scores, key=lambda item: (-item.synthetic_probability, item.index))[:5],
                                    device=self._device, model_id=MODEL_ID, model_revision=REVISION, limitations=LIMITATIONS)
        except Exception as exc:
            logger.warning("Visual analysis unavailable: %s", exc)
            return unavailable(f"Visual analysis unavailable ({type(exc).__name__}): {str(exc)[:500]}")
