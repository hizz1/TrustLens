"""Explicit one-time download. Analysis requests never access the model hub."""
import hashlib
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.analyzers.checkpoint import MODEL_ID, REVISION, WEIGHTS_SHA256
from app.config import Settings


def main():
    from huggingface_hub import hf_hub_download
    from transformers import CLIPProcessor

    # Cache preprocessing/tokenizer assets during setup, never during an offline request.
    CLIPProcessor.from_pretrained("openai/clip-vit-large-patch14")

    destination = Settings().visual_model_dir
    destination.mkdir(parents=True, exist_ok=True)
    name = "model.torchscript"
    target = destination / name

    if target.exists():
        print(f"Model already exists at {target}", flush=True)
        return

    print(f"Downloading {name} from {MODEL_ID}", flush=True)
    try:
        model_path = hf_hub_download(repo_id=MODEL_ID, filename=name, revision=REVISION, local_dir=destination)
        print(f"Downloaded {name} to {model_path}", flush=True)
    except Exception as e:
        print(f"Download failed: {e}", flush=True)
        raise

    print(f"Model ready at {destination}", flush=True)


if __name__ == "__main__":
    main()
