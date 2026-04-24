import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

type Block =
  | { type: "heading"; level: 1 | 2 | 3; text: string }
  | { type: "paragraph"; text: string }
  | { type: "list"; items: string[] }
  | { type: "quote"; lines: string[] }
  | { type: "code"; language?: string; code: string };

function cleanInline(text: string) {
  return text
    .replace(/\[\[([^\]|]+)\|([^\]]+)\]\]/g, "$2")
    .replace(/\[\[([^\]]+)\]\]/g, "$1");
}

function parseInline(text: string): ReactNode[] {
  const tokens = text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g).filter(Boolean);

  return tokens.map((token, index) => {
    if (token.startsWith("`") && token.endsWith("`")) {
      return (
        <code
          key={`code-${index}`}
          className="rounded-md bg-muted px-1.5 py-0.5 font-mono text-[0.92em] text-foreground"
        >
          {cleanInline(token.slice(1, -1))}
        </code>
      );
    }

    if (token.startsWith("**") && token.endsWith("**")) {
      return (
        <strong key={`strong-${index}`} className="font-semibold text-foreground">
          {cleanInline(token.slice(2, -2))}
        </strong>
      );
    }

    return <span key={`text-${index}`}>{cleanInline(token)}</span>;
  });
}

function parseBlocks(content: string): Block[] {
  const lines = content
    .replace(/^---[\s\S]*?---\s*/, "")
    .replace(/\r\n/g, "\n")
    .split("\n");

  const blocks: Block[] = [];
  let paragraphLines: string[] = [];
  let listItems: string[] = [];
  let quoteLines: string[] = [];
  let codeLines: string[] = [];
  let codeLanguage = "";
  let inCode = false;

  const flushParagraph = () => {
    if (paragraphLines.length === 0) return;
    blocks.push({
      type: "paragraph",
      text: paragraphLines.join(" ").replace(/\s+/g, " ").trim(),
    });
    paragraphLines = [];
  };

  const flushList = () => {
    if (listItems.length === 0) return;
    blocks.push({ type: "list", items: [...listItems] });
    listItems = [];
  };

  const flushQuote = () => {
    if (quoteLines.length === 0) return;
    blocks.push({ type: "quote", lines: [...quoteLines] });
    quoteLines = [];
  };

  const flushCode = () => {
    if (codeLines.length === 0) return;
    blocks.push({
      type: "code",
      language: codeLanguage || undefined,
      code: codeLines.join("\n").trimEnd(),
    });
    codeLines = [];
    codeLanguage = "";
  };

  for (const rawLine of lines) {
    const line = rawLine.trimEnd();
    const trimmed = line.trim();

    if (trimmed.startsWith("```")) {
      if (inCode) {
        flushCode();
        inCode = false;
      } else {
        flushParagraph();
        flushList();
        flushQuote();
        inCode = true;
        codeLanguage = trimmed.slice(3).trim();
      }
      continue;
    }

    if (inCode) {
      codeLines.push(rawLine);
      continue;
    }

    if (!trimmed) {
      flushParagraph();
      flushList();
      flushQuote();
      continue;
    }

    const headingMatch = trimmed.match(/^(#{1,3})\s+(.*)$/);
    if (headingMatch) {
      flushParagraph();
      flushList();
      flushQuote();
      blocks.push({
        type: "heading",
        level: headingMatch[1].length as 1 | 2 | 3,
        text: cleanInline(headingMatch[2].trim()),
      });
      continue;
    }

    if (/^[-*]\s+/.test(trimmed)) {
      flushParagraph();
      flushQuote();
      listItems.push(trimmed.replace(/^[-*]\s+/, ""));
      continue;
    }

    if (trimmed.startsWith(">")) {
      flushParagraph();
      flushList();
      quoteLines.push(trimmed.replace(/^>\s?/, ""));
      continue;
    }

    paragraphLines.push(trimmed);
  }

  flushParagraph();
  flushList();
  flushQuote();
  flushCode();

  return blocks;
}

interface EditorialContentProps {
  content: string;
  externalTitle?: string;
  className?: string;
}

export function EditorialContent({
  content,
  externalTitle,
  className,
}: EditorialContentProps) {
  const blocks = parseBlocks(content);
  const normalizedExternalTitle = externalTitle?.trim().toLowerCase();
  const visibleBlocks =
    normalizedExternalTitle &&
    blocks[0]?.type === "heading" &&
    blocks[0].level === 1 &&
    blocks[0].text.trim().toLowerCase() === normalizedExternalTitle
      ? blocks.slice(1)
      : blocks;

  if (visibleBlocks.length === 0) {
    return (
      <div className="rounded-[1.5rem] border border-dashed border-border bg-muted/15 px-5 py-4 text-sm text-muted-foreground">
        No readable content available.
      </div>
    );
  }

  return (
    <div
      className={cn(
        "editorial-surface space-y-5 text-[14px] leading-[1.6] text-foreground/88",
        className,
      )}
    >
      {visibleBlocks.map((block, index) => {
        if (block.type === "heading") {
          if (block.level === 1) {
            return (
              <h1
                key={`heading-${index}`}
                className="max-w-[13ch] text-[2.2rem] font-semibold leading-[0.98] tracking-[-0.05em] text-foreground sm:text-[2.5rem]"
              >
                {block.text}
              </h1>
            );
          }

          if (block.level === 2) {
            return (
              <section key={`section-${index}`} className="space-y-3 pt-2">
                <div className="h-px bg-border/70" />
                <h2 className="text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                  {block.text}
                </h2>
              </section>
            );
          }

          return (
            <h3
              key={`subheading-${index}`}
              className="text-[1rem] font-semibold tracking-tight text-foreground"
            >
              {block.text}
            </h3>
          );
        }

        if (block.type === "paragraph") {
          return (
            <p
              key={`paragraph-${index}`}
              className="max-w-[69ch] text-[14px] leading-[1.6] text-foreground/84"
            >
              {parseInline(block.text)}
            </p>
          );
        }

        if (block.type === "list") {
          return (
            <ul
              key={`list-${index}`}
              className="max-w-[70ch] space-y-2.5 pl-5 text-[14px] leading-[1.6] text-foreground/84 marker:text-muted-foreground"
            >
              {block.items.map((item, itemIndex) => (
                <li key={`item-${index}-${itemIndex}`}>{parseInline(item)}</li>
              ))}
            </ul>
          );
        }

        if (block.type === "quote") {
          return (
            <blockquote
              key={`quote-${index}`}
              className="max-w-[69ch] rounded-r-[1rem] rounded-l-[0.3rem] border-l-[3px] border-status-active/35 bg-status-active/[0.045] px-5 py-4 text-[14px] leading-[1.6] text-foreground/78"
            >
              {block.lines.map((line, lineIndex) => (
                <p key={`quote-line-${index}-${lineIndex}`}>
                  {parseInline(line)}
                </p>
              ))}
            </blockquote>
          );
        }

        return (
          <div
            key={`code-${index}`}
            className="max-w-[72ch] overflow-x-auto rounded-[1.7rem] border border-border bg-muted/28"
          >
            <div className="flex items-center justify-between border-b border-border px-4 py-2">
              <span className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                {block.language || "code"}
              </span>
            </div>
            <pre className="overflow-x-auto px-4 py-4 text-[12px] leading-5 text-foreground/88">
              <code>{block.code}</code>
            </pre>
          </div>
        );
      })}
    </div>
  );
}
