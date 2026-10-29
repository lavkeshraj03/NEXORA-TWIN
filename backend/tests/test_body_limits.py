import asyncio
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.core.body_limit import BodyLimitMiddleware


@pytest.mark.parametrize("path,method,size,headers,expected", [
    ("/api/v1/auth/login", "POST", 16385, [], 413),
    ("/api/v1/auth/login", "POST", 16385, [(b"content-length", b"1")], 413),
    ("/api/v1/auth/login", "POST", 16384, [], 200),
    ("/api/v1/auth/login", "POST", 0, [(b"content-length", b"9" * 5000)], 413),
    ("/api/v1/auth/login", "POST", 0, [(b"content-length", b"0" * 5000)], 200),
    ("/api/v1/auth/login", "POST", 0, [(b"content-length", b"16385")], 413),
    ("/api/v1/auth/login", "POST", 0, [(b"content-length", b"-1")], 400),
    ("/api/v1/auth/login", "POST", 0, [(b"content-length", b"1"), (b"content-length", b"1")], 400),
    ("/api/v1/businesses/id/imports", "POST", 17000, [], 200),
    ("/api/v1/businesses/id/documents", "POST", 2097152, [], 200),
    ("/api/v1/businesses/id/documents", "POST", 2097153, [], 413),
    ("/api/v1/businesses/id/documents", "PATCH", 17000, [], 413),
    ("/api/v1/businesses/id/documents/extra", "POST", 17000, [], 413),
])
def test_stream_limits_before_downstream(path, method, size, headers, expected):
    async def run():
        consumed = 0
        messages = []
        called = False
        async def receive():
            nonlocal consumed
            count = min(4096, size - consumed)
            consumed += count
            return {"type": "http.request", "body": b"x" * count, "more_body": consumed < size}
        async def send(message):
            messages.append(message)
        async def downstream(scope, receive, send):
            nonlocal called
            called = True
            message = await receive()
            assert len(message["body"]) == size and not message["more_body"]
            await send({"type": "http.response.start", "status": 200, "headers": []})
        await BodyLimitMiddleware(downstream)({"type": "http", "method": method, "path": path, "headers": headers}, receive, send)
        assert messages[0]["status"] == expected
        assert called == (expected == 200)
    asyncio.run(run())


def test_direct_api_rejects_oversize_json_before_authentication():
    with TestClient(create_app()) as client:
        response = client.post("/api/v1/auth/register", content=b"x" * 16385)
    assert response.status_code == 413
    assert response.json()["error"]["request_id"] == response.headers["x-request-id"]
    assert response.headers["cache-control"] == "no-store"
