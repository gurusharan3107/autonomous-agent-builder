# Requirements Document

## Introduction

Transform the autonomous-agent-builder from a centralized multi-project system to a project-level, agent-first CLI tool. Each repository will have its own self-contained agent builder instance with local database, embedded server, and dashboard. The CLI remains the primary interface for both human developers and AI agents, with script-based interactions to minimize token usage.

## Glossary

- **Builder_CLI**: The `builder` command-line interface that operates on the agent builder system
- **Project_Instance**: A self-contained agent builder installation within a single repository
- **Local_Database**: SQLite database stored in `.agent-builder/` directory within the project
- **Embedded_Server**: FastAPI server instance running from within the project directory
- **Dashboard**: React-based web interface for visualizing and interacting with the SDLC pipeline
- **Init_Command**: The `builder init` command that bootstraps agent builder into a repository
- **Script_Library**: Pre-built Python scripts packaged with the tool for repetitive agent interactions
- **Central_Server**: Optional remote server for cross-project synchronization (future feature)
- **Agent_Mode**: Non-interactive CLI execution with JSON output for AI agent consumption
- **Human_Mode**: Interactive CLI execution with formatted text output for human users

## Requirements

### Requirement 1: Project Initialization

**User Story:** As a developer, I want to initialize agent builder in any repository, so that I can enable autonomous SDLC capabilities for that project.

#### Acceptance Criteria

1. THE Init_Command SHALL create a `.agent-builder/` directory in the current working directory
2. THE Init_Command SHALL create a SQLite database file at `.agent-builder/agent_builder.db`
3. THE Init_Command SHALL copy the Embedded_Server code into `.agent-builder/server/`
4. THE Init_Command SHALL copy the Dashboard assets into `.agent-builder/dashboard/`
5. THE Init_Command SHALL copy the Script_Library into `.agent-builder/scripts/`
6. THE Init_Command SHALL create a configuration file at `.agent-builder/config.yaml`
7. THE Init_Command SHALL run database migrations to initialize the schema
8. WHEN the `.agent-builder/` directory already exists, THE Init_Command SHALL return an error message
9. WHERE the `--force` flag is provided, THE Init_Command SHALL reinitialize the existing installation

### Requirement 2: Non-Interactive Initialization

**User Story:** As an AI agent, I want to initialize agent builder without user prompts, so that I can automate project setup.

#### Acceptance Criteria

1. WHERE the `--no-input` flag is provided, THE Init_Command SHALL skip all interactive prompts
2. WHERE the `--no-input` flag is provided, THE Init_Command SHALL use default values for all configuration options
3. WHERE the `--project-name` option is provided, THE Init_Command SHALL use the provided name instead of the default
4. WHERE the `--language` option is provided, THE Init_Command SHALL configure the project for the specified language
5. WHERE the `--framework` option is provided, THE Init_Command SHALL configure the project for the specified framework
6. THE Init_Command SHALL return exit code 0 when initialization succeeds
7. THE Init_Command SHALL return exit code 1 when initialization fails

### Requirement 3: Local Database Operations

**User Story:** As a developer, I want all project data stored locally, so that each project is self-contained and portable.

#### Acceptance Criteria

1. THE Builder_CLI SHALL read from the Local_Database in the current project's `.agent-builder/` directory
2. WHEN no `.agent-builder/` directory exists in the current or parent directories, THE Builder_CLI SHALL return an error message with initialization instructions
3. THE Builder_CLI SHALL support SQLite as the default database engine
4. THE Local_Database SHALL store all projects, features, tasks, gates, runs, approvals, and security findings for the current project
5. WHEN the Builder_CLI is invoked from a subdirectory, THE Builder_CLI SHALL search parent directories for `.agent-builder/` up to the filesystem root

### Requirement 4: Embedded Server Management

**User Story:** As a developer, I want to start a local server for the dashboard, so that I can visualize the SDLC pipeline.

#### Acceptance Criteria

1. THE Builder_CLI SHALL provide a `builder start` command that launches the Embedded_Server
2. THE Embedded_Server SHALL bind to an available port starting from 8000
3. WHEN port 8000 is occupied, THE Embedded_Server SHALL try ports 8001 through 8010 sequentially
4. WHEN no ports are available in the range, THE Embedded_Server SHALL return an error message
5. THE Embedded_Server SHALL read from the Local_Database in the same `.agent-builder/` directory
6. THE Embedded_Server SHALL serve the Dashboard assets from `.agent-builder/dashboard/`
7. THE Embedded_Server SHALL log the server URL to stdout when startup completes
8. WHERE the `--port` option is provided, THE Embedded_Server SHALL use the specified port without auto-detection

