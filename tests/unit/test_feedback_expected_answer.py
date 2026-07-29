"""Regression tests for optional expected-answer feedback."""

from starlette.requests import Request

from api import routes
from config import settings
from services import analytics
from utils.validators import FeedbackRequest


def _request() -> Request:
    request = Request({"type": "http", "method": "POST", "path": "/api/feedback", "headers": []})
    request.state.correlation_id = "feedback-event"
    return request


def _body(
    *,
    rating: int = -1,
    comment: str = "",
    expected_answer: str | None = None,
) -> FeedbackRequest:
    return FeedbackRequest(
        sessionId="session-1",
        messageId="message-1",
        rating=rating,
        comment=comment,
        expected_answer=expected_answer,
        metadata={"language": "en", "correlationId": "answer-1"},
    )


def test_expected_answer_is_trimmed_and_bounded() -> None:
    body = _body(expected_answer=f"  {'x' * 2100}  ")

    assert body.expected_answer == "x" * 2000


def test_disabled_feature_records_vote_without_expected_answer(monkeypatch) -> None:
    recorded: list[FeedbackRequest] = []
    queued: list[FeedbackRequest] = []
    monkeypatch.setattr(settings, "FEEDBACK_EXPECTED_ANSWER_ENABLED", False)
    monkeypatch.setattr(routes, "_session_matches_widget_token", lambda *_: True)
    monkeypatch.setattr(routes, "record_feedback_event", lambda body, *_: recorded.append(body))
    monkeypatch.setattr(routes, "enqueue_feedback", lambda body, *_: queued.append(body))

    response = routes.feedback(_body(expected_answer="The answer should contain private@example.com"), _request())

    assert response.success is True
    assert recorded[0].rating == -1
    assert recorded[0].expected_answer is None
    assert queued[0].expected_answer is None


def test_negative_feedback_scrubs_expected_answer_before_delivery(monkeypatch) -> None:
    recorded: list[FeedbackRequest] = []
    queued: list[FeedbackRequest] = []
    scrub_calls: list[tuple[str, str, str]] = []
    monkeypatch.setattr(settings, "FEEDBACK_EXPECTED_ANSWER_ENABLED", True)
    monkeypatch.setattr(routes, "_session_matches_widget_token", lambda *_: True)
    monkeypatch.setattr(
        routes,
        "scrub_pii",
        lambda text, correlation_id, language: (
            scrub_calls.append((text, correlation_id, language)) or "Use [EMAIL] instead."
        ),
    )
    monkeypatch.setattr(routes, "record_feedback_event", lambda body, *_: recorded.append(body))
    monkeypatch.setattr(routes, "enqueue_feedback", lambda body, *_: queued.append(body))

    response = routes.feedback(_body(expected_answer="Use private@example.com instead."), _request())

    assert response.success is True
    assert scrub_calls == [("Use private@example.com instead.", "feedback-event", "en")]
    assert recorded[0].expected_answer == "Use [EMAIL] instead."
    assert queued[0].expected_answer == "Use [EMAIL] instead."


def test_written_feedback_is_scrubbed_and_persisted_as_comment(monkeypatch) -> None:
    recorded: list[FeedbackRequest] = []
    queued: list[FeedbackRequest] = []
    scrub_calls: list[tuple[str, str, str]] = []
    monkeypatch.setattr(settings, "FEEDBACK_EXPECTED_ANSWER_ENABLED", True)
    monkeypatch.setattr(routes, "_session_matches_widget_token", lambda *_: True)
    monkeypatch.setattr(
        routes,
        "scrub_pii",
        lambda text, correlation_id, language: (
            scrub_calls.append((text, correlation_id, language)) or "Please use [EMAIL]."
        ),
    )
    monkeypatch.setattr(routes, "record_feedback_event", lambda body, *_: recorded.append(body))
    monkeypatch.setattr(routes, "enqueue_feedback", lambda body, *_: queued.append(body))

    response = routes.feedback(_body(comment="  Please use private@example.com.  "), _request())

    assert response.success is True
    assert scrub_calls == [("Please use private@example.com.", "feedback-event", "en")]
    assert recorded[0].comment == "Please use [EMAIL]."
    assert recorded[0].expected_answer is None
    assert queued[0].comment == "Please use [EMAIL]."


def test_helpful_feedback_never_persists_expected_answer(monkeypatch) -> None:
    recorded: list[FeedbackRequest] = []
    monkeypatch.setattr(settings, "FEEDBACK_EXPECTED_ANSWER_ENABLED", True)
    monkeypatch.setattr(routes, "_session_matches_widget_token", lambda *_: True)
    monkeypatch.setattr(routes, "record_feedback_event", lambda body, *_: recorded.append(body))
    monkeypatch.setattr(routes, "enqueue_feedback", lambda *_: None)
    monkeypatch.setattr(routes, "scrub_pii", lambda *_: (_ for _ in ()).throw(AssertionError("must not scrub")))

    routes.feedback(_body(rating=1, expected_answer="Unexpected value"), _request())

    assert recorded[0].expected_answer is None


def test_persistence_marks_scrubbed_suggestion_as_present(monkeypatch) -> None:
    captured: list[dict] = []

    class Connection:
        def execute(self, _statement, parameters):
            captured.append(parameters)

    class Begin:
        def __enter__(self):
            return Connection()

        def __exit__(self, *_args):
            return False

    class Engine:
        def begin(self):
            return Begin()

    monkeypatch.setattr(analytics, "get_engine", lambda: Engine())

    analytics.record_feedback_event(_body(expected_answer="Use [EMAIL]."), "feedback-event")

    assert captured[0]["expected_answer"] == "Use [EMAIL]."
    assert captured[0]["expected_answer_present"] is True
