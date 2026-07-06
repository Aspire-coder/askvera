# SDK

The public SDK is exposed as both a module export and a browser global.

```ts
import { AskVera } from "@askvera/widget";
```

```js
window.AskVera
```

## Lifecycle

```ts
await AskVera.init(config);
AskVera.open();
AskVera.close();
AskVera.destroy();
AskVera.reset();
AskVera.updateConfig(partialConfig);
```

## Session

```ts
const session = AskVera.getSession();
const newSession = AskVera.resetSession();
```

## Locale

```ts
AskVera.setCountry("US");
AskVera.setLanguage("en");
AskVera.setLocale("CA", "en");
```

## Conversation

```ts
AskVera.sendMessage("How do I contact support?");
AskVera.clearConversation();
```

`sendMessage()` respects the consent flow. If consent is required, the widget opens the consent step and keeps the message as the draft.

## Events

```ts
const subscription = AskVera.on("message_sent", (event) => {
  console.log(event);
});

subscription.unsubscribe();
```

Also available:

```ts
AskVera.off(type, listener);
AskVera.once(type, listener);
```

## State And Diagnostics

```ts
AskVera.isOpen();
AskVera.isReady();
AskVera.getVersion();
AskVera.getBuildInfo();
AskVera.getConfig();
```

`getBuildInfo()` returns:

```ts
{
  sdk: string;
  version: string;
  buildDate: string;
  commit: string;
}
```

## Plugins

```ts
await AskVera.use({
  name: "example-plugin",
  install(api) {
    api.on("widget_opened", () => {
      console.log("Widget opened");
    });
  }
});
```