### Requirement 5: Agent-First CLI Design

**User Story:** As an AI agent, I want machine-readable output from all commands, so that I can parse results programmatically.

#### Acceptance Criteria

1. WHERE the `--json` flag is provided, THE Builder_CLI SHALL output results as JSON
2. WHERE stdout is not a TTY, THE Builder_CLI SHALL output results as JSON by default
3. WHERE stdout is a TTY and no `--json` flag is provided, THE Builder_CLI SHALL output formatted text
4. THE Builder_CLI SHALL return exit code 0 for successful operations
5. THE Builder_CLI SHALL return exit code 1 for general failures
6. THE Builder_CLI SHALL return exit code 2 for invalid command usage
7. THE Builder_CLI SHALL return exit code 3 for connectivity errors
8. WHEN an error occurs, THE Builder_CLI SHALL include an actionable hint in the error message

### Requirement 6: Non-Interactive Command Execution

**User Story:** As an AI agent, I want to execute commands without confirmation prompts, so that I can automate workflows.

#### Acceptance Criteria

1. WHERE the `--yes` flag is provided, THE Builder_CLI SHALL skip all confirmation prompts
2. WHERE the `--dry-run` flag is provided, THE Builder_CLI SHALL show what would be executed without making changes
3. WHERE the `--no-input` flag is provided, THE Builder_CLI SHALL use default values for all prompts
4. THE Builder_CLI SHALL document all flags that enable non-interactive execution in command help text

### Requirement 7: Context Window Protection

**User Story:** As an AI agent, I want truncated output by default, so that I don't exceed context window limits.

#### Acceptance Criteria

1. THE Builder_CLI SHALL truncate text output to 2000 characters by default
2. WHEN output is truncated, THE Builder_CLI SHALL append a truncation marker indicating the `--full` flag
3. WHERE the `--full` flag is provided, THE Builder_CLI SHALL return complete untruncated output
4. THE Builder_CLI SHALL not truncate JSON output when the `--json` flag is provided

### Requirement 8: Script-Based Agent Interaction

**User Story:** As an AI agent, I want to call pre-built scripts for common tasks, so that I minimize token usage.

#### Acceptance Criteria

1. THE Script_Library SHALL include a script for creating features with validation
2. THE Script_Library SHALL include a script for dispatching tasks through the pipeline
3. THE Script_Library SHALL include a script for checking quality gate results
4. THE Script_Library SHALL include a script for updating the dashboard state
5. THE Builder_CLI SHALL provide a `builder script list` command that shows available scripts
6. THE Builder_CLI SHALL provide a `builder script run <name>` command that executes a script
7. WHERE the `--json` flag is provided, THE script output SHALL be formatted as JSON
8. THE Script_Library SHALL be copied into `.agent-builder/scripts/` during initialization

### Requirement 9: Dashboard Conversational Interface

**User Story:** As a developer, I want to interact with the agent through the dashboard, so that I can provide setup information conversationally.

#### Acceptance Criteria

1. THE Dashboard SHALL include a chat interface for agent interaction
2. THE Dashboard SHALL display the current board state with tasks and their statuses
3. THE Dashboard SHALL display project metrics including cost and gate pass rates
4. THE Dashboard SHALL update in real-time using Server-Sent Events (SSE) for streaming updates
5. THE Dashboard SHALL use the Script_Library for state updates to maintain consistency with CLI
6. THE Dashboard SHALL work offline with no external dependencies
7. THE Dashboard SHALL receive agent progress updates through SSE without polling
8. THE Dashboard SHALL maintain a single SSE connection per browser session

### Requirement 10: Project Isolation

**User Story:** As a developer, I want each project to operate independently, so that changes in one project don't affect others.

#### Acceptance Criteria

1. THE Builder_CLI SHALL operate only on the current Project_Instance by default
2. THE Builder_CLI SHALL not share data between different Project_Instance installations
3. THE Local_Database SHALL contain data only for the current project
4. THE Embedded_Server SHALL serve only the current project's data
5. WHEN multiple projects are open, THE Builder_CLI SHALL determine the current project from the working directory

### Requirement 11: Migration from Multi-Project Mode

**User Story:** As a developer with existing projects, I want to migrate to project-level mode, so that I can adopt the new architecture.

#### Acceptance Criteria

1. THE Builder_CLI SHALL provide a `builder migrate` command that exports a project from the central database
2. THE migrate command SHALL create a `.agent-builder/` directory in the specified path
3. THE migrate command SHALL copy all project data from the central database to the Local_Database
4. THE migrate command SHALL preserve all features, tasks, gates, runs, and approvals
5. WHERE the `--archive` flag is provided, THE migrate command SHALL mark the project as archived in the central database
6. THE migrate command SHALL generate a migration report showing what was transferred

