import hashlib
from pathlib import Path
from typing import BinaryIO

from fastapi import HTTPException


def save_and_hash(source: BinaryIO, destination: Path, limit: int) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with destination.open("xb") as target:
        while chunk := source.read(1024 * 1024):
            size += len(chunk)
            if size > limit:
                raise HTTPException(413, "File exceeds the configured upload size limit.")
            digest.update(chunk)
            target.write(chunk)
    if size == 0:
        raise HTTPException(422, "The uploaded file is empty.")
    return digest.hexdigest(), size
