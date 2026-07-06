# Installation

## Package Entry Points

The widget package is named:

```text
@askvera/widget
```

Package outputs:

```text
dist/widget.es.js
dist/widget.js
dist/widget.min.js
dist/widget.css
dist/widget.min.css
dist/types/
```

## Bundled App

```ts
import { AskVera } from "@askvera/widget";
import "@askvera/widget/styles.css";
```

## Plain Website

```html
<link rel="stylesheet" href="/askvera/widget.min.css" />
<script src="/askvera/widget.min.js"></script>
```

## Required Configuration

At minimum, provide the backend API URL:

```ts
AskVera.init({
  apiUrl: "https://api.vera-api.xyz"
});
```

## Build Verification

Before publishing or deploying the widget:

```bash
npm run typecheck
npm run build
```

