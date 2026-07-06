# Architecture

ASK Vera Widget is structured as an embeddable SDK with a React implementation.

```text
Host Website
  -> AskVera SDK
  -> Runtime Config
  -> Widget State
  -> Event Bus
  -> API Layer
  -> Session Manager
  -> Storage Adapter
  -> FastAPI Backend
```

## Key Boundaries

Networking:

```text
src/api/
```

Browser storage:

```text
src/storage/
```

Session behavior:

```text
src/services/sessionManager.ts
```

Global state:

```text
src/state/
```

Theme generation:

```text
src/themes/
```

Events and analytics:

```text
src/events/
src/services/analyticsService.ts
```

Public SDK:

```text
src/sdk/
```

## Architecture Rules

- UI components should not call `fetch()` directly.
- UI components should not access `localStorage` directly.
- Components emit events; analytics listens through the event bus.
- Theme values should flow through theme tokens and CSS variables.
- External consumers should use the SDK instead of internal React components.
- Generated `dist/` files should be reproducible from source with `npm run build`.