### Requirement 12: Port Conflict Resolution

**User Story:** As a developer running multiple projects, I want automatic port assignment, so that I can run multiple dashboards simultaneously.

#### Acceptance Criteria

1. WHEN the Embedded_Server starts, THE Embedded_Server SHALL check if the target port is available
2. WHEN the target port is occupied, THE Embedded_Server SHALL increment the port number and retry
3. THE Embedded_Server SHALL try up to 10 ports before failing
4. THE Embedded_Server SHALL write the assigned port to `.agent-builder/server.port`
5. THE Builder_CLI SHALL read the port from `.agent-builder/server.port` when connecting to the server

### Requirement 13: Configuration Management

**User Story:** As a developer, I want to configure project-specific settings, so that I can customize behavior for my project.

#### Acceptance Criteria

1. THE Init_Command SHALL create a configuration file at `.agent-builder/config.yaml`
2. THE configuration file SHALL include project name, language, and framework settings
3. THE configuration file SHALL include agent budget limits and gate timeout values
4. THE configuration file SHALL include retry limits and quality gate thresholds
5. THE Builder_CLI SHALL read configuration from `.agent-builder/config.yaml` on startup
6. THE Builder_CLI SHALL provide a `builder config show` command that displays current configuration
7. THE Builder_CLI SHALL provide a `builder config set <key> <value>` command that updates configuration
8. THE configuration precedence SHALL follow: CLI flags > environment variables > project config > user config > system defaults

### Requirement 14: Error Messages with Hints

**User Story:** As a developer, I want actionable error messages, so that I know how to fix problems.

#### Acceptance Criteria

1. WHEN the Builder_CLI cannot find `.agent-builder/`, THE error message SHALL suggest running `builder init`
2. WHEN the Embedded_Server cannot connect to the database, THE error message SHALL suggest checking file permissions
3. WHEN a command requires a running server, THE error message SHALL suggest running `builder start`
4. WHEN a port is already in use, THE error message SHALL suggest using the `--port` option
5. WHEN a command fails validation, THE error message SHALL explain which parameters are invalid

### Requirement 15: Backward Compatibility

**User Story:** As a developer with existing workflows, I want the CLI interface to remain consistent, so that my scripts don't break.

#### Acceptance Criteria

1. THE Builder_CLI SHALL maintain the same command structure (`builder <resource> <verb>`)
2. THE Builder_CLI SHALL maintain the same flag names (`--json`, `--yes`, `--dry-run`)
3. THE Builder_CLI SHALL maintain the same exit codes (0, 1, 2, 3)
4. THE Builder_CLI SHALL maintain the same JSON output schema for existing commands
5. WHERE a command is deprecated, THE Builder_CLI SHALL show a deprecation warning with migration instructions

### Requirement 16: Real-Time Dashboard Updates via SSE

**User Story:** As a developer, I want to see live updates in the dashboard without refreshing, so that I can monitor agent progress in real-time.

#### Acceptance Criteria

1. THE Embedded_Server SHALL provide an SSE endpoint at `/api/stream` for real-time updates
2. THE Dashboard SHALL establish an SSE connection on page load
3. WHEN agent progress occurs, THE Embedded_Server SHALL send SSE events to connected clients
4. WHEN task status changes, THE Embedded_Server SHALL send SSE events with the updated task
5. WHEN quality gates complete, THE Embedded_Server SHALL send SSE events with gate results
6. THE SSE connection SHALL automatically reconnect with exponential backoff on disconnect
7. THE Embedded_Server SHALL clean up SSE connections when clients disconnect
8. THE SSE events SHALL include event types: `task_update`, `gate_result`, `agent_progress`, `board_update`

### Requirement 17: Filesystem-Based Knowledge Storage

**User Story:** As a developer, I want project knowledge stored as files, so that I can search and version control it easily.

#### Acceptance Criteria

1. THE Init_Command SHALL create a `.agent-builder/knowledge/` directory for project knowledge
2. THE knowledge SHALL be stored as markdown files with frontmatter metadata
3. THE Builder_CLI SHALL provide a `builder knowledge search <query>` command using grep
4. THE Builder_CLI SHALL provide a `builder knowledge add` command to add knowledge entries
5. THE knowledge files SHALL include tags for categorization
6. THE Builder_CLI SHALL NOT use vector databases or embeddings for knowledge search
7. THE knowledge search SHALL use filesystem tools (grep, find) for querying
