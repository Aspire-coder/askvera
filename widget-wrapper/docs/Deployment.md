# Deployment

## Build

```bash
npm run typecheck
npm run build
```

## Publishable Files

Deploy these files from `dist/` to the widget host:

```text
widget.min.js
widget.min.css
version.json
```

For module consumers, also publish:

```text
widget.es.js
types/
```

## Static Hosting

The widget can be hosted on S3, CloudFront, a CDN, or any static file host.

## Backend URL

Production should initialize with:

```ts
AskVera.init({
  apiUrl: "https://api.vera-api.xyz"
});
```

## Cache Strategy

Use long-lived cache headers for versioned assets. Keep `version.json` lightly cached so support teams can verify the deployed build.

