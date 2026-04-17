# Implementation Plan: Project-Level Agent Builder

## Overview

Transform the autonomous-agent-builder from a centralized multi-project system to a project-level, agent-first CLI tool. Implementation follows a phased approach: core infrastructure first (init, embedded server, database), then real-time updates (SSE), script library, knowledge management, configuration system, migration tools, and comprehensive testing.

## Tasks

- [x] 1. Set up embedded resource packaging structure
  - Create `src/autonomous_agent_builder/embedded/` directory structure
  - Create subdirectories: `server/`, `dashboard/`, `scripts/`
  - Update `pyproject.toml` to include embedded resources in package data
  - _Requirements: 1.3, 1.4, 1.5_

- [x] 2. Implement CLI `builder init` command
  - [x] 2.1 Create init command with Typer interface
    - Add command signature with options: `--project-name`, `--language`, `--framework`, `--force`, `--no-input`
    - Implement directory existence check and error handling
    - _Requirements: 1.1, 1.8, 1.9, 2.1, 2.2_
  
  - [x] 2.2 Implement directory structure creation
    - Create `.agent-builder/` directory
    - Create subdirectories: `server/`, `dashboard/`, `scripts/`, `knowledge/`, `migrations/`
    - Copy embedded server code from package resources
    - Copy dashboard assets from package resources
    - Copy script library from package resources
    - _Requirements: 1.1, 1.3, 1.4, 1.5, 17.1_
  
  - [x] 2.3 Implement local database initialization
    - Create SQLite database at `.agent-builder/agent_builder.db`
    - Run Alembic migrations to initialize schema
    - _Requirements: 1.2, 1.7, 3.3, 3.4_
  
  - [x] 2.4 Implement configuration file generation
    - Create default `config.yaml` with project metadata, agent budgets, gate config, server settings
    - Support `--no-input` flag for non-interactive defaults
    - Support `--project-name`, `--language`, `--framework` options
    - _Requirements: 1.6, 2.3, 2.4, 2.5, 13.1, 13.2, 13.3, 13.4_
  
  - [ ]* 2.5 Write unit tests for init command
    - Test directory creation, force flag, no-input flag, error cases
    - _Requirements: 1.1, 1.8, 1.9, 2.1_

- [x] 3. Checkpoint - Verify init command creates correct structure
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement project directory discovery
  - [x] 4.1 Create function to search for `.agent-builder/` directory
    - Search current directory, then parent directories up to filesystem root
    - Return path to `.agent-builder/` or None
    - _Requirements: 3.2, 3.5_
  
  - [x] 4.2 Add error handling with actionable hints
    - Return error message with `builder init` suggestion when not found
    - _Requirements: 3.2, 14.1_
  
  - [ ]* 4.3 Write unit tests for directory discovery
    - Test current directory, parent directory, not found cases
    - _Requirements: 3.2, 3.5_

- [x] 5. Implement embedded FastAPI server
  - [x] 5.1 Create server application factory
    - Implement `create_app()` function that accepts db_path and dashboard_path
    - Initialize database connection with SQLAlchemy
    - Register API routes for features, tasks, gates
    - Mount static files for dashboard assets
    - Implement SPA fallback route
    - _Requirements: 4.1, 4.5, 4.6_
  
  - [x] 5.2 Implement port management utilities
    - Create `find_available_port()` function with range 8000-8010
    - Create `write_port_file()` to save port to `.agent-builder/server.port`
    - Create `read_port_file()` to read saved port
    - _Requirements: 4.2, 4.3, 4.4, 12.1, 12.2, 12.3, 12.4, 12.5_
  
  - [ ]* 5.3 Write unit tests for port management
    - Test port detection, port file read/write, range exhaustion
    - _Requirements: 4.2, 4.3, 4.4, 12.1, 12.2, 12.3_

- [x] 6. Implement CLI `builder start` command
  - [x] 6.1 Create start command with Typer interface
    - Add command signature with options: `--port`, `--host`, `--debug`
    - Search for `.agent-builder/` directory
    - Auto-detect available port or use specified port
    - Write assigned port to `.agent-builder/server.port`
    - Launch uvicorn server with embedded FastAPI app
    - Log server URL to stdout
    - _Requirements: 4.1, 4.2, 4.3, 4.7, 4.8_
  
  - [ ]* 6.2 Write unit tests for start command
    - Test port auto-detection, specified port, error cases
    - _Requirements: 4.1, 4.2, 4.8_

