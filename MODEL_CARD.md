# TrustLens visual checkpoint

## Identity and provenance

- Repository: [dima806/deepfake_vs_real_image_detection](https://huggingface.co/dima806/deepfake_vs_real_image_detection)
- Immutable revision: `29e4cf9efc543845610045f6ba7e88e5cf9d9301`
- Weights: root `model.safetensors`, 343,223,968 bytes (about 327 MiB).
- SHA-256: `b38e7d3de2be44b224cb4cffe881a0c4b75f7283c5d4a2017fbadd58bd41fdef`
- Architecture: `ViTForImageClassification`, ViT-base, 12 layers, hidden size 768, 16-pixel patches. Base model: `google/vit-base-patch16-224-in21k`.
- Publisher-declared license: **Apache-2.0**, recorded in the [pinned model card](https://huggingface.co/dima806/deepfake_vs_real_image_detection/blob/29e4cf9efc543845610045f6ba7e88e5cf9d9301/README.md). This is the checkpoint's declared license, not an assertion about ownership of every training image. The downloaded model card is retained alongside the weights.

## Verified inference contract

Verified against the pinned [configuration](https://huggingface.co/dima806/deepfake_vs_real_image_detection/blob/29e4cf9efc543845610045f6ba7e88e5cf9d9301/config.json) and [processor configuration](https://huggingface.co/dima806/deepfake_vs_real_image_detection/blob/29e4cf9efc543845610045f6ba7e88e5cf9d9301/preprocessor_config.json):

1. Decode with Pillow, apply EXIF orientation, and convert to **RGB**, never BGR.
2. Use the checkpoint's `ViTImageProcessor`: resize to **224 × 224** using bilinear resampling (Pillow enum 2); rescale by **1/255**; normalize each channel with mean **0.5** and standard deviation **0.5**.
3. Load only local Safetensors weights with the built-in Transformers ViT class. No remote model code or pickle weights are executed. Verify weight SHA-256 and the processor/label contract before loading.
4. Call `eval()` and run under `torch.inference_mode()`, with batch size at most **4**. Select CUDA when available, otherwise CPU. CUDA transfer/inference failure retries on CPU; total analyzer failure returns unavailable with no scores.
5. Apply softmax to the two logits: class **0 = Real**, class **1 = Fake**. `synthetic_probability` is the Fake softmax output, not a calibrated likelihood of manipulation.

An image is evaluated once. Video inference evaluates all 12 prepared frames independently. Aggregate probability is the arithmetic mean of their Fake scores. `confidence` is `max(mean Fake, 1 - mean Fake)`; frame confidence uses the same definition for that individual frame. It measures uncalibrated model certainty, not reliability or validated accuracy.

The five highest-scoring video frames are returned in `suspicious_frames`, with stable index ordering for ties. They are ranked even if all scores are low. Ranking does not establish that a frame is fake. File paths and intended sampling times are preserved in every `frame_scores` entry.

## Practical limits

- The model card links a real/fake faces evaluation. TrustLens does not perform face detection/cropping; non-face scenes and small faces may be outside the learned distribution. It is an experimental image-forensics signal, not a universal face-swap detector.
- The publisher explicitly warns about training-data age and concept drift from newer generators. We do not reproduce the publisher's benchmark as a claim about this application, retrain the model, or silently lower its threshold.
- Resizing loses detail. Compression, screenshots, illustration, lighting, and distribution changes can cause false positives or missed edits.
- Twelve independent samples do not analyze every frame, motion consistency, or lip sync. This phase does not assess audio, provenance, or compute a Digital Trust Score.
- Functional smoke tests verify loading, execution, score structure, and GPU selection. They are **not an accuracy evaluation**. Held-out, representative labeled data would be needed for an accuracy claim.

## Reproduction

See README.md for the Windows CUDA 12.8 installation and one-time download commands. Requests never send uploaded media to Hugging Face and never download weights. Only the explicit setup helper accesses the public model repository. One model is loaded lazily per backend process, and a lock serializes inference to limit VRAM usage. Run one Uvicorn worker on this laptop.

## Additional video model: UniversalFakeDetect (UniFD)

The video-only `ai_generated` mode uses the official WisconsinAIVision/UniversalFakeDetect
CVPR 2023 linear head with OpenAI CLIP ViT-L/14 projected features (768 dimensions,
unnormalized). Sources and pinned revisions are in
`backend/app/analyzers/checkpoint_unifd.py`; the head is SHA-256 checked and loaded
with `weights_only=True`. The CLIP vision backbone is stored locally in safetensors.

Evaluation follows upstream center-crop (224px, no resize), CLIP normalization,
and binary sigmoid. TrustLens averages the 12 frame scores; this extension has not
been validated as a temporal video detector or benchmarked on current video generators.
Confidence is max(mean sigmoid, 1 - mean sigmoid), not calibrated accuracy.
The existing audio analysis and trust-score fusion remain independent of mode.
Missing or invalid checkpoints return unavailable, never substitute model scores.

## BitMind API provider

The optional primary dashboard provider is BitMind's standard unified detection API.
It receives user-selected image/video bytes only after API mode submission; offline
mode does not invoke it. It reports a vendor AI-generation verdict and confidence,
not a locally validated synthetic probability. No API score calibration or detection
accuracy benchmark is claimed. `visual.synthetic_probability` stays null on successful
API results; the vendor verdict is separate from audio/provenance trust-score fusion.
No per-frame scores are generated from a whole-file verdict. Failures and unsupported
inputs fall back to local models with an explicit reason in the result.
