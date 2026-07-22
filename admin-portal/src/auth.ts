export type AuthSession = {
  accessToken: string;
  expiresAt: number;
  username: string;
};

const domain = (import.meta.env.VITE_COGNITO_DOMAIN as string | undefined)?.replace(/\/$/, "") || "";
const clientId = (import.meta.env.VITE_COGNITO_CLIENT_ID as string | undefined) || "";
const redirectUri = (import.meta.env.VITE_COGNITO_REDIRECT_URI as string | undefined) || `${window.location.origin}${window.location.pathname}`;
const logoutUri = (import.meta.env.VITE_COGNITO_LOGOUT_URI as string | undefined) || `${window.location.origin}${window.location.pathname}`;
const sessionKey = "askvera_admin_session";
const stateKey = "askvera_admin_oauth_state";
const verifierKey = "askvera_admin_pkce_verifier";

export const cognitoConfigured = Boolean(domain && clientId);
export const demoAllowed = import.meta.env.DEV || import.meta.env.VITE_ALLOW_DEMO === "true";

const base64Url = (bytes: Uint8Array) => btoa(String.fromCharCode(...bytes))
  .replaceAll("+", "-")
  .replaceAll("/", "_")
  .replace(/=+$/, "");

const randomValue = (size = 48) => {
  const bytes = new Uint8Array(size);
  crypto.getRandomValues(bytes);
  return base64Url(bytes);
};

const challengeFor = async (verifier: string) => {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
  return base64Url(new Uint8Array(digest));
};

const tokenClaims = (token: string): Record<string, unknown> => {
  try {
    const payload = token.split(".")[1].replaceAll("-", "+").replaceAll("_", "/");
    return JSON.parse(atob(payload.padEnd(Math.ceil(payload.length / 4) * 4, "="))) as Record<string, unknown>;
  } catch {
    return {};
  }
};

export function getSession(): AuthSession | null {
  const raw = window.sessionStorage.getItem(sessionKey);
  if (!raw) return null;
  try {
    const session = JSON.parse(raw) as AuthSession;
    if (!session.accessToken || session.expiresAt <= Date.now() + 30_000) {
      window.sessionStorage.removeItem(sessionKey);
      return null;
    }
    return session;
  } catch {
    window.sessionStorage.removeItem(sessionKey);
    return null;
  }
}

export async function beginSignIn(): Promise<void> {
  if (!cognitoConfigured) throw new Error("Cognito sign-in is not configured.");
  const verifier = randomValue();
  const state = randomValue(24);
  window.sessionStorage.setItem(verifierKey, verifier);
  window.sessionStorage.setItem(stateKey, state);
  const query = new URLSearchParams({
    client_id: clientId,
    response_type: "code",
    scope: "openid email profile",
    redirect_uri: redirectUri,
    state,
    code_challenge_method: "S256",
    code_challenge: await challengeFor(verifier),
  });
  window.location.assign(`${domain}/oauth2/authorize?${query}`);
}

export async function completeSignIn(): Promise<AuthSession | null> {
  const query = new URLSearchParams(window.location.search);
  const code = query.get("code");
  if (!code) return getSession();
  const expectedState = window.sessionStorage.getItem(stateKey);
  const verifier = window.sessionStorage.getItem(verifierKey);
  if (!expectedState || query.get("state") !== expectedState || !verifier) {
    throw new Error("The sign-in response could not be verified.");
  }
  const response = await fetch(`${domain}/oauth2/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "authorization_code",
      client_id: clientId,
      code,
      redirect_uri: redirectUri,
      code_verifier: verifier,
    }),
  });
  if (!response.ok) throw new Error("Administrator sign-in could not be completed.");
  const tokens = await response.json() as { access_token: string; expires_in: number };
  const claims = tokenClaims(tokens.access_token);
  const session: AuthSession = {
    accessToken: tokens.access_token,
    expiresAt: Date.now() + Number(tokens.expires_in || 3600) * 1000,
    username: String(claims.username || claims["cognito:username"] || "Administrator"),
  };
  window.sessionStorage.setItem(sessionKey, JSON.stringify(session));
  window.sessionStorage.removeItem(stateKey);
  window.sessionStorage.removeItem(verifierKey);
  window.history.replaceState({}, document.title, window.location.pathname);
  return session;
}

export function signOut(): void {
  window.sessionStorage.removeItem(sessionKey);
  window.sessionStorage.removeItem("askvera_admin_key");
  if (!cognitoConfigured) {
    window.location.reload();
    return;
  }
  const query = new URLSearchParams({ client_id: clientId, logout_uri: logoutUri });
  window.location.assign(`${domain}/logout?${query}`);
}
