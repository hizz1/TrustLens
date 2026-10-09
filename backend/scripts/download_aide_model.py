"""Explicit one-time download for AIDE model. Analysis requests never access the model hub."""
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.analyzers.checkpoint_aide import MODEL_ID, REVISION, WEIGHTS_SHA256
from app.config import Settings


def main():
    from huggingface_hub import snapshot_download, login

    # Check for HF_TOKEN environment variable
    hf_token = os.environ.get("HF_TOKEN")
    if not hf_token:
        print("ERROR: HF_TOKEN environment variable is required for gated AIDE model.", flush=True)
        print("Please set HF_TOKEN with your Hugging Face access token:", flush=True)
        print("1. Go to https://huggingface.co/settings/tokens", flush=True)
        print("2. Create a new token with 'read' permissions", flush=True)
        print("3. Request access to https://huggingface.co/meet4150/AIDE_image_detector", flush=True)
        print("4. Set environment variable: set HF_TOKEN=your_token_here (Windows)", flush=True)
        print("   or export HF_TOKEN=your_token_here (Linux/Mac)", flush=True)
        sys.exit(1)

    # Login to Hugging Face
    print("Authenticating with Hugging Face...", flush=True)
    login(token=hf_token)

    destination = Settings().aide_model_dir
    destination.mkdir(parents=True, exist_ok=True)

    print(f"Downloading AIDE model from {MODEL_ID}", flush=True)
    try:
        model_path = snapshot_download(
            repo_id=MODEL_ID,
            revision=REVISION,
            local_dir=destination,
            local_dir_use_symlinks=False
        )
        print(f"Downloaded AIDE model to {model_path}", flush=True)
    except Exception as e:
        print(f"Download failed: {e}", flush=True)
        raise

    print(f"AIDE model ready at {destination}", flush=True)


if __name__ == "__main__":
    main()
