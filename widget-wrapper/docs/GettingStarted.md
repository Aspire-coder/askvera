# Getting Started

ASK Vera Widget is an embeddable assistant SDK. It can be used from a bundled JavaScript application or loaded directly on a website with a script tag.

## Install From Source

```bash
cd widget-wrapper
npm install
npm run build
```

The production artifacts are written to:

```text
dist/
```

## Run The Local Demo

```bash
npm run demo
```

Open:

```text
http://127.0.0.1:5174
```

## Use The SDK

```ts
import { AskVera } from "@askvera/widget";
import "@askvera/widget/styles.css";

await AskVera.init({
  apiUrl: "https://api.vera-api.xyz"
});

AskVera.open();
```

## Use A Script Tag

```html
<link rel="stylesheet" href="./widget.css" />
<script src="./widget.min.js"></script>
<script>
  window.AskVera.init({
    apiUrl: "https://api.vera-api.xyz"
  });
</script>
```

