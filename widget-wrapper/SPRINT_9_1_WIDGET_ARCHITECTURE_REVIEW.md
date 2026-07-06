# Sprint 9.1 - Widget Foundation Architecture Review

## Status

Steps 1.1, 1.2, 1.3, 1.4, 1.5, and 1.6 are complete.

This review covers the current reusable widget package in `widget-wrapper` and defines the refactoring plan for Sprint 9.1. The main conclusion is that the widget is functional and already has a good reusable foundation, but it is still organized like a demo plus wrapper instead of a standalone widget software product.

The refactor should preserve current behavior while moving responsibilities into clearer product-grade layers.

## Current Folder Structure

Current package:

```text
widget-wrapper/
  demo/
    index.html
    src/
      App.tsx
      main.tsx
      styles.css
  src/
    generic-widget/
      config/
      examples/
      integrations/
      ConsentPanel.tsx
      FloatingLauncher.tsx
      GenericWidgetWrapper.tsx
      Header.tsx
      LegalLinks.tsx
      Menu.tsx
      MessageFeed.tsx
      PlainStateGenericWidgetWrapper.tsx
      RegionSelector.tsx
      generic-widget.css
      index.ts
      types.ts
      utils.ts
  package.json
  tsconfig.json
  vite.config.ts
  README.md
```

### What Is Good

- The core widget is separated from the demo folder.
- Component names are clear and easy to understand.
- The wrapper already supports custom React children, iframes, script widgets, and message feeds.
- Chatwoot is isolated behind `integrations/ChatwootWidgetAdapter.tsx`.
- The package already exports a public entrypoint through `src/generic-widget/index.ts`.

### Gaps

- `src/generic-widget` is too flat for a growing SDK.
- API behavior is embedded in `examples/BackendChatDemo.tsx`.
- Session persistence utilities are mixed into generic utility helpers.
- Theme generation is embedded inside `GenericWidgetWrapper.tsx`.
- CSS is one large file instead of a theme/component/style system.
- Demo code and production adapter code are too close together.
- There is no explicit SDK layer such as `AskVera.init()`, `AskVera.open()`, or `AskVera.destroy()`.

## Component Review

### Core Components

Current core components:

- `GenericWidgetWrapper.tsx`
- `PlainStateGenericWidgetWrapper.tsx`
- `Header.tsx`
- `FloatingLauncher.tsx`
- `Menu.tsx`
- `RegionSelector.tsx`
- `ConsentPanel.tsx`
- `LegalLinks.tsx`
- `MessageFeed.tsx`

### What Is Good

- Components are small enough to understand.
- Consent, legal links, region selection, messages, menu, launcher, and header are separated.
- Accessibility is present through labels, `aria-label`, `role="log"`, `aria-live`, and screen-reader-only labels.
- `MessageFeed` includes basic markdown formatting support for headings, bullets, and bold text.
- `ConsentPanel` now has a single acknowledgement checkbox and disables accept until checked.

### Gaps

- `GenericWidgetWrapper.tsx` owns too many state concerns:
  - open/closed state
  - menu state
  - locale state
  - message draft
  - consent state
  - session metadata writes
  - consent version checks
  - success banner state
- `ConsentPanel` has its own local acknowledgement state. This is acceptable for local UI state, but the global consent status should belong to the widget state layer.
- `MessageFeed` contains markdown parsing logic directly in the component. This should move to a formatter utility or renderer service.
- `PlainStateGenericWidgetWrapper` is currently only a pass-through wrapper. It should either become a real dependency-free adapter or be removed once the state system is centralized.

## API Communication Review

Most production API communication currently lives in:

```text
src/generic-widget/examples/BackendChatDemo.tsx
```

It includes:

- API envelope types
- API error classes
- request timeout logic
- `fetchWithTimeout`
- `getJson`
- `postJson`
- `/api/config`
- `/api/privacy`
- `/api/consent`
- `/api/chat`
- correlation ID logging
- network/API/timeout error handling

