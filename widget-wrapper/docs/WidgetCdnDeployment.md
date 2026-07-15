# ASK Vera Widget CDN Deployment

This guide explains how the production widget is built, uploaded, cached, and invalidated.

## Architecture

```text
Developer or GitHub Actions
  -> npm run deploy-widget
  -> Build widget.js and widget.css
  -> Validate dist artifacts
  -> Upload immutable version to S3
  -> Upload moving latest alias to S3
  -> Invalidate CloudFront latest path
```

## S3 Layout

Widget assets are stored under a dedicated prefix:

```text
s3://askvera-widget-assets/widget/latest/widget.js
s3://askvera-widget-assets/widget/latest/widget.css

s3://askvera-widget-assets/widget/v1.0.0/widget.js
s3://askvera-widget-assets/widget/v1.0.0/widget.css
```

The versioned folder is immutable. The deployment script refuses to overwrite an existing versioned release.

## Configuration

Deployment settings live in:

```text
widget-wrapper/deployment/widget.config.json
widget-wrapper/deployment/release.config.json
```

The release version is read from:

```text
widget-wrapper/package.json
```

## Local Deployment

From `widget-wrapper`:

```bash
npm run deploy-widget
```

For a safe verification without uploading or invalidating CloudFront:

```bash
npm run deploy-widget -- --dry-run
```

## Cache Policy

Latest assets use a short cache:

```text
Cache-Control: public,max-age=300
```

Versioned assets use long immutable caching:

```text
Cache-Control: public,max-age=31536000,immutable
```

Uploads explicitly set:

```text
widget.js  -> application/javascript
widget.css -> text/css
```

## CloudFront Invalidation

Only the latest alias is invalidated:

```text
/widget/latest/*
```

Versioned assets are never invalidated because they should never change.

## GitHub Actions

The deployment workflow is:

```text
.github/workflows/deploy-widget.yml
```

It runs on manual dispatch and published GitHub releases.

Required GitHub Secrets:

```text
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
AWS_REGION
```

Never commit AWS credentials.

## Rollback

Rollback is not automated yet. To roll back manually:

1. Copy the known-good versioned release back to `widget/latest/`.
2. Invalidate `/widget/latest/*`.
3. Verify `widget/latest/widget.js` and `widget/latest/widget.css` in CloudFront.

Future work can add:

```bash
npm run rollback-widget v1.0.0
```

## Troubleshooting

If deployment fails before upload:

- Confirm Node.js and npm are installed.
- Run `npm run build`.
- Run `npm run validate-widget`.

If deployment fails during AWS access:

- Confirm AWS CLI is installed.
- Confirm credentials are active.
- Confirm the target AWS account is correct.

If the widget does not update in the browser:

- Verify CloudFront invalidation was created.
- Check `Cache-Control` headers.
- Test the versioned URL and latest URL separately.

If browsers refuse to execute the asset:

- Verify `widget.js` is served as `application/javascript`.
- Verify `widget.css` is served as `text/css`.
