"""Authorization tests for short-lived citation links."""

from types import SimpleNamespace

from api import routes
from config import settings


class Result:
    def __init__(self, approved: bool) -> None:
        self.approved = approved

    def first(self):
        return (1,) if self.approved else None


class Connection:
    def __init__(self, approved: bool) -> None:
        self.approved = approved

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, *_args, **_kwargs):
        return Result(self.approved)


class Engine:
    def __init__(self, approved: bool) -> None:
        self.approved = approved

    def connect(self):
        return Connection(self.approved)


class S3:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def generate_presigned_url(self, operation: str, **kwargs):
        self.calls.append({"operation": operation, **kwargs})
        return "https://downloads.example/policy.pdf?signature=test"


def _request(session_id: str = "session-1"):
    return SimpleNamespace(
        state=SimpleNamespace(
            correlation_id="source-test",
            widget_auth={"sessionId": session_id},
        )
    )


def _body(**updates):
    values = {
        "sessionId": "session-1",
        "country": "CA",
        "language": "en",
        "uri": f"s3://{settings.S3_BUCKET}/approved/Canada_en/policies/policy.pdf",
        "page": "12-13",
    }
    values.update(updates)
    return routes.SourceLinkRequest(**values)


def test_source_link_requires_matching_widget_session(monkeypatch) -> None:
    monkeypatch.setattr(settings, "WIDGET_AUTH_REQUIRED", True)

    response = routes.source_link(_body(), _request("another-session"))

    assert response.status_code == 403


def test_source_link_is_widget_authenticated_and_rate_limited() -> None:
    assert "/api/source-link" in settings.WIDGET_AUTH_PROTECTED_PATHS
    assert "/api/source-link" in settings.RATE_LIMIT_PATHS
    assert settings.RATE_LIMITS["/api/source-link"] > 0


def test_source_link_rejects_unapproved_or_wrong_locale_source(monkeypatch) -> None:
    monkeypatch.setattr(settings, "WIDGET_AUTH_REQUIRED", True)
    monkeypatch.setattr(routes, "has_valid_consent", lambda *_args: True)
    monkeypatch.setattr(routes, "get_engine", lambda: Engine(False))

    response = routes.source_link(_body(), _request())

    assert response.status_code == 404


def test_source_link_presigns_approved_s3_object_and_opens_exact_page(monkeypatch) -> None:
    s3 = S3()
    monkeypatch.setattr(settings, "WIDGET_AUTH_REQUIRED", True)
    monkeypatch.setattr(routes, "has_valid_consent", lambda *_args: True)
    monkeypatch.setattr(routes, "get_engine", lambda: Engine(True))
    monkeypatch.setattr(
        routes,
        "get_aws_clients",
        lambda: SimpleNamespace(s3=s3),
    )

    response = routes.source_link(_body(), _request())

    assert response.success is True
    assert response.data["url"].endswith("#page=12")
    assert s3.calls[0]["Params"] == {
        "Bucket": settings.S3_BUCKET,
        "Key": "approved/Canada_en/policies/policy.pdf",
    }
