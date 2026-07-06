"""Unit tests for centralized API protection middleware."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.middleware import RateLimitMiddleware, RequestSizeLimitMiddleware, SecurityHeadersMiddleware


def _app() -> FastAPI:
    app = FastAPI()

    @app.post("/api/chat")
    def chat() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/health")
    def health() -> dict[str, bool]:
        return {"ok": True}

    return app


def test_security_headers_added() -> None:
    app = _app()
    app.add_middleware(SecurityHeadersMiddleware)
    client = TestClient(app)

    response = client.get("/health")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"


def test_request_size_limit_rejects_oversized_body(monkeypatch) -> None:
    from api import middleware as middleware_module

    monkeypatch.setattr(middleware_module.settings, "MAX_REQUEST_BODY_BYTES", 4)
    app = _app()
    app.add_middleware(RequestSizeLimitMiddleware)
    client = TestClient(app)

    response = client.post("/api/chat", content="too large")

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "REQUEST_TOO_LARGE"


def test_endpoint_specific_rate_limit(monkeypatch) -> None:
    from api import middleware as middleware_module

    monkeypatch.setattr(middleware_module.settings, "RATE_LIMIT_POLICIES", {"/api/chat": 1})
    monkeypatch.setattr(middleware_module.settings, "RATE_LIMIT_WINDOW_SECONDS", 60)
    app = _app()
    app.add_middleware(RateLimitMiddleware)
    client = TestClient(app)

    assert client.post("/api/chat", json={"message": "hello"}).status_code == 200
    response = client.post("/api/chat", json={"message": "hello"})

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMITED"
