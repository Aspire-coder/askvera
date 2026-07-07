export type RenderedSource = {
  title?: string;
  uri?: string;
  excerpt?: string;
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
        excerpt: typeof record.excerpt === "string" ? record.excerpt : undefined
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

export function CitationRenderer({ sources }: { sources: unknown }) {
  const normalized = normalizeSources(sources);
  if (!normalized.length) return null;

  return (
    <section className="gw-citations" aria-label="References">
      <div className="gw-citations-title">References</div>
      <div className="gw-citation-list">
        {normalized.map((source, index) => {
          const title = sourceTitle(source);
          return (
            <article key={`${title}-${index}`} className="gw-citation-card">
              {source.uri ? (
                <a href={source.uri} target="_blank" rel="noreferrer">
                  {title}
                </a>
              ) : (
                <span>{title}</span>
              )}
              {source.excerpt ? <p>{source.excerpt}</p> : null}
            </article>
          );
        })}
      </div>
    </section>
  );
}
