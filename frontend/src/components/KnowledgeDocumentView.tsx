import { EditorialContent } from "@/components/EditorialContent";
import { stripAgentOnlySections } from "@/lib/knowledgeDisplay";

interface KnowledgeDocumentViewProps {
  content: string;
  externalTitle?: string;
}

export function KnowledgeDocumentView({
  content,
  externalTitle,
}: KnowledgeDocumentViewProps) {
  return <EditorialContent content={stripAgentOnlySections(content)} externalTitle={externalTitle} />;
}
