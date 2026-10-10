import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.api.upload_limit import UploadLimitMiddleware
from app.analyzers.visual import VisualAnalyzer
from app.analyzers.unifd import UniFDAnalyzer
from app.analyzers.bitmind import BitMindAnalyzer
from app.analyzers.reality_defender import RealityDefenderAnalyzer
from app.analyzers.audio import AudioAnalyzer
from app.config import Settings
from app.schemas import ErrorDetail, ErrorResponse

logger = logging.getLogger(__name__)


def error_response(status: int, code: str, message: str, headers=None) -> JSONResponse:
    body = ErrorResponse(error=ErrorDetail(code=code, message=message))
    return JSONResponse(status_code=status, content=body.model_dump(), headers=headers)


def create_app(settings: Settings | None = None) -> CORSMiddleware:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        settings.ensure_data_directories()
        yield

    api = FastAPI(title="TrustLens API", version="0.1.0", lifespan=lifespan)
    api.state.settings = settings
    api.state.visual_analyzer = VisualAnalyzer(settings)
    api.state.unifd_analyzer = UniFDAnalyzer(settings)
    api.state.bitmind_analyzer = BitMindAnalyzer(settings)
    api.state.reality_defender_analyzer = RealityDefenderAnalyzer(settings)
    api.state.audio_analyzer = AudioAnalyzer(settings)
    api.add_middleware(UploadLimitMiddleware, max_bytes=settings.max_upload_bytes + 64 * 1024)
    api.include_router(router)

    @api.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException):
        return error_response(exc.status_code, f"http_{exc.status_code}", str(exc.detail), exc.headers)

    @api.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        return error_response(422, "validation_error", "Request validation failed.")

    @api.exception_handler(Exception)
    async def unexpected_error(_: Request, exc: Exception):
        logger.exception("Unhandled API error", exc_info=exc)
        return error_response(500, "internal_error", "An unexpected server error occurred.")

    # Wrapping the whole ASGI app also adds CORS headers to unexpected errors.
    return CORSMiddleware(
        api, allow_origins=settings.cors_origins, allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"], allow_credentials=False,
    )


app = create_app()
