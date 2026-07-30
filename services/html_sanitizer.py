"""Conservative HTML sanitization for content-managed legal documents."""

from __future__ import annotations

from html import escape
from html.parser import HTMLParser
from urllib.parse import urlparse

ALLOWED_TAGS = {
    "a",
    "abbr",
    "address",
    "article",
    "aside",
    "b",
    "blockquote",
    "br",
    "caption",
    "cite",
    "code",
    "col",
    "colgroup",
    "dd",
    "del",
    "details",
    "div",
    "dl",
    "dt",
    "em",
    "figcaption",
    "figure",
    "footer",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "hr",
    "i",
    "ins",
    "kbd",
    "li",
    "main",
    "mark",
    "ol",
    "p",
    "pre",
    "q",
    "s",
    "section",
    "small",
    "span",
    "strong",
    "sub",
    "summary",
    "sup",
    "table",
    "tbody",
    "td",
    "tfoot",
    "th",
    "thead",
    "tr",
    "u",
    "ul",
}
VOID_TAGS = {"br", "col", "hr"}
DROP_WITH_CONTENT = {
    "applet",
    "audio",
    "base",
    "button",
    "canvas",
    "embed",
    "form",
    "frame",
    "frameset",
    "iframe",
    "input",
    "link",
    "math",
    "meta",
    "noscript",
    "object",
    "option",
    "script",
    "select",
    "source",
    "style",
    "svg",
    "template",
    "textarea",
    "video",
}
GLOBAL_ATTRIBUTES = {"dir", "lang", "title"}
TAG_ATTRIBUTES = {
    "a": {"href", "target"},
    "blockquote": {"cite"},
    "col": {"span"},
    "colgroup": {"span"},
    "del": {"cite", "datetime"},
    "ins": {"cite", "datetime"},
    "ol": {"reversed", "start", "type"},
    "q": {"cite"},
    "td": {"colspan", "headers", "rowspan"},
    "th": {"abbr", "colspan", "headers", "rowspan", "scope"},
}
SAFE_SCHEMES = {"", "http", "https", "mailto", "tel"}
URL_ATTRIBUTES = {"cite", "href"}


def _safe_url(value: str) -> bool:
    normalized = "".join(value.split()).lower()
    if not normalized or normalized.startswith("#"):
        return True
    return urlparse(normalized).scheme in SAFE_SCHEMES


class _LegalHtmlSanitizer(HTMLParser):
    """Allow document markup while dropping executable and embedded content."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.output: list[str] = []
        self._dropped_depth = 0
        self._open_tags: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.lower()
        if self._dropped_depth:
            if normalized_tag in DROP_WITH_CONTENT:
                self._dropped_depth += 1
            return
        if normalized_tag in DROP_WITH_CONTENT:
            self._dropped_depth = 1
            return
        if normalized_tag not in ALLOWED_TAGS:
            return

        allowed_attributes = GLOBAL_ATTRIBUTES | TAG_ATTRIBUTES.get(normalized_tag, set())
        rendered_attributes: list[str] = []
        target_blank = False
        for name, raw_value in attrs:
            normalized_name = name.lower()
            if normalized_name.startswith("on") or normalized_name == "style":
                continue
            if normalized_name not in allowed_attributes:
                continue
            value = raw_value or ""
            if normalized_name in URL_ATTRIBUTES and not _safe_url(value):
                continue
            if normalized_name == "target":
                if value != "_blank":
                    continue
                target_blank = True
            rendered_attributes.append(f' {normalized_name}="{escape(value, quote=True)}"')

        if normalized_tag == "a" and target_blank:
            rendered_attributes.append(' rel="noopener noreferrer"')
        self.output.append(f"<{normalized_tag}{''.join(rendered_attributes)}>")
        if normalized_tag not in VOID_TAGS:
            self._open_tags.append(normalized_tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() in ALLOWED_TAGS and tag.lower() not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if self._dropped_depth:
            if normalized_tag in DROP_WITH_CONTENT:
                self._dropped_depth -= 1
            return
        if normalized_tag not in ALLOWED_TAGS or normalized_tag in VOID_TAGS:
            return
        if normalized_tag not in self._open_tags:
            return

        while self._open_tags:
            open_tag = self._open_tags.pop()
            self.output.append(f"</{open_tag}>")
            if open_tag == normalized_tag:
                break

    def handle_data(self, data: str) -> None:
        if not self._dropped_depth:
            self.output.append(escape(data))

    def get_html(self) -> str:
        while self._open_tags:
            self.output.append(f"</{self._open_tags.pop()}>")
        return "".join(self.output)


def sanitize_legal_html(value: str) -> str:
    """Return safe, inert HTML suitable for the widget and print view."""
    sanitizer = _LegalHtmlSanitizer()
    sanitizer.feed(value)
    sanitizer.close()
    return sanitizer.get_html()