### What Is Good

- API requests use a 30-second timeout.
- Network errors, timeout errors, and API response errors are represented separately.
- The backend envelope shape is handled consistently.
- Duplicate chat submits are blocked with `requestInFlightRef`.
- Backend correlation IDs are preserved in message metadata and logged in local development.
- `/api/config` and `/api/privacy` load dynamically instead of hardcoding markets/legal content.

### Gaps

- UI components should not own API client code.
- There is no dedicated API folder.
- There are no named API services yet:
  - Chat API
  - Consent API
  - Config API
  - Privacy/legal API
  - Feedback API
  - Health API
- Retry/reconnect behavior is not centralized.
- API types are local to `BackendChatDemo.tsx`, so they cannot be reused cleanly by the SDK.

## State Management Review

Current state is distributed between:

- `GenericWidgetWrapper.tsx`
- `BackendChatDemo.tsx`
- `ConsentPanel.tsx`
- browser `localStorage`

### What Is Good

- Session ID and visitor ID are persisted.
- Session metadata stores:
  - session ID
  - creation timestamp
  - legal version
  - market
  - language
- Legal version mismatch resets local consent state.
- Pending message retry after consent is handled.
- Request loading state prevents duplicate chat sends.

### Gaps

- There is no centralized widget store.
- Several global states are maintained separately:
  - open/closed
  - loading
  - session
  - conversation
  - country
  - language
  - consent
  - errors
  - pending message
- State transitions are spread across components, making future SDK APIs harder.
- There is no single reset path for `AskVera.reset()`.
- There is no single reconnect path.

## CSS Organization Review

Current CSS:

```text
src/generic-widget/generic-widget.css
```

The file is currently about 599 lines.

### What Is Good

- Styles are namespaced with `gw-`, which reduces leakage into host websites.
- Theme values are exposed through CSS variables.
- Layout is polished and close to the Forever visual direction.
- Focus and disabled states exist.
- The widget is responsive enough for current demo usage.

### Gaps

- Layout, themes, component styling, animation, and brand-like choices are all in one file.
- Theme tokens live partly in TypeScript and partly in CSS.
- There is no separate light/dark/custom theme strategy.
- Runtime theme switching is not formalized.
- The current CSS is not organized as a reusable design system.

## Build Process Review

Current scripts:

```json
{
  "dev": "vite demo --host 127.0.0.1 --port 5174",
  "demo": "vite demo --host 127.0.0.1 --port 5174",
  "build": "vite build",
  "build:demo": "vite build demo",
  "typecheck": "tsc --noEmit"
}
```

Current Vite library build:

```text
entry: src/generic-widget/index.ts
formats: es
fileName: generic-widget-wrapper
external: react, react-dom, react/jsx-runtime
```

### What Is Good

- Vite library mode exists.
- React is externalized, which is appropriate for an npm-style package.
- Demo build and library build are separate.
- TypeScript typecheck is available.

### Gaps

- There is no dedicated embeddable browser SDK build yet.
- No `widget.js` / `widget.min.js` output is defined.
- No CSS artifact naming contract is defined.
- No source map/version metadata contract exists.
- Package is still private and named generically.
- There is no public SDK entrypoint for script-tag installation.

## Session Handling Review

Current session handling lives in:

```text
src/generic-widget/utils.ts
```

### What Is Good

- Visitor ID generation exists.
- Session ID generation exists.
- IDs are persisted to `localStorage`.
- Session metadata is persisted to `localStorage`.
- Legal version, market, and language are stored with the session metadata.
- Corrupt stored metadata is ignored safely.

### Gaps

- Session logic should be moved to a dedicated `services/sessionManager.ts`.
- Expiration is not clearly centralized.
- Reconnect and reset flows are not explicit.
- Storage keys are configurable, but storage behavior is not behind a clean interface.
- There is no single source of truth for whether a restored session is valid.

## Configuration Review

Current configuration is based on `GenericWidgetConfig` in:

