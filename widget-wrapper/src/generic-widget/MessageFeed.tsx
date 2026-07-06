import type { ReactNode } from "react";
import type { GenericWidgetConfig, GenericWidgetRenderState, WidgetMessage } from "./types";

type MessageRole = WidgetMessage["role"];

function normalizeMessageContent(content: string): string {
  return content
    .replace(/\r\n/g, "\n")
    .replace(/([^\n])\s+(#{1,3}\s+)/g, "$1\n\n$2")
    .replace(/\s+-\s+(?=(?:\*\*)?[A-Z0-9])/g, "\n- ");
}

function renderInlineMarkdown(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = /(`([^`]+)`)|(\*\*(.+?)\*\*)|(\[([^\]]+)\]\((https?:\/\/[^)\s]+)\))/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) nodes.push(text.slice(lastIndex, match.index));
    if (match[2]) {
      nodes.push(<code key={`code-${match.index}`}>{match[2]}</code>);
    } else if (match[4]) {
      nodes.push(<strong key={`strong-${match.index}`}>{match[4]}</strong>);
    } else if (match[6] && match[7]) {
      nodes.push(
        <a key={`link-${match.index}`} href={match[7]} target="_blank" rel="noreferrer">
          {match[6]}
        </a>
      );
    }
    lastIndex = pattern.lastIndex;
  }

  if (lastIndex < text.length) nodes.push(text.slice(lastIndex));
  return nodes;
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

function renderTable(headerLine: string, rowLines: string[], key: string): ReactNode {
  const headers = parseTableCells(headerLine);
  const rows = rowLines.map(parseTableCells);

  return (
    <div className="gw-message-table-wrap" key={key}>
      <table className="gw-message-table">
        <thead>
          <tr>
            {headers.map((header, index) => (
              <th key={`${header}-${index}`}>{renderInlineMarkdown(header)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
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

function renderMessageContent(content: string): ReactNode {
  const lines = normalizeMessageContent(content).split("\n");
  const blocks: ReactNode[] = [];
  let paragraph: string[] = [];
  let listItems: string[] = [];
  let orderedItems: string[] = [];

  const flushParagraph = () => {
    if (!paragraph.length) return;
    const text = paragraph.join(" ").trim();
    if (text) blocks.push(<p key={`p-${blocks.length}`}>{renderInlineMarkdown(text)}</p>);
    paragraph = [];
  };

  const flushList = () => {
    if (!listItems.length) return;
    blocks.push(
      <ul key={`ul-${blocks.length}`}>
        {listItems.map((item, index) => (
          <li key={`${item}-${index}`}>{renderInlineMarkdown(item)}</li>
        ))}
      </ul>
    );
    listItems = [];
  };

  const flushOrderedList = () => {
    if (!orderedItems.length) return;
    blocks.push(
      <ol key={`ol-${blocks.length}`}>
        {orderedItems.map((item, index) => (
          <li key={`${item}-${index}`}>{renderInlineMarkdown(item)}</li>
        ))}
      </ol>
    );
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

    const codeFence = /^```(\w+)?$/.exec(line);
    if (codeFence) {
      flushAll();
      const codeLines: string[] = [];
      index += 1;
      while (index < lines.length && !/^```$/.test(lines[index].trim())) {
        codeLines.push(lines[index]);
        index += 1;
      }
      blocks.push(
        <pre key={`codeblock-${blocks.length}`}>
          <code>{codeLines.join("\n")}</code>
        </pre>
      );
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
      blocks.push(renderTable(line, rowLines, `table-${blocks.length}`));
      continue;
    }

    const heading = /^(#{1,3})\s+(.+)$/.exec(line);
    if (heading) {
      flushAll();
      const level = heading[1].length;
      const Tag = level === 1 ? "h3" : level === 2 ? "h4" : "h5";
      blocks.push(<Tag key={`h-${blocks.length}`}>{renderInlineMarkdown(heading[2])}</Tag>);
      continue;
    }

    const quote = /^>\s+(.+)$/.exec(line);
    if (quote) {
      flushAll();
      blocks.push(<blockquote key={`quote-${blocks.length}`}>{renderInlineMarkdown(quote[1])}</blockquote>);
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

  return blocks.length ? blocks : <p>{content}</p>;
}

function formatMessageTimestamp(timestamp?: string): string {
  if (!timestamp) return "Now";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return timestamp;
  return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function roleLabel(role: MessageRole, config: GenericWidgetConfig): string {
  if (role === "assistant") return config.assistantName || config.brandName;
  if (role === "user") return "You";
  return "System";
}

function assistantMark(config: GenericWidgetConfig): string {
  const label = config.assistantName || config.brandName;
  return label.trim().slice(0, 1) || "A";
}

function MessageActions() {
  return (
    <div className="gw-message-actions" aria-hidden="true">
      <span className="gw-message-action">Copy</span>
      <span className="gw-message-action">Helpful</span>
      <span className="gw-message-action">Not helpful</span>
    </div>
  );
}

function MessageCard({ message, config }: { message: WidgetMessage; config: GenericWidgetConfig }) {
  const isAssistant = message.role === "assistant";
  const isSystem = message.role === "system";
  const label = roleLabel(message.role, config);
  const content =
    typeof message.content === "string" && (isAssistant || isSystem)
      ? renderMessageContent(message.content)
      : message.content;

  return (
    <article className={`gw-message gw-message-${message.role}`}>
      <div className="gw-message-avatar" aria-hidden="true">
        {isAssistant ? assistantMark(config) : message.role === "user" ? "Y" : "i"}
      </div>
      <div className="gw-message-card">
        <header className="gw-message-meta">
          <span className="gw-message-author">{label}</span>
          <time>{formatMessageTimestamp(message.timestamp)}</time>
        </header>
        <div className="gw-message-body">{content}</div>
        {isAssistant ? <MessageActions /> : null}
      </div>
    </article>
  );
}

export function MessageFeed({
  config,
  messages,
  state,
  renderMessages
}: {
  config: GenericWidgetConfig;
  messages: WidgetMessage[];
  state: GenericWidgetRenderState;
  renderMessages?: (messages: WidgetMessage[], state: GenericWidgetRenderState) => ReactNode;
}) {
  if (renderMessages) return <div className="gw-message-feed">{renderMessages(messages, state)}</div>;

  return (
    <div className="gw-message-feed" role="log" aria-live="polite">
      {config.welcomeText ? (
        <MessageCard message={{ id: "gw-welcome-message", role: "system", content: config.welcomeText }} config={config} />
      ) : null}
      {messages.map((message) => (
        <MessageCard key={message.id} message={message} config={config} />
      ))}
    </div>
  );
}
