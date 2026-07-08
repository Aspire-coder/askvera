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

export function CitationRenderer({ sources }: { sources: unknown }) {
  const normalized = normalizeSources(sources);
  if (!normalized.length) return null;

  return (
    <section className="gw-citations" aria-label="References">
      <div className="gw-citations-title">References</div>
      <div className="gw-citation-list">
        {normalized.map((source, index) => {
          const title = sourceTitle(source);
          const pageLabel = formatPage(source.page);
          return (
            <article key={`${title}-${index}`} className="gw-citation-card">
              {source.uri ? (
                <a href={source.uri} target="_blank" rel="noreferrer">
                  {title}
                </a>
              ) : (
                <span>{title}</span>
              )}
              {pageLabel ? <span className="gw-citation-page">{pageLabel}</span> : null}
              {source.excerpt ? <p>{source.excerpt}</p> : null}
            </article>
          );
        })}
      </div>
    </section>
  );
}
