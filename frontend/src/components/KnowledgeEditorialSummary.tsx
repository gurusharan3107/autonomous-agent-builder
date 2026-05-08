import { KnowledgeDocumentView } from "@/components/KnowledgeDocumentView";
import { stripAgentOnlySections } from "@/lib/knowledgeDisplay";
import type { KBDocument, RelatedDocs } from "@/lib/types";

const TYPE_LABELS: Record<string, string> = {
  adr: "ADR",
  api_contract: "API Contract",
  schema: "Schema",
  runbook: "Runbook",
  context: "Context",
  raw: "Article",
};

const DETAIL_SUMMARY_MAX_WORDS = 58;
const TAKEAWAY_MAX_WORDS = 18;

function cleanInline(text: string) {
  return text
    .replace(/\[\[([^\]|]+)\|([^\]]+)\]\]/g, "$2")
    .replace(/\[\[([^\]]+)\]\]/g, "$1")
    .replace(/\[(.*?)\]\((.*?)\)/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\*([^*]+)\*/g, "$1")
    .replace(/#+\s*/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function stripBody(content: string) {
  return content
    .replace(/^---[\s\S]*?---\s*/, "")
    .replace(/\r\n/g, "\n")
    .replace(/```[\s\S]*?```/g, "")
    .trim();
}

function truncateWords(text: string, maxWords: number) {
  const words = text.trim().split(/\s+/).filter(Boolean);
  if (words.length <= maxWords) return text.trim();
  return `${words.slice(0, maxWords).join(" ").replace(/[,:;.-]+$/, "")}...`;
}

function getSections(content: string) {
  const body = stripBody(content);
  const pattern = /^##\s+(.+)$/gm;
  const matches = Array.from(body.matchAll(pattern));

  return matches.map((match, index) => {
    const start = match.index ?? 0;
    const bodyStart = start + match[0].length;
    const bodyEnd = matches[index + 1]?.index ?? body.length;
    return {
      heading: cleanInline(match[1] ?? ""),
      content: body.slice(bodyStart, bodyEnd).trim(),
    };
  });
}

function getSummaryParagraph(content: string) {
  const preferredHeadings = new Set([
    "overview",
    "insight",
    "summary",
    "purpose",
    "context",
    "applicability",
  ]);

  const sections = getSections(content);
  const preferredSection =
    sections.find((section) => preferredHeadings.has(section.heading.toLowerCase())) ??
    sections.find((section) => cleanInline(section.content).length > 0);

  const summarySource = preferredSection?.content ?? stripBody(content);
  const cleaned = cleanInline(summarySource);
  if (!cleaned) return "";
  return truncateWords(cleaned, DETAIL_SUMMARY_MAX_WORDS);
}

function getParagraphs(content: string) {
  const summary = getSummaryParagraph(content);
  if (summary) {
    return [summary];
  }

  return stripBody(content)
    .split(/\n\s*\n/)
    .map((chunk) => cleanInline(chunk))
    .filter((chunk) => chunk.length > 70 && !chunk.startsWith("- ") && !chunk.startsWith("* "))
    .map((chunk) => truncateWords(chunk, DETAIL_SUMMARY_MAX_WORDS))
    .slice(0, 1);
}

