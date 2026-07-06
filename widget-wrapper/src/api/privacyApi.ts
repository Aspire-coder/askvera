import type { ApiClient } from "./client";

export type LegalDocument = {
  id: string;
  title: string;
  required: boolean;
  html: string;
};

export type PrivacyResponseData = {
  version: string;
  documents: LegalDocument[];
};

export function loadPrivacy(client: ApiClient, country: string, language: string) {
  const path = `/api/privacy?country=${encodeURIComponent(country)}&lang=${encodeURIComponent(language)}`;
  return client.get<PrivacyResponseData>(path);
}
