from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse


class UploadLimitMiddleware:
    """Bound multipart bodies before they can spool an unbounded file to disk."""

    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"] != "/api/analyze":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        try:
            declared = int(headers.get(b"content-length", b"0"))
        except ValueError:
            declared = 0
        if declared > self.max_bytes:
            response = JSONResponse(status_code=413, content={"error": {"code": "http_413", "message": "Upload request exceeds the configured size limit."}})
            return await response(scope, receive, send)
        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise HTTPException(413, "Upload request exceeds the configured size limit.")
            return message

        await self.app(scope, limited_receive, send)