```text
src/generic-widget/types.ts
```

### What Is Good

The config already supports:

- brand name
- welcome text
- loading text
- success text
- labels
- menu labels
- provider name/type
- consent
- policy links
- countries
- languages
- starter topics
- contextual topics
- theme
- default country/language
- persistence keys

### Gaps

The next product-grade configuration object should explicitly support:

- API URL
- theme mode
- accent color
- logo
- company name
- launcher position
- widget width
- widget height
- welcome message
- default country
- default language
- font
- debug mode
- SDK mount target

The current `GenericWidgetConfig` is strong for rendering, but it should be wrapped by a higher-level runtime config for the full widget product.

## Error Handling Review

### What Is Good

- API errors distinguish timeout, network, and response failures.
- Config and privacy load failures use stable warning message IDs to avoid duplicate warning spam.
- Consent failure blocks entry into chat and shows a friendly message.
- Chat consent-required errors trigger the consent UI and retry the pending message after consent.

### Gaps

- Error classes should move to `src/api/errors.ts`.
- User-facing error copy should be configurable.
- Internal debug behavior should be controlled by config.
- The widget needs a structured event for errors so host sites can subscribe.

## Refactoring Plan

### Step 1.2 - Folder Structure

Create the target structure without changing behavior first:

```text
widget-wrapper/
  src/
    api/
    assets/
    adapters/
    components/
    config/
    constants/
    events/
    hooks/
    integrations/
    localization/
    plugins/
    providers/
    renderers/
    sdk/
    services/
    state/
    storage/
    styles/
    testing/
    themes/
    types/
    utils/
```

Move files in small groups:

1. Create the full long-term folder structure with placeholder files so Git tracks it.
2. Keep all existing imports and compatibility exports working.
3. Move UI components into `src/components`.
4. Move API helpers from `BackendChatDemo.tsx` into `src/api`.
5. Move session helpers from `utils.ts` into `src/services/sessionManager.ts`.
6. Move storage-specific code into `src/storage`.
7. Move locale helpers into `src/utils/locale.ts`.
8. Move widget-specific text helpers into `src/localization`.
9. Move markdown rendering helpers into `src/renderers`.
10. Move theme helpers into `src/themes`.
11. Reserve `src/providers`, `src/adapters`, and `src/plugins` for future integrations.
12. Keep compatibility exports in `src/generic-widget/index.ts` until the new structure is stable.

### Step 1.3 - Configuration System

Introduce `WidgetRuntimeConfig` as the top-level product config.

It should include:

- `apiUrl`
- `companyName`
- `logo`
- `theme`
- `accentColor`
- `launcherPosition`
- `width`
- `height`
- `welcomeMessage`
- `defaultCountry`
- `defaultLanguage`
- `fontFamily`
- `debug`

Keep `GenericWidgetConfig` as the render/content config, but derive it from runtime config plus backend config.

### Step 1.4 - Widget State

Create a centralized state layer:

```text
src/state/
  widgetState.ts
  widgetReducer.ts
  WidgetStateProvider.tsx
  useWidgetState.ts
```

Store:

- open/closed
- loading
- connected
- visitor ID
- session ID
- session metadata
- messages
- selected country
- selected language
- consent status
- typing state
- errors
- pending message

### Step 1.5 - API Layer

Create:

```text
src/api/
  client.ts
  errors.ts
  envelope.ts
  chatApi.ts
  consentApi.ts
  configApi.ts
  privacyApi.ts
  feedbackApi.ts
  healthApi.ts
```

No UI component should call `fetch` directly after this step.

### Step 1.6 - Event Bus

Create:

```text
src/events/
  eventBus.ts
  events.ts
```

Expose events:

- widget open
- widget close
- message sent
- message received
- feedback submitted
- error
- reconnect
- consent accepted
- consent rejected
- country changed
- language changed

### Step 1.7 - Session Manager

Create:

```text
src/services/sessionManager.ts
```

Responsibilities:

