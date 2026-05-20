---
title: "Filesystem Trust Boundaries"
doc_type: "reference"
summary: "Stable contract for resolving caller- or file-controlled paths under Builder-owned roots."
---

# Filesystem Trust Boundaries

Builder code that combines a trusted root with a caller-, route-, tool-, or
file-controlled path must resolve the child through
`autonomous_agent_builder.services.path_containment.resolve_contained_path`.

This applies to workspace tools, dashboard assets, KB document IDs, KB routing
article files, memory `routing.json` entries, and any future root-plus-relative
filesystem boundary. Do not use direct `root / value` joins for those values.

If the helper returns `None`, the caller must reject, skip, or degrade the
request without reading or writing the escaped path.
