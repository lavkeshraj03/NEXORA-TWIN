"""Bound request bodies before JSON parsing, including chunked direct API traffic."""
from starlette.responses import JSONResponse


class BodyLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        parts = scope["path"].strip("/").split("/")
        upload = (scope["method"] == "POST" and len(parts) == 5
                  and parts[:3] == ["api", "v1", "businesses"]
                  and parts[4] in {"documents", "imports"})
        limit = 2 * 1024 * 1024 if upload else 16 * 1024

        async def reject(status, message):
            await JSONResponse(status_code=status, content={"error": {
                "code": "body_limit", "message": message,
                "request_id": scope.get("state", {}).get("request_id")
            }})(scope, receive, send)

        lengths = [value for key, value in scope["headers"] if key.lower() == b"content-length"]
        if lengths:
            if len(lengths) != 1 or not lengths[0].isdigit():
                return await reject(400, "Invalid Content-Length")
            declared = lengths[0].lstrip(b"0") or b"0"
            if len(declared) > len(str(limit)) or int(declared) > limit:
                return await reject(413, "Request is too large")
        chunks = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > limit:
                return await reject(413, "Request is too large")
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        body = b"".join(chunks)
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)
