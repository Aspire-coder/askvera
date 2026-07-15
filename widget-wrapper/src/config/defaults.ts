import type { RuntimeConfig } from "./runtimeConfig";

export const defaultRuntimeConfig: Readonly<RuntimeConfig> = Object.freeze({
  apiUrl: "https://api.vera-api.xyz",
  companyName: "AskVera",
  launcherPosition: "bottom-right",
  debug: false
});
