import subprocess


class MediaToolError(Exception):
    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.status_code = status_code


def run_tool(arguments: list[str], timeout: float) -> str:
    """No shell, bounded runtime, and no raw command diagnostics in API responses."""
    try:
        result = subprocess.run(
            arguments, stdin=subprocess.DEVNULL, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=timeout,
            check=False, shell=False,
        )
    except (FileNotFoundError, PermissionError) as exc:
        raise MediaToolError("FFmpeg/FFprobe is unavailable. Check the configured executable paths.", 503) from exc
    except subprocess.TimeoutExpired as exc:
        raise MediaToolError("Media processing exceeded the configured time limit.", 504) from exc
    if result.returncode != 0:
        raise MediaToolError("Media could not be decoded or processed. It may be corrupt or unsupported.")
    return result.stdout
