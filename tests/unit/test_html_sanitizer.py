"""Security tests for content-managed legal HTML."""

from services.html_sanitizer import sanitize_legal_html


def test_sanitizer_preserves_document_structure() -> None:
    html = (
        "<h1>Privacy Notice</h1><p class='lead'>Read this.</p>"
        "<table><tr><th scope='col'>Term</th><td colspan='2'>Value</td></tr></table>"
        "<a href='https://example.com' target='_blank'>Official source</a>"
    )

    sanitized = sanitize_legal_html(html)

    assert "<h1>Privacy Notice</h1>" in sanitized
    assert "<p>Read this.</p>" in sanitized
    assert '<th scope="col">Term</th>' in sanitized
    assert 'href="https://example.com"' in sanitized
    assert 'rel="noopener noreferrer"' in sanitized


def test_sanitizer_removes_executable_embedded_and_form_content() -> None:
    html = (
        "<p onclick='steal()' style='color:red'>Safe text</p>"
        "<script>alert(1)</script><style>body{display:none}</style>"
        "<iframe src='https://attacker.invalid'>frame</iframe>"
        "<form><input value='secret'><button>Send</button></form>"
        "<img src='https://tracker.invalid/pixel'>"
    )

    sanitized = sanitize_legal_html(html)

    assert sanitized == "<p>Safe text</p>"


def test_sanitizer_blocks_unsafe_links_and_keeps_safe_schemes() -> None:
    html = (
        "<a href='javascript:alert(1)'>Unsafe</a>"
        "<a href='data:text/html,bad'>Data</a>"
        "<a href='mailto:privacy@example.com'>Email</a>"
        "<a href='#rights'>Rights</a>"
    )

    sanitized = sanitize_legal_html(html)

    assert 'href="javascript:' not in sanitized
    assert 'href="data:' not in sanitized
    assert 'href="mailto:privacy@example.com"' in sanitized
    assert 'href="#rights"' in sanitized
