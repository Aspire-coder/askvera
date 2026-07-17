"""Tests for application process lifecycle behavior."""

import signal

import main


def test_sigterm_marks_service_draining_and_forwards_to_uvicorn(monkeypatch) -> None:
    forwarded: list[tuple[int, object]] = []
    frame = object()

    monkeypatch.setattr(main, "shutdown_requested", False)
    monkeypatch.setattr(
        main,
        "_previous_sigterm_handler",
        lambda signum, received_frame: forwarded.append((signum, received_frame)),
    )

    main._handle_sigterm(signal.SIGTERM, frame)

    assert main.shutdown_requested is True
    assert forwarded == [(signal.SIGTERM, frame)]


def test_sigterm_does_not_call_default_signal_handler(monkeypatch) -> None:
    monkeypatch.setattr(main, "shutdown_requested", False)
    monkeypatch.setattr(main, "_previous_sigterm_handler", signal.SIG_DFL)

    main._handle_sigterm(signal.SIGTERM, None)

    assert main.shutdown_requested is True
