# Configuration

The widget configuration is split by responsibility.

## Runtime Config

Runtime config is passed by the host website.

Common fields:

```ts
{
  apiUrl: "https://api.vera-api.xyz",
  companyName: "Forever",
  logo: "/logo.svg",
  accentColor: "#ffc400",
  launcherPosition: "bottom-right",
  width: 420,
  height: 680,
  defaultCountry: "US",
  defaultLanguage: "en",
  debug: false
}
```

## Backend Config

Backend config is loaded from the API and includes dynamic market, language, legal, and topic data. UI components should not read static country or legal files directly.

## Theme Config

Theme config controls visual tokens such as colors, spacing, radius, typography, shadows, and animation.

## Feature Flags

Current feature flags:

```ts
{
  streaming: false,
  markdown: true,
  feedback: true,
  typingIndicator: true,
  darkMode: true,
  citations: false,
  attachments: false,
  analytics: true
}
```

## Configuration Flow

```text
AskVera.init()
  -> RuntimeConfig
  -> BackendConfig
  -> ThemeConfig
  -> validate
  -> freeze
  -> WidgetConfig
```

