"""Count request bytes even when Content-Length is absent or forged."""

from fastapi import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class BoundedBodies:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        total = 0
        path = scope.get("path", "")
        limit = (
            8 * 1024 * 1024
            if path.endswith("/photos") or path == "/api/v1/images/preview"
            else 16384
        )

        async def bounded_receive() -> Message:
            nonlocal total
            message = await receive()
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > limit:
                    raise HTTPException(413, "Request body is too large.")
            return message

        await self.app(scope, bounded_receive, send)
