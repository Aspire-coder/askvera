import type { RuntimeConfig } from "./runtimeConfig";

// apiUrl has no real default - every real caller (AskVeraSdkImpl.init) already
// requires it and throws if it's missing. Leaving it empty here means a
// caller that skips that check fails loudly against an invalid URL instead
// of silently sending traffic to production.
export const defaultRuntimeConfig: Readonly<RuntimeConfig> = Object.freeze({
  apiUrl: "",
  companyName: "AskVera",
  launcherPosition: "bottom-right",
  debug: false
});
