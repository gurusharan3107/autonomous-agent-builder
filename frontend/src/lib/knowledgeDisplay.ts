const AGENT_ONLY_SECTION_HEADINGS = new Set(["agent change map", "proof for agents"]);

function normalizeHeading(heading: string) {
  return heading
    .replace(/\[\[([^\]|]+)\|([^\]]+)\]\]/g, "$2")
    .replace(/\[\[([^\]]+)\]\]/g, "$1")
    .replace(/\[(.*?)\]\((.*?)\)/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\*([^*]+)\*/g, "$1")
    .trim()
    .toLowerCase();
}

export function stripAgentOnlySections(content: string) {
  const lines = content.replace(/\r\n/g, "\n").split("\n");
  const filtered: string[] = [];
  let hideSection = false;

  for (const line of lines) {
    const sectionMatch = line.match(/^##\s+(.+?)\s*$/);
    if (sectionMatch) {
      hideSection = AGENT_ONLY_SECTION_HEADINGS.has(normalizeHeading(sectionMatch[1] ?? ""));
    }

    if (!hideSection) {
      filtered.push(line);
    }
  }

  return filtered.join("\n").replace(/\n{3,}/g, "\n\n").trim();
}
