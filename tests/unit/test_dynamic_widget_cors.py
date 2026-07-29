"""Unit tests for browser access to widget and operations API routes."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch

from app.widget_auth.cors import DynamicWidgetCorsMiddleware


def test_admin_put_preflight_is_allowed() -> None:
    app = FastAPI()
    app.add_middleware(DynamicWidgetCorsMiddleware)

    @app.put("/api/admin/support-routes/IT")
    def update_route() -> dict[str, bool]:
        return {"saved": True}

    with patch.object(DynamicWidgetCorsMiddleware, "_is_allowed_origin", return_value=True):
        with TestClient(app) as client:
            response = client.options(
                "/api/admin/support-routes/IT",
                headers={
                    "Origin": "https://operations.vera-api.xyz",
                    "Access-Control-Request-Method": "PUT",
                    "Access-Control-Request-Headers": "authorization,content-type",
                },
            )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://operations.vera-api.xyz"
    assert "PUT" in response.headers["access-control-allow-methods"]
    assert response.headers["access-control-allow-headers"] == "authorization,content-type"
