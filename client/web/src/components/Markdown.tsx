import type { ReactNode } from "react";

/**
 * Lightweight Markdown renderer for LLM responses.
 *
 * Handles the subset of Markdown that the recommendation LLM actually emits:
 * headings (#..######), ordered/unordered lists, **bold**, and `inline code`.
 * Intentionally dependency-free — no react-markdown / remark in the bundle.
 * All text is rendered through React (escaped), so there is no XSS surface.
 */

type Block =
  | { type: "heading"; level: number; text: string }
  | { type: "ul"; items: string[] }
  | { type: "ol"; items: string[] }
  | { type: "p"; text: string };

const HEADING_RE = /^(#{1,6})\s+(.*)$/;
const ORDERED_RE = /^\s*\d+\.\s+(.*)$/;
const UNORDERED_RE = /^\s*[-*]\s+(.*)$/;
const INLINE_RE = /(\*\*[^*]+\*\*|`[^`]+`|https?:\/\/[^\s]+)/g;

function parseBlocks(source: string): Block[] {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const blocks: Block[] = [];

  let paragraph: string[] = [];
  let list: { type: "ul" | "ol"; items: string[] } | null = null;

  const flushParagraph = () => {
    if (paragraph.length > 0) {
      blocks.push({ type: "p", text: paragraph.join(" ") });
      paragraph = [];
    }
  };
  const flushList = () => {
    if (list) {
      blocks.push(list);
      list = null;
    }
  };

  for (const raw of lines) {
    const line = raw.trimEnd();

    if (line.trim() === "") {
      flushParagraph();
      flushList();
      continue;
    }

    const heading = HEADING_RE.exec(line);
    if (heading) {
      flushParagraph();
      flushList();
      blocks.push({ type: "heading", level: heading[1].length, text: heading[2] });
      continue;
    }

    const ordered = ORDERED_RE.exec(line);
    if (ordered) {
      flushParagraph();
      if (!list || list.type !== "ol") {
        flushList();
        list = { type: "ol", items: [] };
      }
      list.items.push(ordered[1]);
      continue;
    }

    const unordered = UNORDERED_RE.exec(line);
    if (unordered) {
      flushParagraph();
      if (!list || list.type !== "ul") {
        flushList();
        list = { type: "ul", items: [] };
      }
      list.items.push(unordered[1]);
      continue;
    }

    flushList();
    paragraph.push(line.trim());
  }

  flushParagraph();
  flushList();
  return blocks;
}

function renderInline(text: string): ReactNode[] {
  return text.split(INLINE_RE).map((token, i) => {
    if (token.startsWith("**") && token.endsWith("**")) {
      return (
        <strong key={i} className="font-semibold text-on-surface">
          {token.slice(2, -2)}
        </strong>
      );
    }
    if (token.startsWith("`") && token.endsWith("`")) {
      return (
        <code
          key={i}
          className="px-1 py-0.5 rounded bg-surface-container text-[0.85em] font-mono text-on-surface"
        >
          {token.slice(1, -1)}
        </code>
      );
    }
    if (/^https?:\/\//i.test(token)) {
      // Peel trailing punctuation that should not be part of the link.
      const m = token.match(/^(https?:\/\/\S*?)([.,;:!?)\]]*)$/i);
      const url = m ? m[1] : token;
      const trailing = m ? m[2] : "";
      return (
        <span key={i}>
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary hover:underline break-all"
          >
            {url}
          </a>
          {trailing}
        </span>
      );
    }
    return <span key={i}>{token}</span>;
  });
}

const HEADING_CLASS: Record<number, string> = {
  1: "text-lg font-semibold text-on-surface mt-3 mb-1.5",
  2: "text-base font-semibold text-on-surface mt-3 mb-1.5",
  3: "text-base font-semibold text-on-surface mt-3 mb-1",
  4: "text-sm font-semibold text-on-surface mt-2 mb-1",
  5: "text-sm font-semibold text-on-surface-variant mt-2 mb-1",
  6: "text-sm font-semibold text-on-surface-variant mt-2 mb-1",
};

export default function Markdown({
  content,
  className,
}: {
  content: string;
  className?: string;
}) {
  const blocks = parseBlocks(content);

  return (
    <div className={className ?? "text-base leading-relaxed space-y-2"}>
      {blocks.map((block, i) => {
        if (block.type === "heading") {
          return (
            <p key={i} className={HEADING_CLASS[block.level] ?? HEADING_CLASS[6]}>
              {renderInline(block.text)}
            </p>
          );
        }
        if (block.type === "ol") {
          return (
            <ol key={i} className="list-decimal pl-5 space-y-1">
              {block.items.map((item, j) => (
                <li key={j}>{renderInline(item)}</li>
              ))}
            </ol>
          );
        }
        if (block.type === "ul") {
          return (
            <ul key={i} className="list-disc pl-5 space-y-1">
              {block.items.map((item, j) => (
                <li key={j}>{renderInline(item)}</li>
              ))}
            </ul>
          );
        }
        return (
          <p key={i} className="whitespace-pre-wrap">
            {renderInline(block.text)}
          </p>
        );
      })}
    </div>
  );
}
