---
title: "API Endpoints"
tags: ["api", "endpoints", "rest", "reverse-engineering"]
doc_type: "reverse-engineering"
created: "2026-04-17T19:33:45.629468"
auto_generated: true
version: 1
---

# API Endpoints

## Overview

This document describes all REST API endpoints, their methods, parameters,
and expected responses.

## Base URL

- **Development**: `http://localhost:8000`
- **Production**: Configured via environment

## 

### GET /

Pipeline board — main dashboard view.

**Response**: JSON

### POST /

Create a knowledge base document.

**Parameters**:

- `body` (KBDocCreate)

**Response**: DesignDocument

### GET /

List knowledge base documents with optional filters.

**Parameters**:

- `task_id` (Any)
- `doc_type` (Any)
- `limit` (int)

**Response**: list

### GET /

List memory entries from .memory/routing.json.

**Parameters**:

- `mem_type` (Any)
- `phase` (Any)
- `entity` (Any)
- `limit` (int)

**Response**: list

### POST /

**Parameters**:

- `data` (ProjectCreate)

**Response**: JSON

### GET /

**Response**: JSON

## Api

### GET /api/board

HTMX fragment — returns only the board inner HTML for polling swap.

**Response**: JSON

### GET /api/approval-gates/{gate_id}/thread

HTMX fragment — returns chat thread HTML for approval gate polling.

**Parameters**:

- `gate_id` (str)

**Response**: JSON

## Approval-Gates

### POST /approval-gates/{gate_id}/approve

Submit an approval decision for a gate.

**Parameters**:

- `gate_id` (str)
- `data` (ApprovalCreate)

**Response**: JSON

## Approvals

### GET /approvals/{gate_id}

Group chat approval review page.

**Parameters**:

- `gate_id` (str)

**Response**: JSON

## Dashboard

### GET /dashboard/board

Board data as JSON — consumed by React frontend.

**Response**: JSON

### GET /dashboard/metrics

Metrics data as JSON — consumed by React frontend.

**Response**: JSON

### GET /dashboard/approvals/{gate_id}

Approval gate details as JSON — consumed by React frontend.

**Parameters**:

- `gate_id` (str)

**Response**: JSON

### GET /dashboard/features

Feature list from .claude/progress/feature-list.json.

**Response**: JSON

### GET /dashboard/board

Board data as JSON — consumed by React frontend.

**Response**: JSON

### GET /dashboard/metrics

Metrics data as JSON — consumed by React frontend.

**Response**: JSON

### GET /dashboard/approvals/{gate_id}

Approval gate details as JSON — consumed by React frontend.

**Parameters**:

- `gate_id` (str)

**Response**: JSON

## Dispatch

### POST /dispatch

Dispatch a task through the SDLC pipeline.

The orchestrator runs the task's next phase asynchronously.

**Parameters**:

- `data` (DispatchRequest)
- `background` (BackgroundTasks)

**Response**: JSON

## Features

### GET /features/{feature_id}

**Parameters**:

- `feature_id` (str)

**Response**: JSON

### POST /features/{feature_id}/tasks

**Parameters**:

- `feature_id` (str)
- `data` (TaskCreate)

**Response**: JSON

### GET /features/{feature_id}/tasks

**Parameters**:

- `feature_id` (str)

**Response**: JSON

### GET /features

List all features for the current project.

**Response**: JSON

### POST /features

Create a new feature.

**Parameters**:

- `title` (str)
- `description` (str)
- `priority` (int)

**Response**: JSON

## Gates

### GET /gates

List quality gate results.

**Response**: JSON

## Kb

### GET /kb/

List knowledge base documents.

**Parameters**:

- `task_id` (Any)
- `doc_type` (Any)
- `limit` (Any)

**Response**: JSON

### GET /kb/{doc_id}

Get a specific knowledge base document.

**Parameters**:

- `doc_id` (str)

**Response**: JSON

### GET /kb/search

Search knowledge base documents.

**Parameters**:

- `q` (str)

**Response**: JSON

## Memory

### GET /memory/

List all memory entries.

**Response**: JSON

### GET /memory/{slug}

Get a specific memory entry.

**Parameters**:

- `slug` (str)

**Response**: JSON

## Metrics

### GET /metrics

Metrics dashboard — cost tracking, gate pass rates.

**Response**: JSON

## Projects

### POST /projects/{project_id}/features

**Parameters**:

- `project_id` (str)
- `data` (FeatureCreate)

**Response**: JSON

### GET /projects/{project_id}/features

**Parameters**:

- `project_id` (str)

**Response**: JSON

### POST /projects/

Create a new project.

**Parameters**:

- `data` (ProjectCreate)

**Response**: JSON

### GET /projects/

List all projects.

**Response**: JSON

### GET /projects/{project_id}

Get a specific project.

**Parameters**:

- `project_id` (str)

**Response**: JSON

## Search

### GET /search

Search KB documents by title and content (SQL LIKE).

**Parameters**:

- `q` (str)
- `doc_type` (Any)
- `task_id` (Any)
- `limit` (int)

**Response**: list

### GET /search

Search memories by title, tags, and content.

**Parameters**:

- `q` (str)
- `entity` (Any)
- `tag` (Any)
- `limit` (int)

**Response**: list

## Stream

### GET /stream

SSE endpoint for real-time updates.

Streams events to connected clients for real-time dashboard updates.
Events include task updates, gate results, agent progress, and board changes.

Event types:
- task_update: Task status changed
- gate_result: Quality gate completed
- agent_progress: Agent execution progress
- board_update: Board state changed

**Response**: JSON

## Tasks

### GET /tasks/{task_id}

**Parameters**:

- `task_id` (str)

**Response**: JSON

### GET /tasks/{task_id}/gates

**Parameters**:

- `task_id` (str)

**Response**: JSON

### GET /tasks/{task_id}/runs

**Parameters**:

- `task_id` (str)

**Response**: JSON

### GET /tasks/{task_id}/approvals

**Parameters**:

- `task_id` (str)

**Response**: JSON

### GET /tasks

List all tasks for the current project.

**Response**: JSON

### POST /tasks/{task_id}/dispatch

Dispatch a task through the orchestrator.

**Parameters**:

- `task_id` (str)

**Response**: JSON

## {Doc_Id}

### GET /{doc_id}

Get a single KB document by ID.

**Parameters**:

- `doc_id` (str)

**Response**: DesignDocument

### PUT /{doc_id}

Update a KB document. Bumps version on content change.

**Parameters**:

- `doc_id` (str)
- `body` (KBDocUpdate)

**Response**: DesignDocument

## {Project_Id}

### GET /{project_id}

**Parameters**:

- `project_id` (str)

**Response**: JSON

## {Slug}

### GET /{slug}

Get a single memory entry with content.

**Parameters**:

- `slug` (str)

**Response**: dict

## Authentication

Authentication details (if applicable):
- API keys
- JWT tokens
- OAuth

## Error Responses

Standard error response format:
```json
{
  "detail": "Error message",
  "status_code": 400
}
```

Common status codes:
- 200: Success
- 201: Created
- 400: Bad Request
- 401: Unauthorized
- 404: Not Found
- 500: Internal Server Error

