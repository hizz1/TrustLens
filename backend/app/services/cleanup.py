import shutil
from pathlib import Path
from uuid import UUID


def remove_analysis(data_dir: Path, analysis_id: str) -> None:
    """Only remove a canonical UUID's directories inside the configured data root."""
    if str(UUID(analysis_id)) != analysis_id:
        raise ValueError("Expected a canonical analysis UUID")
    for category in ("uploads", "frames", "audio"):
        parent = (data_dir / category).resolve()
        target = (parent / analysis_id).resolve()
        if target.parent != parent:
            raise ValueError("Analysis path escaped its data directory")
        if target.exists():
            shutil.rmtree(target)
