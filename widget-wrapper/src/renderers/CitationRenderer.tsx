export type RenderedSource = {
  title?: string;
  uri?: string;
  excerpt?: string;
  page?: string;
};

function normalizeSources(value: unknown): RenderedSource[] {
  if (!Array.isArray(value)) return [];
  const sources: RenderedSource[] = [];
  value.forEach((source) => {
    if (!source || typeof source !== "object") return;
    const record = source as Record<string, unknown>;
    const normalized = {
      title: typeof record.title === "string" ? record.title : undefined,
      uri: typeof record.uri === "string" ? record.uri : undefined,
      excerpt: typeof record.excerpt === "string" ? record.excerpt : undefined,
      page: typeof record.page === "string" ? record.page : typeof record.page === "number" ? String(record.page) : undefined,
    };
    if (normalized.title || normalized.uri) sources.push(normalized);
  });
  return sources;
}

function sourceTitle(source: RenderedSource): string {
  if (source.title) return source.title;
  if (!source.uri) return "Source";
  try {
    return decodeURIComponent(new URL(source.uri).pathname.split("/").filter(Boolean).pop() || source.uri);
  } catch {
    return source.uri;
  }
}

function formatPage(page?: string): string | null {
  if (!page) return null;
  const trimmed = page.endsWith(".0") ? page.slice(0, -2) : page;
  return `p. ${trimmed}`;
}

export function CitationRenderer({
  sources,
  onDownloadSource
}: {
  sources: unknown;
  onDownloadSource?: (source: RenderedSource) => void | Promise<void>;
}) {
  const normalized = normalizeSources(sources);
  if (!normalized.length) return null;

  return (
    <details className="gw-citations" aria-label="References">
      <summary className="gw-citations-title">Sources used for this answer ({normalized.length})</summary>
      <div className="gw-citation-list">
        {normalized.map((source, index) => {
          const title = sourceTitle(source);
          const pageLabel = formatPage(source.page);
          const canDownload = Boolean(source.uri?.startsWith("s3://"));
          return (
            <article key={`${title}-${index}`} className="gw-citation-card">
              <div className="gw-citation-heading">
                <span className="gw-citation-kind">{index === 0 ? "Primary source" : "Supporting source"}</span>
                <span className="gw-citation-document">{title}</span>
              </div>
              <div className="gw-citation-meta">
                {pageLabel ? <span className="gw-citation-page">{pageLabel}</span> : null}
                {canDownload && onDownloadSource ? (
                  <button type="button" className="gw-citation-download" onClick={() => void onDownloadSource(source)}>
                    Download PDF
                  </button>
                ) : null}
              </div>
              {source.excerpt ? <p>{source.excerpt}</p> : null}
            </article>
          );
        })}
      </div>
    </details>
  );
}
