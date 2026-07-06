import type { ReactNode } from "react";

type RenderBlock = {
  type: "paragraph" | "unordered" | "ordered" | "table" | "heading" | "quote" | "code" | "hr" | "callout" | "directory";
  content?: string;
  items?: string[];
  header?: string;
  rows?: string[];
  level?: number;
  variant?: "policy" | "compliance" | "notice";
  fields?: Array<{ label: string; value: string; href?: string }>;
};

const CALLOUT_HEADINGS = new Map([
  ["policy update", "policy" as const],
  ["compliance notice", "compliance" as const],
  ["important notice", "notice" as const],
  ["notice", "notice" as const]
]);

const DIRECTORY_LABELS = [
  { label: "Address", pattern: /^(address|location)\s*:\s*(.+)$/i },
  { label: "Phone", pattern: /^(phone|tel|telephone)\s*:\s*(.+)$/i },
  { label: "Email", pattern: /^(email|e-mail)\s*:\s*(.+)$/i },
  { label: "Website", pattern: /^(website|site|url)\s*:\s*(.+)$/i },
  { label: "Hours", pattern: /^(hours|office hours)\s*:\s*(.+)$/i }
];

function normalizeMessageContent(content: string): string {
  return content
    .replace(/\r\n/g, "\n")
    .replace(/([^\n])\s+(#{1,3}\s+)/g, "$1\n\n$2")
    .replace(/\s+-\s+(?=(?:\*\*)?[A-Z0-9])/g, "\n- ");
}

function renderInlineMarkdown(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = /(`([^`]+)`)|(\*\*(.+?)\*\*)|(\*([^*]+)\*)|(\[([^\]]+)\]\((https?:\/\/[^)\s]+)\))|(https?:\/\/[^\s)]+)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) nodes.push(text.slice(lastIndex, match.index));
    if (match[2]) {
      nodes.push(<code key={`code-${match.index}`}>{match[2]}</code>);
    } else if (match[4]) {
      nodes.push(<strong key={`strong-${match.index}`}>{match[4]}</strong>);
    } else if (match[6]) {
      nodes.push(<em key={`em-${match.index}`}>{match[6]}</em>);
    } else if (match[8] && match[9]) {
      nodes.push(
        <a key={`link-${match.index}`} href={match[9]} target="_blank" rel="noreferrer">
          {match[8]}
        </a>
      );
    } else if (match[10]) {
      nodes.push(
        <a key={`url-${match.index}`} href={match[10]} target="_blank" rel="noreferrer">
          {friendlyLinkLabel(match[10])}
        </a>
      );
    }
    lastIndex = pattern.lastIndex;
  }

  if (lastIndex < text.length) nodes.push(text.slice(lastIndex));
  return nodes;
}

function friendlyLinkLabel(url: string): string {
  try {
    const parsed = new URL(url);
    const fileName = decodeURIComponent(parsed.pathname.split("/").filter(Boolean).pop() || parsed.hostname);
    if (/\.pdf$/i.test(fileName)) return `${fileName.replace(/\.pdf$/i, "")} PDF`;
    return fileName || parsed.hostname;
  } catch {
    return url;
  }
}

function parseTableCells(line: string): string[] {
  return line
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

function isTableSeparator(line: string): boolean {
  return /^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$/.test(line.trim());
}

function parseDirectoryField(line: string) {
  const normalized = line.replace(/^[-*]\s+/, "").trim();
  for (const option of DIRECTORY_LABELS) {
    const match = option.pattern.exec(normalized);
    if (!match) continue;
    const value = match[2].trim();
    const href = option.label === "Email" ? `mailto:${value}` : option.label === "Phone" ? `tel:${value.replace(/[^\d+]/g, "")}` : /^https?:\/\//i.test(value) ? value : undefined;
    return { label: option.label, value, href };
  }
  return null;
}

function parseBlocks(content: string): RenderBlock[] {
  const lines = normalizeMessageContent(content).split("\n");
  const blocks: RenderBlock[] = [];
  let paragraph: string[] = [];
  let listItems: string[] = [];
  let orderedItems: string[] = [];

  const flushParagraph = () => {
    if (!paragraph.length) return;
    const text = paragraph.join(" ").trim();
    if (text) blocks.push({ type: "paragraph", content: text });
    paragraph = [];
  };

  const flushList = () => {
    if (!listItems.length) return;
    blocks.push({ type: "unordered", items: listItems });
    listItems = [];
  };

  const flushOrderedList = () => {
    if (!orderedItems.length) return;
    blocks.push({ type: "ordered", items: orderedItems });
    orderedItems = [];
  };

  const flushAll = () => {
    flushParagraph();
    flushList();
    flushOrderedList();
  };

  for (let index = 0; index < lines.length; index += 1) {
    const rawLine = lines[index];
    const line = rawLine.trim();

    if (!line) {
      flushAll();
      continue;
    }

    if (/^(-{3,}|\*{3,}|_{3,})$/.test(line)) {
      flushAll();
      blocks.push({ type: "hr" });
      continue;
    }

    const codeFence = /^```(\w+)?$/.exec(line);
    if (codeFence) {
      flushAll();
      const codeLines: string[] = [];
      index += 1;
      while (index < lines.length && !/^```$/.test(lines[index].trim())) {
        codeLines.push(lines[index]);
        index += 1;
      }
      blocks.push({ type: "code", content: codeLines.join("\n") });
      continue;
    }

    if (index + 1 < lines.length && line.includes("|") && isTableSeparator(lines[index + 1])) {
      flushAll();
      index += 2;
      const rowLines: string[] = [];
      while (index < lines.length && lines[index].includes("|") && lines[index].trim()) {
        rowLines.push(lines[index]);
        index += 1;
      }
      index -= 1;
      blocks.push({ type: "table", header: line, rows: rowLines });
      continue;
    }

    const heading = /^(#{1,3})\s+(.+)$/.exec(line);
    if (heading) {
      flushAll();
      const title = heading[2].trim();
      const variant = CALLOUT_HEADINGS.get(title.toLowerCase());
      if (variant) {
        const body: string[] = [];
        index += 1;
        while (index < lines.length && lines[index].trim() && !/^#{1,3}\s+/.test(lines[index].trim())) {
          body.push(lines[index].trim());
          index += 1;
        }
        index -= 1;
        blocks.push({ type: "callout", variant, header: title, content: body.join(" ") });
      } else if (/office|directory|contact/i.test(title)) {
        const fields: Array<{ label: string; value: string; href?: string }> = [];
        index += 1;
        while (index < lines.length && lines[index].trim() && !/^#{1,3}\s+/.test(lines[index].trim())) {
          const field = parseDirectoryField(lines[index].trim());
          if (field) fields.push(field);
          index += 1;
        }
        index -= 1;
        if (fields.length) blocks.push({ type: "directory", header: title, fields });
        else blocks.push({ type: "heading", level: heading[1].length, content: title });
      } else {
        blocks.push({ type: "heading", level: heading[1].length, content: title });
      }
      continue;
    }

    const plainCallout = /^(Policy Update|Compliance Notice|Important Notice|Notice)\s*:?\s*$/i.exec(line);
    if (plainCallout) {
      flushAll();
      const title = plainCallout[1];
      const variant = CALLOUT_HEADINGS.get(title.toLowerCase()) || "notice";
      const body: string[] = [];
      index += 1;
      while (index < lines.length && lines[index].trim() && !/^(Policy Update|Compliance Notice|Important Notice|Notice)\s*:?\s*$/i.test(lines[index].trim())) {
        body.push(lines[index].trim());
        index += 1;
      }
      index -= 1;
      blocks.push({ type: "callout", variant, header: title, content: body.join(" ") });
      continue;
    }

    const quote = /^>\s+(.+)$/.exec(line);
    if (quote) {
      flushAll();
      blocks.push({ type: "quote", content: quote[1] });
      continue;
    }

    const bullet = /^[-*]\s+(.+)$/.exec(line);
    if (bullet) {
      flushParagraph();
      flushOrderedList();
      listItems.push(bullet[1]);
      continue;
    }

    const ordered = /^\d+\.\s+(.+)$/.exec(line);
    if (ordered) {
      flushParagraph();
      flushList();
      orderedItems.push(ordered[1]);
      continue;
    }

    flushList();
    flushOrderedList();
    paragraph.push(line);
  }

  flushAll();
  return blocks;
}

function TableRenderer({ header, rows }: { header: string; rows: string[] }) {
  const headers = parseTableCells(header);
  const parsedRows = rows.map(parseTableCells);

  return (
    <div className="gw-message-table-wrap">
      <table className="gw-message-table">
        <thead>
          <tr>
            {headers.map((headerCell, index) => (
              <th key={`${headerCell}-${index}`}>{renderInlineMarkdown(headerCell)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {parsedRows.map((row, rowIndex) => (
            <tr key={`row-${rowIndex}`}>
              {headers.map((_, cellIndex) => (
                <td key={`cell-${rowIndex}-${cellIndex}`}>{renderInlineMarkdown(row[cellIndex] || "")}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CalloutRenderer({ block }: { block: RenderBlock }) {
  return (
    <aside className={`gw-rich-callout gw-rich-callout-${block.variant || "notice"}`}>
      <strong>{block.header}</strong>
      {block.content ? <p>{renderInlineMarkdown(block.content)}</p> : null}
    </aside>
  );
}

function DirectoryCardRenderer({ block }: { block: RenderBlock }) {
  return (
    <section className="gw-directory-card">
      <h4>{block.header}</h4>
      <dl>
        {(block.fields || []).map((field) => (
          <div key={`${field.label}-${field.value}`} className="gw-directory-row">
            <dt>{field.label}</dt>
            <dd>{field.href ? <a href={field.href}>{field.value}</a> : field.value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function renderBlock(block: RenderBlock, index: number): ReactNode {
  switch (block.type) {
    case "heading": {
      const Tag = block.level === 1 ? "h3" : block.level === 2 ? "h4" : "h5";
      return <Tag key={`h-${index}`}>{renderInlineMarkdown(block.content || "")}</Tag>;
    }
    case "unordered":
      return (
        <ul key={`ul-${index}`}>
          {(block.items || []).map((item, itemIndex) => (
            <li key={`${item}-${itemIndex}`}>{renderInlineMarkdown(item)}</li>
          ))}
        </ul>
      );
    case "ordered":
      return (
        <ol key={`ol-${index}`}>
          {(block.items || []).map((item, itemIndex) => (
            <li key={`${item}-${itemIndex}`}>{renderInlineMarkdown(item)}</li>
          ))}
        </ol>
      );
    case "table":
      return <TableRenderer key={`table-${index}`} header={block.header || ""} rows={block.rows || []} />;
    case "quote":
      return <blockquote key={`quote-${index}`}>{renderInlineMarkdown(block.content || "")}</blockquote>;
    case "code":
      return (
        <pre key={`codeblock-${index}`}>
          <code>{block.content}</code>
        </pre>
      );
    case "hr":
      return <hr key={`hr-${index}`} className="gw-rich-divider" />;
    case "callout":
      return <CalloutRenderer key={`callout-${index}`} block={block} />;
    case "directory":
      return <DirectoryCardRenderer key={`directory-${index}`} block={block} />;
    default:
      return <p key={`p-${index}`}>{renderInlineMarkdown(block.content || "")}</p>;
  }
}

export function MarkdownRenderer({ content }: { content: string }) {
  const blocks = parseBlocks(content);
  if (!blocks.length) return <p>{content}</p>;
  return <>{blocks.map(renderBlock)}</>;
}
