# Events

The event bus is the integration point for SDK consumers, analytics, plugins, and future monitoring.

## Subscribe

```ts
const sub = AskVera.on("message_sent", (event) => {
  console.log(event);
});
```

## Unsubscribe

```ts
sub.unsubscribe();
```

or:

```ts
AskVera.off("message_sent", listener);
```

## One-Time Listener

```ts
AskVera.once("widget_opened", () => {
  console.log("First open");
});
```

## Event Guidelines

- Components emit events.
- Analytics listens through the event bus.
- Plugins subscribe through the SDK.
- Cross-cutting behavior should not be hardcoded inside UI components.

