# Planning Phase

Canonical owner contract for the `planning` phase.

## Purpose

Turn a feature request for an existing product into one correctly bounded backlog
feature and the next delivery handoff.

This is the canonical lane for feature addition or modification on top of an
existing repo.

## Entry Conditions

Enter `planning` when:
- the repo already exists
- the user wants to add or modify a feature
- the main need is to shape one delivery-sized backlog feature against current
  repo reality

Forward-engineering idea intake should enter `requirements` first, not
`planning`.

## Owner

Owner: the top-level interactive Agent-page lane until one backlog feature is
correctly bounded.

The phase remains interactive because operator decisions can still be required,
but the agent is expected to ground the work in current repo context instead of
asking the user to supply technical discovery.

## Auto-Allowed Tools

- `AskUserQuestion`
- `Read`
- `Glob`
- `Grep`
- read-only workspace and project-info tools
- bounded builder context surfaces such as repo-local knowledge, backlog, and
  memory reads

Critical rule:
- read-only repo inspection is auto-allowed here

The planning lane should be able to inspect current routes, models, UI
surfaces, and naming before writing a feature contract.

## Denied Tools

- `Edit`
- `Write`
- `Bash`
- task execution or dispatch tools
- broad mutation tools
- implementation-phase specialist work

## Operator Checkpoint Rules

Use `AskUserQuestion` only when the next blocker is a true product ambiguity
that repo context cannot resolve.

Do not use `AskUserQuestion` for:
- discovering what already exists in the repo
- learning file structure or API shape
- re-asking information already answered in the session

The planning lane should first inspect the repo with read-only tools, then ask
only the minimum operator questions required to lock scope.

## Output And Handoff Contract

Expected output:
- one concrete backlog feature
- implementation-oriented description and boundaries
- acceptance criteria
- next handoff into task generation or delivery dispatch

The phase ends when the feature is sufficiently bounded for downstream delivery,
not when implementation is complete.

## Context-Efficiency Rules

- start with bounded repo retrieval and read-only inspection
- only read the parts of the repo that affect the feature contract
- keep operator questions sparse and high leverage
- do not reopen broad product-definition work that belongs in `requirements`

## Current Repo Mapping

Current repo mapping: `pending`, `planning`, and the interactive feature-backlog
interview lane used for existing-product feature requests.

