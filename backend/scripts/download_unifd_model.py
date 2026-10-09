"""Explicit download of pinned official UniFD head and OpenAI CLIP backbone."""
from pathlib import Path
import hashlib
import sys
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.analyzers.checkpoint_unifd import CLIP_ID, CLIP_REVISION, HEAD_URL, HEAD_SHA256
from app.config import Settings


def main():
    import torch
    from transformers import CLIPImageProcessor, CLIPVisionModelWithProjection

    destination = Settings().unifd_model_dir
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / "fc_weights.pth"
    if not target.exists():
        with urlopen(HEAD_URL, timeout=60) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != HEAD_SHA256:
            raise RuntimeError("Downloaded UniFD head checksum mismatch.")
        temporary = target.with_suffix(".download")
        try:
            temporary.write_bytes(data)
            torch.nn.Linear(768, 1).load_state_dict(torch.load(temporary, weights_only=True, map_location="cpu"))
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    if hashlib.sha256(target.read_bytes()).hexdigest() != HEAD_SHA256:
        raise RuntimeError("Existing UniFD head checksum mismatch.")
    if not (destination / "clip" / "model.safetensors").exists():
        print("Downloading OpenAI CLIP ViT-L/14 backbone...", flush=True)
        model = CLIPVisionModelWithProjection.from_pretrained(CLIP_ID, revision=CLIP_REVISION)
        model.save_pretrained(destination / "clip", safe_serialization=True)
    processor = CLIPImageProcessor.from_pretrained(CLIP_ID, revision=CLIP_REVISION, do_resize=False)
    processor.save_pretrained(destination / "clip")
    print(f"UniFD ready at {destination}. Analysis uses local files only.", flush=True)


if __name__ == "__main__":
    main()
