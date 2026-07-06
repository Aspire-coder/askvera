# ASK Vera Widget SDK

Reusable React + TypeScript widget SDK for embedding ASK Vera or another assistant experience into a host website.

The implementation is generic. No brand-specific text, country list, language list, consent copy, response text, product copy, or starter content is hardcoded in the components. Visible content comes from `config` or caller-provided children/render functions.

## Documentation

Developer documentation lives in:

```text
docs/
```

Start here:

- `docs/GettingStarted.md`
- `docs/Installation.md`
- `docs/SDK.md`
- `docs/Configuration.md`
- `docs/Themes.md`
- `docs/Events.md`
- `docs/Plugins.md`
- `docs/Deployment.md`
- `docs/Security.md`
- `docs/Troubleshooting.md`
- `docs/ReleaseNotes.md`
- `docs/Architecture.md`

## SDK Usage

```ts
import { AskVera } from "@askvera/widget";
import "@askvera/widget/styles.css";

await AskVera.init({
  apiUrl: "https://api.vera-api.xyz"
});

AskVera.open();
```

For script-tag usage:

```html
<link rel="stylesheet" href="./widget.min.css" />
<script src="./widget.min.js"></script>
<script>
  window.AskVera.init({
    apiUrl: "https://api.vera-api.xyz"
  });
</script>
```

Build diagnostics:

```ts
AskVera.getBuildInfo();
```

## AWS-Connected Demo

The default demo runs the widget locally and sends consent/chat events to the production Python API at `https://api.vera-api.xyz`. This mirrors the deployed widget host at `https://chat.vera-api.xyz`.

Start the API from the `chatbot python` folder:

```bash
uvicorn main:app --host 127.0.0.1 --port 8000
```

Then start the widget demo:

```bash
cd "chatbot python/widget-wrapper"
npm install
npm run demo
```

Open `http://127.0.0.1:5174`.

To point the demo at a different API host, add the `api` query string:

```text
http://127.0.0.1:5174/?api=https://your-api.example.com
```

Local development on `5174` and `5175` is intentionally allowed by backend CORS. Production defaults should continue to use `https://api.vera-api.xyz`.

The API needs AWS access for RDS, Valkey, Bedrock, Firehose, SQS, and Comprehend before real answers will return. If you are running locally with the defaults in `config/settings.py`, use `SSM_CONFIG_ENABLED=false` only when you do not want startup to read SSM Parameter Store.

## Offline Simulator

`LocalChatwootDemo` is still available when you want to review the visual flow without an API connection. It uses a simulated Chatwoot-style provider so the wrapper can be reviewed before the real Chatwoot inbox is ready.

## Files

- `src/generic-widget/GenericWidgetWrapper.tsx`
- `src/generic-widget/PlainStateGenericWidgetWrapper.tsx`
- `src/generic-widget/Header.tsx`
- `src/generic-widget/RegionSelector.tsx`
- `src/generic-widget/ConsentPanel.tsx`
- `src/generic-widget/LegalLinks.tsx`
- `src/generic-widget/MessageFeed.tsx`
- `src/generic-widget/Menu.tsx`
- `src/generic-widget/FloatingLauncher.tsx`
- `src/generic-widget/types.ts`
- `src/generic-widget/config/defaultTheme.ts`
- `src/generic-widget/config/exampleWidgetConfig.ts`
- `src/generic-widget/examples/ThirdPartyWidgetExample.tsx`
- `src/generic-widget/examples/ChatwootWidgetExample.tsx`
- `src/generic-widget/examples/BackendChatDemo.tsx`
- `src/generic-widget/examples/LocalChatwootDemo.tsx`
- `src/generic-widget/examples/foreverDemoConfig.tsx`
- `src/generic-widget/integrations/ChatwootWidgetAdapter.tsx`
- `demo/`

## Mock Chatbot

```tsx
import { useState } from "react";
import { GenericWidgetWrapper, exampleWidgetConfig, type WidgetMessage } from "./src/generic-widget";

export function DemoChat() {
  const [messages, setMessages] = useState<WidgetMessage[]>([]);

  return (
    <GenericWidgetWrapper
      config={exampleWidgetConfig}
      messages={messages}
      onSendMessage={(payload) => {
        setMessages((current) => [
          ...current,
          { id: crypto.randomUUID(), role: "user", content: payload.message }
        ]);
      }}
    />
  );
}
```

## Iframe

```tsx
import { GenericWidgetWrapper, exampleWidgetConfig } from "./src/generic-widget";

export function IframeWrapper() {
  return (
    <GenericWidgetWrapper config={{ ...exampleWidgetConfig, provider: { name: "Iframe provider", type: "iframe" } }}>
      <iframe title="Embedded assistant" src="https://example.com/embed" />
    </GenericWidgetWrapper>
  );
}
```

## Third-Party Script

```tsx
import { useEffect, useRef } from "react";
import { PlainStateGenericWidgetWrapper, exampleWidgetConfig } from "./src/generic-widget";

function ScriptMount({ src }: { src: string }) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const script = document.createElement("script");
    script.src = src;
    script.async = true;
    ref.current.appendChild(script);
    return () => script.remove();
  }, [src]);

  return <div ref={ref} />;
}

export function ScriptWrapper() {
  return (
    <PlainStateGenericWidgetWrapper config={{ ...exampleWidgetConfig, provider: { name: "Script provider", type: "script" } }}>
      <ScriptMount src="https://example.com/widget.js" />
    </PlainStateGenericWidgetWrapper>
  );
}
```

## Chatwoot

Use `ChatwootWidgetAdapter` when Chatwoot is the chat engine behind the generic wrapper. The wrapper still owns the launcher, header, region/language selector, consent step, legal links, and callbacks. Chatwoot is loaded as an injected third-party script and receives wrapper context through custom attributes.

```tsx
import { GenericWidgetWrapper, ChatwootWidgetAdapter, exampleWidgetConfig } from "./src/generic-widget";

export function ChatwootWrapper() {
  return (
    <GenericWidgetWrapper
      config={{
        ...exampleWidgetConfig,
        provider: { name: "Chatwoot", type: "script" }
      }}
    >
      {(state) => (
        <ChatwootWidgetAdapter
          baseUrl="https://app.chatwoot.com"
          websiteToken="replace-with-chatwoot-website-token"
          state={state}
          settings={{
            position: "right",
            type: "standard",
            launcherTitle: exampleWidgetConfig.labels.launcherAriaLabel
          }}
          customAttributes={{
            source: "generic-widget-wrapper"
          }}
        />
      )}
    </GenericWidgetWrapper>
  );
}
```

For self-hosted Chatwoot, pass the self-hosted app URL as `baseUrl`. Keep the website token outside this package and inject it from the consuming app's environment/config.

For a real local Chatwoot instance, run Chatwoot locally and pass its app URL, usually `http://localhost:3000`, plus the website token from the Chatwoot website inbox.
