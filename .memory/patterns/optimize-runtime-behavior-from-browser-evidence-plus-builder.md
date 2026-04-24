---
title: Optimize runtime behavior from browser evidence plus builder telemetry
type: pattern
date: 2026-04-24
phase: testing
entity: runtime-validation
tags: [browser, telemetry, builder-logs, verification]
status: active
---

When improving autonomous-agent-builder runtime behavior, start with browser-based validation of the real operator flow, then use builder CLI telemetry and builder logs as the canonical compact evidence lane. Only drop to lower-level DB or server inspection when builder-owned evidence is insufficient. Do not optimize only from static code inspection when the live product surface or builder logs can prove the behavior more directly.
