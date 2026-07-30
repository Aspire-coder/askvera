const ALLOWED_TAGS = new Set([
  "A", "ABBR", "ADDRESS", "ARTICLE", "ASIDE", "B", "BLOCKQUOTE", "BR", "CAPTION",
  "CITE", "CODE", "COL", "COLGROUP", "DD", "DEL", "DETAILS", "DIV", "DL", "DT",
  "EM", "FIGCAPTION", "FIGURE", "FOOTER", "H1", "H2", "H3", "H4", "H5", "H6",
  "HEADER", "HR", "I", "INS", "KBD", "LI", "MAIN", "MARK", "OL", "P", "PRE",
  "Q", "S", "SECTION", "SMALL", "SPAN", "STRONG", "SUB", "SUMMARY", "SUP",
  "TABLE", "TBODY", "TD", "TFOOT", "TH", "THEAD", "TR", "U", "UL"
]);

const DROP_WITH_CONTENT = new Set([
  "APPLET", "AUDIO", "BASE", "BUTTON", "CANVAS", "EMBED", "FORM", "FRAME",
  "FRAMESET", "IFRAME", "INPUT", "LINK", "MATH", "META", "NOSCRIPT", "OBJECT",
  "OPTION", "SCRIPT", "SELECT", "SOURCE", "STYLE", "SVG", "TEMPLATE", "TEXTAREA", "VIDEO"
]);

const GLOBAL_ATTRIBUTES = new Set(["dir", "lang", "title"]);
const TAG_ATTRIBUTES: Record<string, Set<string>> = {
  A: new Set(["href", "target"]),
  BLOCKQUOTE: new Set(["cite"]),
  COL: new Set(["span"]),
  COLGROUP: new Set(["span"]),
  DEL: new Set(["cite", "datetime"]),
  INS: new Set(["cite", "datetime"]),
  OL: new Set(["reversed", "start", "type"]),
  Q: new Set(["cite"]),
  TD: new Set(["colspan", "headers", "rowspan"]),
  TH: new Set(["abbr", "colspan", "headers", "rowspan", "scope"])
};

function isSafeUrl(value: string): boolean {
  const normalized = value.replace(/\s/g, "").toLowerCase();
  if (!normalized || normalized.startsWith("#")) return true;
  try {
    return ["http:", "https:", "mailto:", "tel:"].includes(new URL(normalized, window.location.origin).protocol);
  } catch {
    return false;
  }
}

export function sanitizeLegalHtml(value: string): string {
  const parsed = new DOMParser().parseFromString(value, "text/html");
  const elements = Array.from(parsed.body.querySelectorAll("*"));

  elements.forEach((element) => {
    if (DROP_WITH_CONTENT.has(element.tagName)) {
      element.remove();
      return;
    }
    if (!ALLOWED_TAGS.has(element.tagName)) {
      element.replaceWith(...Array.from(element.childNodes));
      return;
    }

    const tagAttributes = TAG_ATTRIBUTES[element.tagName] || new Set<string>();
    Array.from(element.attributes).forEach((attribute) => {
      const name = attribute.name.toLowerCase();
      const allowed = GLOBAL_ATTRIBUTES.has(name) || tagAttributes.has(name);
      const unsafeUrl = ["href", "cite"].includes(name) && !isSafeUrl(attribute.value);
      if (!allowed || name.startsWith("on") || name === "style" || unsafeUrl) {
        element.removeAttribute(attribute.name);
      }
    });

    if (element.tagName === "A" && element.getAttribute("target") === "_blank") {
      element.setAttribute("rel", "noopener noreferrer");
    } else if (element.tagName === "A") {
      element.removeAttribute("target");
    }
  });

  return parsed.body.innerHTML;
}
