export type RenderedSource = {
  title?: string;
  uri?: string;
  excerpt?: string;
  page?: string;
  section?: string;
  sectionTitle?: string;
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
      section: typeof record.section === "string" ? record.section : undefined,
      sectionTitle: typeof record.sectionTitle === "string" ? record.sectionTitle : undefined,
    };
    if (normalized.title || normalized.uri) sources.push(normalized);
  });
  return sources;
}

function sourceTitle(source: RenderedSource, fallback: string): string {
  if (source.title) return source.title;
  if (!source.uri) return fallback;
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
  labels
}: {
  sources: unknown;
  labels?: WidgetCitationLabels;
}) {
  const normalized = normalizeSources(sources);
  if (!normalized.length) return null;
  const copy = labels || {
    references: "References", sourcesUsed: "Sources used for this answer",
    primarySource: "Primary source", supportingSource: "Supporting source",
    source: "Source", section: "Section"
  };

  return (
    <details className="gw-citations" aria-label={copy.references}>
      <summary className="gw-citations-title">{copy.sourcesUsed} ({normalized.length})</summary>
      <div className="gw-citation-list">
        {normalized.map((source, index) => {
          const title = sourceTitle(source, copy.source);
          const pageLabel = formatPage(source.page);
          return (
            <article key={`${title}-${index}`} className="gw-citation-card">
              <div className="gw-citation-heading">
                <span className="gw-citation-kind">{index === 0 ? copy.primarySource : copy.supportingSource}</span>
                <span className="gw-citation-document">{title}</span>
              </div>
              <div className="gw-citation-meta">
                {source.section ? <span className="gw-citation-section">{copy.section} {source.section}</span> : null}
                {pageLabel ? <span className="gw-citation-page">{pageLabel}</span> : null}
              </div>
              {source.sectionTitle ? <p>{source.sectionTitle}</p> : null}
              {source.excerpt ? <p>{source.excerpt}</p> : null}
            </article>
          );
        })}
      </div>
    </details>
  );
}
import type { WidgetCitationLabels } from "../generic-widget/types";
