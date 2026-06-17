import type { ReactNode } from "react";

import type { ChatSourceResponse } from "../../shared/api/types";
import { MessageCodeBlock } from "./components/MessageCodeBlock";

export type SourcePreview = {
  index: number;
  source: ChatSourceResponse;
  sessionId?: number | null;
};

function renderSourceRefTag(
  label: string,
  index: number,
  key: string,
  sources?: ChatSourceResponse[],
  onSelectSource?: (preview: SourcePreview) => void,
) {
  const source = sources?.[index - 1];
  const title = source
    ? `${source.source_title || source.file}\n${source.section_path || source.file}\n${source.content.slice(0, 120)}`
    : `来源 ${index}`;
  return (
    <button
      className="message-source-ref"
      disabled={!source}
      key={key}
      onClick={() => source ? onSelectSource?.({ index, source }) : undefined}
      title={title}
      type="button"
    >
      {label.includes("Doc") ? label : `[${index}]`}
    </button>
  );
}

function renderInlineMarkdown(
  text: string,
  keyPrefix: string,
  sources?: ChatSourceResponse[],
  onSelectSource?: (preview: SourcePreview) => void,
): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`|\[\[[^\]]+\]\]|[（(]\s*来源\s*\d+\s*[）)]|来源\s*\d+)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }
    const token = match[0];
    if (token.startsWith("**")) {
      nodes.push(<strong key={`${keyPrefix}-strong-${match.index}`}>{token.slice(2, -2)}</strong>);
    } else if (token.startsWith("`")) {
      nodes.push(<code className="message-inline-code" key={`${keyPrefix}-code-${match.index}`}>{token.slice(1, -1)}</code>);
    } else if (/来源\s*\d+/.test(token)) {
      const sourceIndex = Number(token.match(/\d+/)?.[0] ?? "0");
      nodes.push(renderSourceRefTag(`[${sourceIndex}]`, sourceIndex, `${keyPrefix}-source-${match.index}`, sources, onSelectSource));
    } else {
      nodes.push(<span className="message-wikilink" key={`${keyPrefix}-wiki-${match.index}`}>{token}</span>);
    }
    lastIndex = match.index + token.length;
  }
  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }
  return nodes;
}

function isMarkdownTable(lines: string[]) {
  return lines.length >= 2 && lines[0].includes("|") && /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(lines[1]);
}

function renderMarkdownTable(
  lines: string[],
  key: string,
  sources?: ChatSourceResponse[],
  onSelectSource?: (preview: SourcePreview) => void,
) {
  const parseRow = (line: string) => line.replace(/^\s*\|/, "").replace(/\|\s*$/, "").split("|").map((cell) => cell.trim());
  const headers = parseRow(lines[0]);
  const rows = lines.slice(2).filter((line) => line.includes("|")).map(parseRow);
  return (
    <div className="message-table-wrap" key={key}>
      <table className="message-table">
        <thead>
          <tr>{headers.map((header, index) => <th key={`${key}-h-${index}`}>{renderInlineMarkdown(header, `${key}-h-${index}`, sources, onSelectSource)}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={`${key}-r-${rowIndex}`}>
              {row.map((cell, cellIndex) => <td key={`${key}-r-${rowIndex}-${cellIndex}`}>{renderInlineMarkdown(cell, `${key}-r-${rowIndex}-${cellIndex}`, sources, onSelectSource)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function renderMarkdownText(
  text: string,
  keyPrefix: string,
  sources?: ChatSourceResponse[],
  onSelectSource?: (preview: SourcePreview) => void,
) {
  const blocks = text.split(/\n{2,}/g).filter((block) => block.trim().length > 0);
  return blocks.map((block, blockIndex) => {
    const key = `${keyPrefix}-block-${blockIndex}`;
    const lines = block.split("\n").filter((line) => line.trim().length > 0);
    const firstLine = lines[0]?.trim() ?? "";

    if (isMarkdownTable(lines)) {
      return renderMarkdownTable(lines, key, sources, onSelectSource);
    }
    if (lines.every((line) => /^\s*-{3,}\s*$/.test(line))) {
      return <hr className="message-divider" key={key} />;
    }
    if (/^#{1,4}\s+/.test(firstLine)) {
      const level = Math.min(4, firstLine.match(/^#+/)?.[0].length ?? 3);
      const headingContent = renderInlineMarkdown(firstLine.replace(/^#{1,4}\s+/, ""), key, sources, onSelectSource);
      if (level === 1) return <h1 className="message-heading" key={key}>{headingContent}</h1>;
      if (level === 2) return <h2 className="message-heading" key={key}>{headingContent}</h2>;
      if (level === 3) return <h3 className="message-heading" key={key}>{headingContent}</h3>;
      return <h4 className="message-heading" key={key}>{headingContent}</h4>;
    }
    if (lines.every((line) => /^\s*[-*]\s+/.test(line))) {
      return (
        <ul className="message-list" key={key}>
          {lines.map((line, index) => <li key={`${key}-${index}`}>{renderInlineMarkdown(line.replace(/^\s*[-*]\s+/, ""), `${key}-${index}`, sources, onSelectSource)}</li>)}
        </ul>
      );
    }
    if (lines.every((line) => /^\s*\d+\.\s+/.test(line))) {
      return (
        <ol className="message-list" key={key}>
          {lines.map((line, index) => <li key={`${key}-${index}`}>{renderInlineMarkdown(line.replace(/^\s*\d+\.\s+/, ""), `${key}-${index}`, sources, onSelectSource)}</li>)}
        </ol>
      );
    }
    if (lines.every((line) => /^\s*>\s?/.test(line))) {
      return <blockquote className="message-quote" key={key}>{lines.map((line, index) => <p key={`${key}-${index}`}>{renderInlineMarkdown(line.replace(/^\s*>\s?/, ""), `${key}-${index}`, sources, onSelectSource)}</p>)}</blockquote>;
    }
    return (
      <p className="message-paragraph" key={key}>
        {lines.map((line, index) => (
          <span key={`${key}-${index}`}>
            {renderInlineMarkdown(line, `${key}-${index}`, sources, onSelectSource)}
            {index < lines.length - 1 ? <br /> : null}
          </span>
        ))}
      </p>
    );
  });
}

export function renderMessageContent(
  content: string,
  sources?: ChatSourceResponse[],
  onSelectSource?: (preview: SourcePreview) => void,
) {
  const nodes: ReactNode[] = [];
  const pattern = /```([A-Za-z0-9_-]+)?\n?([\s\S]*?)```/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let index = 0;
  while ((match = pattern.exec(content)) !== null) {
    const before = content.slice(lastIndex, match.index);
    if (before.trim()) {
      nodes.push(...renderMarkdownText(before, `text-${index}`, sources, onSelectSource));
    }
    const language = match[1]?.trim();
    const code = match[2].trim();
    nodes.push(
      <MessageCodeBlock code={code} key={`code-${index}`} language={language} />,
    );
    lastIndex = pattern.lastIndex;
    index += 1;
  }
  const rest = content.slice(lastIndex);
  if (rest.trim()) {
    nodes.push(...renderMarkdownText(rest, `text-${index}`, sources, onSelectSource));
  }
  return nodes;
}
