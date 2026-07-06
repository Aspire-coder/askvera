import type { ApiClient } from "./client";

export type ApiLanguage = {
  code: string;
  name: string;
};

export type ApiCountry = {
  code: string;
  name: string;
  languages: ApiLanguage[];
};

export type ConfigResponseData = {
  countries: ApiCountry[];
  privacyVersion: string;
};

export function loadConfig(client: ApiClient) {
  return client.get<ConfigResponseData>("/api/config");
}
