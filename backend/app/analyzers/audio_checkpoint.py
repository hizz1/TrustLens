"""Pinned identity for the audio deepfake-detection checkpoint."""

MODEL_ID = "Vansh180/deepfake-audio-wav2vec2"
REVISION = "e1197e2063deb056b0a6a348f3913d27de7f3d83"
# SHA-256 of model.safetensors — verified after download on 2026-10-09
WEIGHTS_SHA256: str | None = "e6bc501e391e78a52f5ce76f34c726c6b30fe225c0d24a37a55daf284b5b70ec"
SAMPLE_RATE = 16_000
# Maximum audio fed per window to the model (seconds).  Wav2Vec2 has no hard
# limit but very long clips cause OOM; 30 s strikes a good balance.
WINDOW_SECONDS = 30.0
# Label index → class interpretation confirmed from config.json id2label
LABEL_REAL = "real"   # index 0
LABEL_FAKE = "fake"   # index 1
FAKE_INDEX = 1