function getHeadings(content: string, title?: string) {
  const titleKey = title?.trim().toLowerCase();
  return stripBody(content)
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => /^#{2,3}\s+/.test(line))
    .map((line) => cleanInline(line.replace(/^#{2,3}\s+/, "")))
    .filter((line) => line.length > 0 && line.toLowerCase() !== titleKey)
    .slice(0, 4);
}

function getTakeaways(content: string) {
  const sections = getSections(content);
  const preferredSections = sections.filter((section) => section.heading.toLowerCase() !== "overview");
  const sourceSections = preferredSections.length > 0 ? preferredSections : sections;

  const bullets = sourceSections
    .flatMap((section) =>
      section.content
        .split("\n")
        .map((line) => line.trim())
        .filter((line) => /^[-*]\s+/.test(line))
        .map((line) => cleanInline(line.replace(/^[-*]\s+/, ""))),
    )
    .filter((line) => line.length > 0);

  if (bullets.length > 0) {
    return bullets.map((item) => truncateWords(item, TAKEAWAY_MAX_WORDS)).slice(0, 3);
  }

  return getParagraphs(content)
    .map((paragraph) => truncateWords(paragraph, TAKEAWAY_MAX_WORDS))
    .filter(Boolean)
    .slice(0, 3);
}

function formatDate(value?: string) {
  if (!value) return "Recent";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Recent";
  return parsed.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function formatDocType(value: string) {
  return TYPE_LABELS[value] ?? value.replaceAll("_", " ");
}

function summaryLabel(doc: KBDocument) {
  if (doc.source_author) return doc.source_author;
  if (doc.source_title) return doc.source_title;
  return doc.scope === "global" ? "Global knowledge" : "Local knowledge";
}

export function KnowledgeEditorialSummary({
  doc,
  relatedDocs,
}: {
  doc: KBDocument;
  relatedDocs: RelatedDocs | null;
}) {
  const userVisibleContent = stripAgentOnlySections(doc.content);
  const paragraphs =
    doc.detail_summary && doc.detail_summary.trim()
      ? [doc.detail_summary.trim()]
      : getParagraphs(userVisibleContent);
  const headings = getHeadings(userVisibleContent, doc.title);
  const takeaways = getTakeaways(userVisibleContent);
  const relatedCount =
    (relatedDocs?.wikilinks.length ?? 0) +
    (relatedDocs?.backlinks.length ?? 0) +
    (relatedDocs?.similar.length ?? 0);

  return (
    <article className="rounded-[1.85rem] border border-border/76 bg-card/88 px-5 py-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.68)] sm:px-6 sm:py-6">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
        <span className="inline-flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-status-active" />
          {summaryLabel(doc)}
        </span>
        <span>{formatDocType(doc.doc_type)}</span>
        <span>{formatDate(doc.date_published || doc.created_at)}</span>
      </div>

      <div className="mt-5 max-w-[46rem]">
        <h3 className="font-[family:var(--font-heading)] text-[2.2rem] font-semibold leading-[0.94] tracking-[-0.065em] text-foreground sm:text-[2.8rem]">
          {doc.title}
        </h3>

        {paragraphs.length > 0 ? (
          <div className="mt-5 space-y-4">
            {paragraphs.map((paragraph) => (
              <p
                key={paragraph}
                className="max-w-[42rem] text-[16px] leading-[1.62] text-foreground/82"
              >
                {paragraph}
              </p>
            ))}
          </div>
        ) : (
          <p className="mt-5 max-w-[42rem] text-[16px] leading-[1.62] text-muted-foreground">
            This document is available for reading in full below.
          </p>
        )}
      </div>

      <div className="mt-8 grid gap-4 xl:grid-cols-[minmax(0,1.08fr)_minmax(280px,0.92fr)]">
        <section className="min-w-0 rounded-[1.45rem] border border-status-active/18 bg-status-active/[0.05] px-5 py-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
            Operator brief
          </p>
          {takeaways.length > 0 ? (
            <ul className="mt-4 space-y-3">
              {takeaways.map((item) => (
                <li key={item} className="flex min-w-0 items-start gap-3 text-[15px] leading-[1.6] text-foreground/82">
                  <span className="mt-[0.55rem] h-1.5 w-1.5 shrink-0 rounded-full bg-status-active" />
                  <span className="min-w-0 [overflow-wrap:anywhere]">{item}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-4 text-[15px] leading-[1.6] text-muted-foreground">
              No concise brief could be derived from this record yet.
            </p>
          )}
        </section>

        <div className="min-w-0 space-y-4">
          <section className="min-w-0 rounded-[1.45rem] border border-border/74 bg-background/62 px-5 py-4">
            <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
              Document map
            </p>
            {headings.length > 0 ? (
              <ul className="mt-4 space-y-3">
                {headings.map((heading) => (
                  <li key={heading} className="flex min-w-0 items-start gap-3 text-[14px] leading-[1.55] text-foreground/78">
                    <span className="mt-[0.48rem] h-1.5 w-1.5 shrink-0 rounded-full bg-foreground/28" />
                    <span className="min-w-0 [overflow-wrap:anywhere]">{heading}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-4 text-[14px] leading-[1.55] text-muted-foreground">
                This note reads as a continuous document without major subsections.
              </p>
            )}
          </section>

          <section className="rounded-[1.45rem] border border-border/74 bg-background/62 px-5 py-4">
            <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
              Supporting context
            </p>
            <div className="mt-4 grid gap-3 sm:grid-cols-3 xl:grid-cols-1">
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                  Scope
                </p>
                <p className="mt-2 text-[14px] font-semibold text-foreground">
                  {doc.scope === "global" ? "Global workspace" : "Local workspace"}
                </p>
              </div>
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                  Links in note
                </p>
                <p className="mt-2 font-mono text-[14px] text-foreground">
                  {doc.wikilinks?.length ?? 0}
                </p>
              </div>
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                  Related context
                </p>
                <p className="mt-2 font-mono text-[14px] text-foreground">{relatedCount}</p>
              </div>
            </div>
          </section>
        </div>
      </div>

      <div className="mt-8 border-t border-border/68 pt-7">
        <KnowledgeDocumentView content={userVisibleContent} externalTitle={doc.title} />
      </div>
    </article>
  );
}
