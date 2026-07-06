# Security

## Current Client-Side Controls

- Consent-first chat flow
- Session and visitor IDs isolated through the session manager
- API calls centralized in `src/api`
- Browser storage centralized in `src/storage`
- Public API exposed through the SDK

## Backend Controls Expected

The backend remains the authority for:

- CORS
- origin allowlists
- consent enforcement
- legal version validation
- rate limiting
- audit logging
- abuse prevention

## Future Hardening

Recommended before broad external rollout:

- widget IDs
- publishable keys
- server-side domain allowlists
- short-lived widget session tokens
- key rotation
- WAF rules
- stricter rate limits

Do not place private secrets in widget configuration. The widget runs in the browser and all client-side values are visible to users.

