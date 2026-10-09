"""Download and verify the Phase 4 audio deepfake-detection checkpoint.

Run from backend/:
    .venv\\Scripts\\python.exe scripts/download_audio_model.py

Downloads Vansh180/deepfake-audio-wav2vec2 (MIT license) to models/audio/.
Prints the model.safetensors SHA-256 so you can pin it in audio_checkpoint.py.
"""
import hashlib
import shutil
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.analyzers.audio_checkpoint import MODEL_ID, REVISION
from app.config import Settings

TARGET = Settings().audio_model_dir
REQUIRED = ["config.json", "preprocessor_config.json", "model.safetensors"]


def main() -> None:
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("ERROR: huggingface_hub is not installed.  Run:  pip install huggingface_hub")
        sys.exit(1)

    print(f"Downloading {MODEL_ID} @ {REVISION[:12]}... -> {TARGET}")
    TARGET.mkdir(parents=True, exist_ok=True)
    tmp = snapshot_download(
        repo_id=MODEL_ID,
        revision=REVISION,
        allow_patterns=REQUIRED,
        local_dir=str(TARGET),
        local_dir_use_symlinks=False,
    )
    for name in REQUIRED:
        src = Path(tmp) / name
        dst = TARGET / name
        if src != dst and src.exists():
            shutil.copy2(src, dst)

    missing = [n for n in REQUIRED if not (TARGET / n).is_file()]
    if missing:
        print(f"ERROR: Missing files after download: {missing}")
        sys.exit(1)

    weights = TARGET / "model.safetensors"
    with weights.open("rb") as fh:
        digest = hashlib.file_digest(fh, "sha256").hexdigest()
    print(f"\nmodel.safetensors SHA-256: {digest}")
    print("\nPaste the SHA-256 above into backend/app/analyzers/audio_checkpoint.py")
    print("  WEIGHTS_SHA256 = \"" + digest + "\"")
    print("\nDone — audio checkpoint ready.")


if __name__ == "__main__":
    main()
