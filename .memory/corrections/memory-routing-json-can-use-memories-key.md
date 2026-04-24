---
title: Memory routing.json can use memories key
type: correction
date: 2026-04-18
phase: implementation
entity: memory-api
tags: [memory, routing, json, ui]
status: active
---

## Constraint
Project-local agent memory is indexed by `.memory/routing.json`, and real repos may store entries under `memories` rather than `entries`.

## What Went Wrong
The memory API only read `entries`, so the Memory page rendered as empty even when `.memory` contained active items.

## What To Do Instead
Accept both `entries` and `memories` when loading `.memory/routing.json`, and prefer the live project-local `.memory` index over assumptions copied from older fixtures.
