"""Unit tests for privacy/legal document route."""

from unittest.mock import MagicMock, patch

from api import routes


def test_privacy_route_works_without_locale_params() -> None:
    """Legal documents are global and do not require country/lang query parameters."""
    request = MagicMock()
    request.state.correlation_id = "cid"

    with patch("api.routes.get_legal_documents", return_value={"version": "2026.1", "documents": []}):
        response = routes.privacy(request)

    assert response.success is True
    assert response.data == {"version": "2026.1", "documents": []}
