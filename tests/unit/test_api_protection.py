"""Unit tests for centralized API protection middleware without TestClient."""

import asyncio
import json
from types import SimpleNamespace

from fastapi.responses import JSONResponse, Response

from api.middleware import RateLimitMiddleware, RequestSizeLimitMiddleware, SecurityHeadersMiddleware


class FakeRequest:
    def __init__(self, path: str, headers: dict[str, str] | None = None) -> None:
        self.headers = headers or {}
        self.url = SimpleNamespace(path=path, scheme="http")
        self.client = SimpleNamespace(host="203.0.113.10")
        self.state = SimpleNamespace(correlation_id="cid")


def _run(coro):
    return asyncio.run(coro)


async def _ok_response(_request) -> Response:
    return Response(status_code=200)


def _json(response: JSONResponse) -> dict:
    return json.loads(response.body.decode("utf-8"))


def test_security_headers_added() -> None:
    middleware = SecurityHeadersMiddleware(lambda scope, receive, send: None)
    request = FakeRequest("/health")

    response = _run(middleware.dispatch(request, _ok_response))

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"


def test_request_size_limit_rejects_oversized_body(monkeypatch) -> None:
    from api import middleware as middleware_module

    monkeypatch.setattr(middleware_module.settings, "MAX_REQUEST_BODY_BYTES", 4)
    middleware = RequestSizeLimitMiddleware(lambda scope, receive, send: None)
    request = FakeRequest("/api/chat", {"content-length": "9"})

    response = _run(middleware.dispatch(request, _ok_response))

    assert response.status_code == 413
    assert _json(response)["error"]["code"] == "REQUEST_TOO_LARGE"


def test_document_upload_uses_the_separate_admin_limit(monkeypatch) -> None:
    from api import middleware as middleware_module

    monkeypatch.setattr(middleware_module.settings, "MAX_REQUEST_BODY_BYTES", 4)
    monkeypatch.setattr(middleware_module.settings, "ADMIN_UPLOAD_MAX_BYTES", 100)
    middleware = RequestSizeLimitMiddleware(lambda scope, receive, send: None)
    request = FakeRequest("/api/admin/documents", {"content-length": "80"})

    response = _run(middleware.dispatch(request, _ok_response))

    assert response.status_code == 200


def test_endpoint_specific_rate_limit(monkeypatch) -> None:
    from api import middleware as middleware_module

    monkeypatch.setattr(middleware_module.settings, "RATE_LIMIT_POLICIES", {"/api/chat": 1})
    monkeypatch.setattr(middleware_module.settings, "RATE_LIMIT_WINDOW_SECONDS", 60)
    monkeypatch.setattr(middleware_module.settings, "SHARED_SECURITY_STATE_ENABLED", False)
    middleware_module.security_state.reset_local_state()
    middleware = RateLimitMiddleware(lambda scope, receive, send: None)
    request = FakeRequest("/api/chat")

    assert _run(middleware.dispatch(request, _ok_response)).status_code == 200
    response = _run(middleware.dispatch(request, _ok_response))

    assert response.status_code == 429
    assert _json(response)["error"]["code"] == "RATE_LIMITED"


def test_rate_limit_uses_proxy_appended_client_address(monkeypatch) -> None:
    from api import middleware as middleware_module

    monkeypatch.setattr(middleware_module.settings, "RATE_LIMIT_POLICIES", {"/api/chat": 1})
    monkeypatch.setattr(middleware_module.settings, "RATE_LIMIT_WINDOW_SECONDS", 60)
    monkeypatch.setattr(middleware_module.settings, "SHARED_SECURITY_STATE_ENABLED", False)
    middleware_module.security_state.reset_local_state()
    first = FakeRequest("/api/chat", {"x-forwarded-for": "spoofed, 203.0.113.20"})
    second = FakeRequest("/api/chat", {"x-forwarded-for": "different-spoof, 203.0.113.20"})

    assert _run(RateLimitMiddleware(lambda scope, receive, send: None).dispatch(first, _ok_response)).status_code == 200
    response = _run(RateLimitMiddleware(lambda scope, receive, send: None).dispatch(second, _ok_response))

    assert response.status_code == 429
