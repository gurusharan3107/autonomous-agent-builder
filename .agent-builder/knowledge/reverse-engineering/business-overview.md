---
title: "Business Overview"
tags: ["business", "domain", "reverse-engineering"]
doc_type: "reverse-engineering"
created: "2026-04-17T19:33:52.023581"
auto_generated: true
version: 1
---

# Business Overview

## Business Context

This document provides an overview of the business domain and key concepts
implemented in this system.

## Business Entities

Core domain entities that represent business concepts:

- **TaskStatus**: Business entity
- **GateStatus**: Business entity
- **ApprovalDecision**: Business entity
- **FeatureStatus**: Business entity
- **HarnessAction**: Business entity
- **Project**: Business entity
- **Feature**: Business entity
- **Task**: Business entity
- **QualityGate**: Gate configuration — what gates exist and their settings.
- **GateResult**: Business entity
- **ApprovalGate**: Business entity
- **Approval**: Business entity
- **AgentRun**: Business entity
- **AgentRunEvent**: Business entity
- **Workspace**: Business entity

## Domain Concepts

Key concepts and terminology used in the domain:

- **Wrappers**

## Business Transactions

Business transactions are implemented through:
- API endpoints (see API Documentation)
- Service layer methods
- Database transactions
- Event handlers (if applicable)

## Domain-Driven Design

The codebase follows domain-driven design principles:
- **Entities**: Core business objects with identity
- **Value Objects**: Immutable domain concepts
- **Aggregates**: Clusters of related entities
- **Services**: Business logic that doesn't belong to entities
- **Repositories**: Data access abstraction

## Business Logic Location

Business logic is typically found in:
- Service layer (`services/`, `*_service.py`)
- Domain models (`models/`, `entities/`)
- Use cases (`use_cases/`, `handlers/`)
- Controllers/Views (presentation logic)

