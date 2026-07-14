import type { ApiClient } from "./client";

export type SourceDownloadResponseData = {
  url: string;
  filename: string;
};

export function getSourceDownload(client: ApiClient, uri: string) {
  return client.get<SourceDownloadResponseData>(`/api/source-download?uri=${encodeURIComponent(uri)}`);
}