- [x] 7. Checkpoint - Verify server starts and serves dashboard
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Implement SSE infrastructure
  - [x] 8.1 Create SSE event manager
    - Implement event queue registration/unregistration
    - Implement event broadcasting to all connected clients
    - Implement connection cleanup on disconnect
    - _Requirements: 9.4, 9.7, 9.8, 16.7_
  
  - [x] 8.2 Create SSE stream endpoint
    - Implement `/api/stream` GET endpoint
    - Create async event generator with queue
    - Handle client disconnection
    - Send events with types: `task_update`, `gate_result`, `agent_progress`, `board_update`
    - _Requirements: 16.1, 16.3, 16.4, 16.5, 16.8_
  
  - [ ]* 8.3 Write integration tests for SSE
    - Test connection establishment, event delivery, reconnection, cleanup
    - _Requirements: 16.1, 16.2, 16.3, 16.7_

- [x] 9. Implement dashboard SSE client
  - [x] 9.1 Create SSE hook in React
    - Implement `useSSE()` hook with EventSource API
    - Add event listeners for all event types
    - Implement automatic reconnection with exponential backoff
    - Clean up connection on unmount
    - _Requirements: 9.4, 9.7, 16.2, 16.6_
  
  - [x] 9.2 Integrate SSE updates into dashboard pages
    - Update BoardPage to handle `task_update` and `board_update` events
    - Update MetricsPage to handle metric updates
    - Trigger UI updates on SSE events
    - _Requirements: 9.2, 9.3, 9.4, 16.3, 16.4, 16.5_
  
  - [ ]* 9.3 Write integration tests for dashboard SSE
    - Test event reception, UI updates, reconnection behavior
    - _Requirements: 9.4, 16.2, 16.6_

- [x] 10. Checkpoint - Verify real-time updates work end-to-end
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Implement script library base infrastructure
  - [x] 11.1 Create base script interface
    - Define `Script` abstract base class with `run()` and `validate_args()` methods
    - Define standard return format: `{'success': bool, 'data': Any, 'error': str | None}`
    - _Requirements: 8.1, 8.2, 8.3, 8.4_
  
  - [x] 11.2 Create script execution framework
    - Implement script discovery and loading
    - Implement argument parsing and validation
    - Implement error handling and JSON output formatting
    - _Requirements: 8.6, 8.7_
  
  - [ ]* 11.3 Write unit tests for script framework
    - Test script loading, validation, execution, error handling
    - _Requirements: 8.6, 8.7_

- [x] 12. Implement pre-built scripts
  - [x] 12.1 Implement `ask_user.py` script
    - Create script for prompting user input through dashboard
    - Implement validation and response handling
    - _Requirements: 8.1, 9.1_
  
  - [x] 12.2 Implement `create_feature.py` script
    - Create script for feature creation with validation
    - Insert feature into database
    - Trigger SSE `board_update` event
    - _Requirements: 8.1, 8.4, 9.5_
  
  - [x] 12.3 Implement `dispatch_task.py` script
    - Create script for task dispatch through orchestrator
    - Update task status in database
    - Trigger SSE `task_update` event
    - _Requirements: 8.2, 8.4, 9.5_
  
  - [x] 12.4 Implement `update_dashboard.py` script
    - Create script for manual dashboard state updates
    - Trigger appropriate SSE events
    - _Requirements: 8.3, 8.4, 9.5_
  
  - [ ]* 12.5 Write unit tests for pre-built scripts
    - Test each script's validation, execution, database updates, SSE events
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

- [x] 13. Implement CLI `builder script` commands
  - [x] 13.1 Create `builder script list` command
    - List all available scripts in `.agent-builder/scripts/`
    - Show script names and descriptions
    - _Requirements: 8.5_
  
  - [x] 13.2 Create `builder script run` command
    - Execute specified script with arguments
    - Support `--json` flag for JSON output
    - Handle script errors and return appropriate exit codes
    - _Requirements: 8.6, 8.7_
  
  - [ ]* 13.3 Write unit tests for script commands
    - Test list command, run command, JSON output, error handling
    - _Requirements: 8.5, 8.6, 8.7_

