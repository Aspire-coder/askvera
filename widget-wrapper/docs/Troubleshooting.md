# Troubleshooting

## Widget Does Not Appear

Check:

- CSS file is loaded.
- `AskVera.init()` is called.
- `mountTarget` exists if provided.
- Browser console has no script loading errors.

## API Requests Fail

Check:

- `apiUrl` is correct.
- Backend CORS allows the current origin.
- Backend `/health` is reachable.
- Network tab shows the expected request URL.

## Consent Appears Repeatedly

Check:

- Legal version from `/api/privacy`.
- Session metadata in browser storage.
- Backend consent response.
- Whether the user changed market or language.

## Markets Or Languages Are Missing

Check:

- `/api/config` response.
- Disabled markets or languages.
- Default country and language values.

## Debug Build Info

```ts
console.log(AskVera.getBuildInfo());
```

Use this when comparing the browser bundle to a deployed release.