- create session
- restore session
- validate expiration
- persist metadata
- reset session
- reconnect session

### Step 1.8 - Theme Manager

Create:

```text
src/themes/
  defaultTheme.ts
  themeManager.ts
  themeTypes.ts
```

Support:

- light mode
- dark mode
- custom theme
- runtime switching
- brand color overrides
- font overrides

### Step 1.9 - Analytics and Feature Flags

Create lightweight widget-side analytics and feature flag foundations:

```text
src/events/
  analytics.ts
src/config/
  featureFlags.ts
```

Initial feature flags:

- streaming
- feedback
- typing indicator
- markdown
- dark mode
- citations
- attachments

Analytics events should be provider-neutral so they can later feed CloudWatch, Google Analytics, Adobe Analytics, Mixpanel, Segment, or a custom enterprise system.

### Step 1.10 - Widget SDK

Create:

```text
src/sdk/
  AskVera.ts
  mount.tsx
```

Public API:

```ts
AskVera.init(config)
AskVera.open()
AskVera.close()
AskVera.destroy()
AskVera.reset()
AskVera.updateConfig(config)
```

### Step 1.11 - Build Pipeline

Update build output to produce:

```text
dist/
  widget.js
  widget.min.js
  widget.css
  widget.css.map
  widget.js.map
  version.json
```

Keep the React library build separate from the standalone SDK build if needed.

### Step 1.12 - Documentation and Examples

Update documentation and examples after the architecture is stabilized:

- React usage
- Script-tag usage
- iframe usage
- Chatwoot usage
- custom provider usage
- theme customization
- event subscriptions
- feature flags
- troubleshooting
- local demo setup

## Recommended Sprint 9.1 Order

1. Complete folder structure and compatibility exports.
2. Add runtime configuration system.
3. Add centralized state provider/reducer.
4. Extract API layer from `BackendChatDemo.tsx`.
5. Add event bus.
6. Extract session manager.
7. Add theme manager.
8. Add analytics and feature flags.
9. Add SDK API.
10. Update build pipeline.
11. Update documentation and examples.

## Risk Notes

- Do not rewrite the UI while reorganizing folders.
- Keep `GenericWidgetWrapper` behavior stable during Step 1.2.
- Keep the local demo running at `127.0.0.1:5174`.
- Keep the AWS backend demo query parameter behavior.
- Keep dynamic `/api/config` and `/api/privacy`.
- Keep consent-required retry behavior.
- Keep request timeout handling.
- Keep correlation ID logging in local development.
- Every step must preserve behavior, pass `npm run typecheck`, and keep the local demo runnable before moving on.

## Step 1.1 Conclusion

The widget is ready for productization. It already has the correct UX foundation and backend-connected behavior, but the next work should focus on clean package boundaries:

- UI components in `components`
- backend communication in `api`
- persistent session behavior in `services`
- global state in `state`
- theme behavior in `themes`
- public script API in `sdk`

This will make ASK Vera reusable as a real embeddable widget product instead of only a React demo wrapper.

## Step 1.3 Implementation Notes

Step 1.3 added the first version of the centralized runtime configuration system.

New configuration modules:

```text
src/config/
  backendConfig.ts
  configLoader.ts
  configValidator.ts
  defaults.ts
  featureFlags.ts
  index.ts
  runtimeConfig.ts
  themeConfig.ts
```

The configuration layer now separates:

- `RuntimeConfig`: values passed by the host website or future `AskVera.init()`.
- `BackendConfig`: values loaded from the backend, such as markets, languages, legal version, and legal documents.
- `ThemeConfig`: visual settings only.
- `WidgetFeatureFlags`: centralized feature toggles.
- `WidgetConfig`: immutable merged configuration consumed by the widget.

Current configuration flow:

```text
RuntimeConfig
  +
BackendConfig
  +
ThemeConfig
  +
Base GenericWidgetConfig
  ↓
buildWidgetConfig()
  ↓
Validate
  ↓
Freeze
  ↓
GenericWidgetWrapper
```