- [x] 14. Checkpoint - Verify script library works with SSE updates
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 15. Implement filesystem-based knowledge management
  - [ ] 15.1 Create knowledge file structure
    - Define markdown format with YAML frontmatter (title, tags, created, updated)
    - Implement file naming convention
    - _Requirements: 17.1, 17.2_
  
  - [ ] 15.2 Implement `builder knowledge add` command
    - Create command to add knowledge entries
    - Generate markdown file with frontmatter
    - Support `--tags` option for categorization
    - _Requirements: 17.4, 17.5_
  
  - [ ] 15.3 Implement `builder knowledge search` command
    - Use grep for text search across markdown files
    - Support `--tags` filter option
    - Support `--json` flag for JSON output
    - _Requirements: 17.3, 17.6_
  
  - [ ]* 15.4 Write unit tests for knowledge commands
    - Test add command, search command, tag filtering, JSON output
    - _Requirements: 17.3, 17.4, 17.5_

- [ ] 16. Implement configuration system
  - [ ] 16.1 Create configuration precedence hierarchy
    - Implement config loading from: defaults, system, user, project, env, CLI
    - Implement `Config.get()` method with precedence resolution
    - _Requirements: 13.8_
  
  - [ ] 16.2 Implement environment variable parsing
    - Parse `BUILDER_*` environment variables
    - Map to configuration keys
    - _Requirements: 13.8_
  
  - [ ] 16.3 Implement `builder config show` command
    - Display current configuration with source precedence
    - Support `--json` flag for JSON output
    - _Requirements: 13.6_
  
  - [ ] 16.4 Implement `builder config set` command
    - Update project configuration file
    - Validate configuration values
    - _Requirements: 13.7_
  
  - [ ]* 16.5 Write unit tests for configuration system
    - Test precedence hierarchy, env parsing, show command, set command
    - _Requirements: 13.5, 13.6, 13.7, 13.8_

- [ ] 17. Checkpoint - Verify knowledge and config systems work
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 18. Update existing CLI commands for project-level mode
  - [ ] 18.1 Modify database connection logic
    - Update all commands to use project directory discovery
    - Connect to local SQLite database in `.agent-builder/`
    - Add error handling with actionable hints
    - _Requirements: 3.1, 3.2, 3.5, 14.1_
  
  - [ ] 18.2 Update project isolation logic
    - Ensure commands operate only on current project
    - Remove multi-project filtering logic
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_
  
  - [ ]* 18.3 Write integration tests for updated commands
    - Test all existing commands in project-level mode
    - Verify project isolation
    - _Requirements: 3.1, 10.1, 10.2_

- [ ] 19. Implement agent-first CLI features
  - [ ] 19.1 Implement JSON output mode
    - Add `--json` flag to all commands
    - Auto-detect TTY and default to JSON for non-TTY
    - Ensure consistent JSON schema across commands
    - _Requirements: 5.1, 5.2, 5.3, 15.4_
  
  - [ ] 19.2 Implement output truncation
    - Truncate text output to 2000 characters by default
    - Add truncation marker with `--full` flag hint
    - Add `--full` flag to disable truncation
    - Do not truncate JSON output
    - _Requirements: 7.1, 7.2, 7.3, 7.4_
  
  - [ ] 19.3 Implement non-interactive flags
    - Add `--yes` flag to skip confirmation prompts
    - Add `--dry-run` flag to show actions without executing
    - Add `--no-input` flag to use defaults for all prompts
    - _Requirements: 6.1, 6.2, 6.3, 6.4_
  
  - [ ] 19.4 Implement exit codes
    - Return 0 for success, 1 for general failure, 2 for invalid usage, 3 for connectivity errors
    - _Requirements: 2.6, 2.7, 5.4, 5.5, 5.6, 5.7, 15.3_
  
  - [ ]* 19.5 Write unit tests for agent-first features
    - Test JSON output, TTY detection, truncation, flags, exit codes
    - _Requirements: 5.1, 5.2, 5.3, 7.1, 7.2, 7.3, 6.1, 6.2_

- [ ] 20. Implement error messages with actionable hints
  - [ ] 20.1 Create `BuilderError` exception class
    - Add message and hint attributes
    - Format error output with hint
    - _Requirements: 5.8, 14.1, 14.2, 14.3, 14.4, 14.5_
  
  - [ ] 20.2 Update all error handling to use hints
    - Add hints for: not initialized, database connection, server not running, port in use, validation errors
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5_
  
  - [ ]* 20.3 Write unit tests for error messages
    - Test error formatting, hint inclusion, exit codes
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5_

