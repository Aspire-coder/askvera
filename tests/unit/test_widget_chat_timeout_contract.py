from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_widget_uses_a_dedicated_chat_timeout_without_changing_default_requests():
    constants = (ROOT / "widget-wrapper/src/constants/api.ts").read_text(encoding="utf-8")
    runtime = (ROOT / "widget-wrapper/src/sdk/WidgetRuntime.tsx").read_text(encoding="utf-8")

    assert "DEFAULT_REQUEST_TIMEOUT_MS = 30_000" in constants
    assert "CHAT_REQUEST_TIMEOUT_MS = 95_000" in constants
    assert "timeoutMs: CHAT_REQUEST_TIMEOUT_MS" in runtime
    assert "chatClient, CHAT_REQUEST_TIMEOUT_MS" in runtime


def test_widget_preserves_cards_market_detection_and_release_badge():
    runtime = (ROOT / "widget-wrapper/src/sdk/WidgetRuntime.tsx").read_text(encoding="utf-8")
    locale_utils = (ROOT / "widget-wrapper/src/generic-widget/utils.ts").read_text(encoding="utf-8")
    header = (ROOT / "widget-wrapper/src/generic-widget/Header.tsx").read_text(encoding="utf-8")

    assert "quickReplies: envelope.data?.cards || []" in runtime
    assert "countries[0]?.code" not in locale_utils
    assert "gw-early-access-badge" in header
