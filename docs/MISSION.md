# Mission

Autonomous Agent Builder exists to make software delivery work in the agentic era.

The product should become an agent-native environment for building and evolving applications, where the user interacts through a simple chat surface, while the system takes responsibility for orchestrating the real work of the software lifecycle. Instead of making the user manually coordinate tools, context, models, workflows, and documentation, the builder should manage those concerns inside one operating environment.

## Product Thesis

In modern software teams, the SDLC is spread across many disconnected systems: backlog tools, documentation tools, code editors, git, CI/CD, and various knowledge sources. Agents can operate across those systems, but most users still need to decide what tool to use, what model to use, how to manage context, when to plan, when to execute, and how to preserve continuity.

Autonomous Agent Builder should remove that burden.

The user experience should stay simple:
- the user works through a chat interface
- the system understands the project and its state
- the system chooses the right workflow, model, tools, and execution strategy
- the system leaves behind durable state that both users and agents can build on

## What The Product Should Do

Autonomous Agent Builder should:

- Manage the SDLC through explicit agent-driven phases rather than one-shot coding.
- Keep project state durable and inspectable across backlog, tasks, approvals, quality gates, documentation, knowledge, and memory.
- Help users who are not deeply technical by taking responsibility for architecture research, tool selection, model routing, and context management.
- Maintain agent-friendly project documentation and knowledge with progressive disclosure, so both humans and agents can understand the system without loading everything at once.
- Capture project-specific memory to avoid repeated friction, and promote durable lessons into stronger workflows or controls when needed.
- Use the right execution mode for the situation, including planning, exploration, implementation, verification, and recovery, without making the user manage those choices manually.
- Apply cost-aware intelligence by choosing cheaper models for routine work and stronger models only when the task actually requires them.
- Use proven agent workflows and platform capabilities, such as isolated workspaces, worktrees, reusable procedures, and automated validation, as a built-in product responsibility rather than optional expert behavior.

## Core Promise

For the user, this should feel like one product, not a pile of integrations.

The user should not need to think about:
- which model to use
- how to manage context
- when to switch from planning to execution
- how to preserve project memory
- how to structure agent-friendly documentation
- when to use isolated workspaces or worktrees
- how to route work across the SDLC

Those are system responsibilities.

## Non-Goals

Autonomous Agent Builder should not become:
- a thin chat wrapper over existing tools
- a manual orchestration layer that still depends on expert users to make workflow decisions
- a generic documentation store with no execution intelligence
- a loose collection of integrations without a coherent operating model

## Design Principles

- Chat-first for the user, structured execution under the hood.
- Durable state over ephemeral agent behavior.
- Retrieval before guesswork.
- Progressive disclosure over context overload.
- System-owned workflow decisions over user micromanagement.
- Cost-efficient execution without lowering quality.
- Agent-friendly surfaces and CLIs wherever possible.
- One coherent operating environment for project delivery.

## End State

The end state is a product where an agent can take a software project from understanding, planning, and design through implementation, validation, and iteration inside a single coherent environment, while continuously maintaining the project’s state, knowledge, memory, and delivery flow with minimal user burden.
