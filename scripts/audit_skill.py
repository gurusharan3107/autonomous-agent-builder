"""Audit a SKILL.md file for quality gate metrics."""
import re
import os
import sys
import json

skill_path = sys.argv[1] if len(sys.argv) > 1 else "."
skill_md = os.path.join(skill_path, "SKILL.md")

with open(skill_md, encoding="utf-8") as f:
    content = f.read()

lines = content.split("\n")

# Frontmatter
has_name = "name:" in content[:500]
has_description = "description:" in content[:500]

# Description word count
desc_match = re.search(r'description:\s*"(.+?)"', content, re.DOTALL)
desc_words = len(desc_match.group(1).split()) if desc_match else 0

# Imperatives
imperatives = len(
    re.findall(r"\b(MUST|NEVER|ALWAYS|REQUIRED|CRITICAL|IMPORTANT|DO NOT)\b", content)
)

# Why explanations
why_count = len(
    re.findall(r"\b(because|reason|why|rationale|principle)\b", content, re.IGNORECASE)
)

# Inline bash blocks
bash_blocks = len(re.findall(r"```bash", content))

# References
ref_dir = os.path.join(skill_path, "references")
ref_count = len(os.listdir(ref_dir)) if os.path.isdir(ref_dir) else 0

# Scripts
script_dir = os.path.join(skill_path, "scripts")
script_count = (
    len([f for f in os.listdir(script_dir) if f.endswith((".sh", ".py"))])
    if os.path.isdir(script_dir)
    else 0
)

# Gotchas
has_gotchas = bool(re.search(r"## Gotchas|## Gotcha|gotcha", content, re.IGNORECASE))

# Context fork
has_context_fork = "context: fork" in content or "context:fork" in content

result = {
    "total_lines": len(lines),
    "has_name": has_name,
    "has_description": has_description,
    "description_words": desc_words,
    "imperative_count": imperatives,
    "why_explanations": why_count,
    "inline_bash_blocks": bash_blocks,
    "reference_count": ref_count,
    "script_count": script_count,
    "has_gotchas": has_gotchas,
    "has_context_fork": has_context_fork,
}
print(json.dumps(result, indent=2))