The existing backend demo now builds its current `GenericWidgetConfig` through `buildWidgetConfig()`, preserving the current visual behavior while introducing the new configuration architecture.

Step 1.3 deliberately does not move API calls, state management, or SDK logic yet. Those remain in later steps so each change stays small and verifiable.

## Step 1.4 Implementation Notes

Step 1.4 added the centralized widget state foundation.

New state modules:

```text
src/state/
  WidgetStateProvider.tsx
  index.ts
  selectors.ts
  useWidgetState.ts
  widgetActions.ts
  widgetReducer.ts
  widgetState.ts
```

The widget state is now modeled by domains:

- `ui`: open/closed, loading, menu, success banner, draft message, active panel.
- `session`: visitor ID, session ID, creation time, expiration placeholder.
- `conversation`: messages, pending message, request-in-flight flag.
- `consent`: accepted state, legal version, pending retry, consent error.
- `locale`: selected country and language.
- `connection`: online, reconnecting, backend health placeholder.
- `errors`: last error and warnings.
- `analytics`: opened timestamp and last event timestamp.

The state layer now includes:

- explicit reducer actions
- a reducer for all widget state transitions
- selectors so components do not need to depend on raw state shape
- a provider/hook foundation for future SDK and plugin integration

`GenericWidgetWrapper` now uses the centralized reducer for the global widget state it owns, while preserving the existing public props, callbacks, local storage behavior, consent flow, locale behavior, loading behavior, and message composer behavior.

This step intentionally does not extract the backend API layer yet. API communication remains in the backend demo until the event bus and API layer steps are completed.

## Step 1.5 Implementation Notes

Step 1.5 extracted backend communication from UI code into a dedicated API layer.

New API modules:

```text
src/api/
  apiInterceptor.ts
  chatApi.ts
  client.ts
  configApi.ts
  consentApi.ts
  envelope.ts
  errors.ts
  feedbackApi.ts
  healthApi.ts
  index.ts
  privacyApi.ts
```

The API layer now owns:

- the fetch wrapper
- request timeouts
- backend envelope parsing
- HTTP error handling
- network error handling
- timeout error handling
- correlation ID request headers
- future interceptor hooks
- endpoint-specific functions for chat, config, privacy, consent, feedback, and health

`BackendChatDemo.tsx` now uses API services instead of direct `fetch()` helpers:

- `loadConfig()`
- `loadPrivacy()`
- `submitConsent()`
- `sendMessage()`

The permanent rule after this step is:

```text
No widget UI component should call fetch() directly.
```

Verification confirmed the only remaining `fetch()` call under `src/` is inside:

```text
src/api/client.ts
```

This step reduced `BackendChatDemo.tsx` substantially and kept the existing backend-connected demo behavior intact.

## Step 1.6 Implementation Notes

Step 1.6 added the framework-independent widget event bus.

New event modules:

```text
src/events/
  eventBus.ts
  eventListeners.ts
  events.ts
  eventTypes.ts
  index.ts
```

The event bus now supports:

- `emit()`
- `subscribe()`
- `unsubscribe()`
- `once()`
- optional debug logging
- typed event payloads
- listener isolation so one failed listener does not break the widget

Centralized event categories include:

- widget lifecycle
- conversation
- consent
- locale
- session
- connection
- errors
- analytics

`GenericWidgetWrapper` now emits events for:

- widget initialized
- widget opened
- widget closed
- consent required
- consent accepted
- consent rejected
- country changed
- language changed
- message sent

`BackendChatDemo` now emits events for:

- backend connected
- backend disconnected
- API error
- chat started
- first message
- message received
- message failed
- message retried
- API-triggered consent required

The wrapper accepts an optional custom event bus and falls back to the shared `widgetEventBus`, which keeps the future SDK and plugin architecture straightforward.

This step preserves existing widget behavior while making future analytics, plugins, SDK callbacks, and integrations independent from React component internals.