- [ ] 21. Checkpoint - Verify agent-first CLI features work
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 22. Implement migration from centralized mode
  - [ ] 22.1 Create `builder migrate` command
    - Add command signature with options: `--project-id`, `--target-path`, `--archive`, `--central-db`
    - _Requirements: 11.1_
  
  - [ ] 22.2 Implement project export from central database
    - Connect to central database
    - Export all project data: features, tasks, gates, runs, approvals, security findings
    - _Requirements: 11.1, 11.4_
  
  - [ ] 22.3 Implement project import to local database
    - Initialize target directory with `builder init`
    - Import exported data to local SQLite database
    - Preserve all relationships and timestamps
    - _Requirements: 11.2, 11.3, 11.4_
  
  - [ ] 22.4 Implement archive functionality
    - Mark project as archived in central database when `--archive` flag provided
    - _Requirements: 11.5_
  
  - [ ] 22.5 Implement migration report generation
    - Show what was transferred: counts of features, tasks, gates, runs
    - Show any errors or warnings
    - _Requirements: 11.6_
  
  - [ ]* 22.6 Write integration tests for migration
    - Test export, import, archive, report generation
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6_

- [ ] 23. Implement backward compatibility checks
  - [ ] 23.1 Verify CLI command structure preserved
    - Ensure `builder <resource> <verb>` pattern maintained
    - Ensure flag names preserved: `--json`, `--yes`, `--dry-run`
    - _Requirements: 15.1, 15.2_
  
  - [ ] 23.2 Verify exit codes preserved
    - Ensure exit codes 0, 1, 2, 3 maintained
    - _Requirements: 15.3_
  
  - [ ] 23.3 Verify JSON output schemas preserved
    - Ensure existing commands return same JSON structure
    - _Requirements: 15.4_
  
  - [ ]* 23.4 Write backward compatibility tests
    - Test command structure, flags, exit codes, JSON schemas
    - _Requirements: 15.1, 15.2, 15.3, 15.4_

- [ ] 24. Checkpoint - Verify migration and backward compatibility
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 25. Implement end-to-end SDLC flow tests
  - [ ]* 25.1 Write E2E test for complete project lifecycle
    - Test: init → start → create project → create feature → dispatch task → quality gates → dashboard updates
    - Verify all data in local database
    - Verify SSE events received
    - _Requirements: 3.4, 9.4, 10.1, 16.3, 16.4, 16.5_
  
  - [ ]* 25.2 Write E2E test for multi-project isolation
    - Test two projects in different directories
    - Verify no data leakage between projects
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_
  
  - [ ]* 25.3 Write E2E test for agent script workflow
    - Test agent calling scripts via CLI
    - Verify JSON output parsing
    - Verify dashboard updates via SSE
    - _Requirements: 8.6, 8.7, 9.5_

- [ ] 26. Update package distribution configuration
  - [ ] 26.1 Update pyproject.toml for embedded resources
    - Add package data configuration for `embedded/` directory
    - Include server, dashboard, and scripts in package
    - _Requirements: 1.3, 1.4, 1.5_
  
  - [ ] 26.2 Build and test package installation
    - Build package with `poetry build`
    - Test installation in clean environment
    - Verify embedded resources are included
    - _Requirements: 1.3, 1.4, 1.5_

- [ ] 27. Update documentation
  - [ ] 27.1 Update README with project-level workflow
    - Document installation and initialization
    - Document new commands: init, start, script, knowledge, config, migrate
    - Update architecture diagram
    - _Requirements: 1.1, 4.1, 8.5, 8.6, 11.1, 13.6, 13.7, 17.3, 17.4_
  
  - [ ] 27.2 Create migration guide
    - Document migration process from centralized to project-level
    - Provide examples and troubleshooting
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6_
  
  - [ ] 27.3 Update CLAUDE.md
    - Update commands section with new CLI commands
    - Update architecture section with embedded server and project-level structure
    - Update key files section
    - _Requirements: 1.1, 4.1, 8.5, 13.6, 17.3_

- [ ] 28. Final checkpoint - Complete system verification
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Implementation uses Python with FastAPI, Typer, SQLAlchemy, and React
- Focus on maintaining backward compatibility while adding new project-level features
- SSE provides real-time updates without polling overhead
- Script library minimizes token usage for repetitive agent interactions
