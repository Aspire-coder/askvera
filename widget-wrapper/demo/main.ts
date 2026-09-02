// Imported before AskVera so its :root custom properties (shared names
// with the widget's own .gw-root theme tokens, e.g. --gw-text-caption-size)
// lose the cascade tie instead of silently overriding the widget's actual
// values - this was making the demo render text ~1px larger than
// production, which had been throwing off pixel-level layout checks here.
import "../src/styles/index.css";
import AskVera from "../src/sdk/index";

const params = new URLSearchParams(window.location.search);
const apiUrl = params.get("api") || "https://api.vera-api.xyz";
const status = document.querySelector<HTMLElement>("#local-demo-status");

if (status) {
  status.textContent = `AskVera local demo · API: ${apiUrl}`;
  status.style.cssText = "position:fixed;left:12px;bottom:12px;z-index:1;padding:8px 12px;border-radius:8px;background:#fff;color:#555;font:12px system-ui;box-shadow:0 2px 12px #0002";
}

void AskVera.init({
  widgetId: params.get("widget") || "askvera-demo",
  apiUrl,
  position: "bottom-right",
  conversationPersistence: "local"
}).catch((error: unknown) => {
  if (status) {
    status.textContent = `AskVera could not connect to ${apiUrl}. ${error instanceof Error ? error.message : "Check the API URL and try again."}`;
    status.style.color = "#9b2c2c";
  }
  console.error("AskVera local demo failed to initialize", error);
});
