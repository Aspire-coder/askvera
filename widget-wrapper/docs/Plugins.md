# Plugins

Plugins extend the widget without modifying core components.

## Plugin Shape

```ts
type AskVeraPlugin = {
  name: string;
  install: (api: AskVeraSdk) => void | Promise<void>;
};
```

## Example

```ts
await AskVera.use({
  name: "support-debug-panel",
  install(api) {
    api.on("message_received", (event) => {
      console.log("Received", event);
    });
  }
});
```

## Rules

- Plugin names should be unique.
- A plugin is installed only once.
- Plugins should use SDK methods instead of reaching into React internals.
- Plugins should subscribe to events instead of patching components.

