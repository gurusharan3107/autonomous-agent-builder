Perfect. Now I have a clear picture. Let me design the complete production-grade autonomous agent builder system. I'll create a comprehensive architecture plan.

## PRODUCTION-GRADE AUTONOMOUS AGENT BUILDER - ARCHITECTURE DESIGN

### Executive Summary

This design outlines a complete, production-ready autonomous software builder system for Accenture enterprise clients. It spans the full SDLC lifecycle with composable agents, configurable quality gates, and developer approval checkpoints. The system is entirely open-source, supports Java/Node.js/Python, and includes observability, auditability, and isolation-by-default.

---

## 1. SDLC PHASES & AGENT ROLES

### Phase Mapping

```
┌─────────────────────────────────────────────────────────────┐
│                    SDLC Lifecycle                            │
├─────────────────────────────────────────────────────────────┤
│ 1. PLANNING PHASE                                            │
│    └─ Planning Agent (autonomous)                            │
│       • Break feature into implementation tasks              │
│       • Generate design checklist                           │
│       • Estimate scope (token count, complexity)            │
│       → Developer Gate: APPROVE or REQUEST_CHANGES           │
│                                                              │
│ 2. DESIGN PHASE                                             │
│    └─ Design Agent (autonomous)                             │
│       • Generate architecture decision doc                  │
│       • Propose database schema changes                     │
│       • Create API contracts (OpenAPI)                      │
│       • Document non-functional requirements                │
│       → Developer Gate: APPROVE or REJECT                    │
│                                                              │
│ 3. IMPLEMENTATION PHASE                                      │
│    └─ Code Generation Agent (autonomous)                    │
│       • Generate implementation code per task               │
│       • Create unit test scaffolds                          │
│       • Update configuration/docs                           │
│       • Create workspace (git worktree)                      │
│       → Auto-proceed if scoped correctly                     │
│                                                              │
│ 4. QUALITY GATES (automated, no approval)                    │
│    ├─ Code Quality Gate                                      │
│    │  └─ Ruff/ESLint/Checkstyle + complexity               │
│    ├─ Security Gate                                         │
│    │  └─ Semgrep + Trivy + OWASP checks                    │
│    ├─ Testing Gate                                          │
│    │  └─ pytest/Jest/JUnit + coverage                      │
│    ├─ Architecture Gate                                     │
│    │  └─ Circular imports, naming, layering               │
│    └─ Result: PASS, WARN, or FAIL                          │
│       → On FAIL: Auto-retry or escalate                     │
│                                                              │
│ 5. CODE REVIEW PHASE                                        │
│    └─ PR Creation Agent (autonomous)                        │
│       • Create PR with test evidence package                │
│       • Generate summary report (gates, changes)            │
│       • Attach quality metrics and recommendations          │
│       → Developer Gate: APPROVE_AND_MERGE or REQUEST_CHANGES │
│                                                              │
│ 6. INTEGRATION PHASE                                        │
│    └─ Build Verification Agent (autonomous)                 │
│       • Run full build on target branch                     │
│       • Run integration tests                               │
│       • Verify deployment readiness                         │
│       → Auto-proceed or FAIL with logs                      │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Agent Roles (Detailed)

#### 1. **Planning Agent** (autonomous + developer gate)
- **Input**: Feature epic with acceptance criteria
- **Output**: 
  - Task breakdown (ordered by dependency)
  - Design checklist
  - Risk assessment
  - Token estimate
- **Technology**: Claude (via Claude Code CLI)
- **Autonomy**: 100% (but blocked by developer approval)
- **Gate**: Developer approves task breakdown or requests changes

#### 2. **Design Agent** (autonomous + developer gate)
- **Input**: Feature + task context
- **Output**:
  - Architecture Decision Record (ADR)
  - Schema migrations (SQL + ORM models)
  - API contract (OpenAPI 3.0)
  - Dependency graph
  - Non-functional requirements (performance, scalability, security)
- **Technology**: Claude
- **Gate**: Developer approves design or rejects

#### 3. **Code Generation Agent** (autonomous, no gate)
- **Input**: Design doc + task + codebase context
- **Output**:
  - Implementation code (Java/Node/Python)
  - Unit test stubs
  - Integration test stubs
  - Configuration updates
  - Documentation updates
- **Technology**: Claude Code CLI (primary), support for aider/Continue.dev via LiteLLM
- **Workspace**: Git worktree per task (isolated)
- **Gate**: Quality gates (automated)

#### 4. **Quality Gate Runners** (automated, no approval)
- **Code Quality Runner**: Ruff (Python), ESLint (JS), Checkstyle (Java)
- **Security Runner**: Semgrep + Trivy + OWASP checks
- **Testing Runner**: pytest/Jest/JUnit + coverage ≥80%
- **Architecture Runner**: Dependency checks, circular imports, conventions
- **Output**: Structured JSON evidence + PASS/WARN/FAIL
- **Auto-retry**: On WARN, agent fixes. On FAIL, escalate or notify.

#### 5. **PR Creation Agent** (autonomous + developer gate)
- **Input**: Code changes + quality evidence + test results
- **Output**:
  - GitHub/GitLab PR with:
    - Summary section
    - Quality gates table
    - Test coverage report
    - Security findings
    - Performance impact
    - Recommendations
- **Gate**: Developer reviews and approves merge, or requests changes

#### 6. **Build Verification Agent** (autonomous, no gate)
- **Input**: Merged code
- **Output**:
  - Build log (success/fail)
  - Integration test results
  - Artifact link
  - Deployment readiness
- **On Fail**: Notifies team, blocks deployment

---

## 2. BOARD SYSTEM (Self-Hosted Work Item Tracker)

### Design Principles
- **Zero SaaS**: SQLite for local dev, PostgreSQL for prod
- **REST-first**: All operations via API
- **Minimal UI**: HTMX + vanilla JS (no React SPA overhead)
- **Git-native**: Each board item links to git commits/PRs
- **Audit trail**: Every state change logged

### Data Model

```sql
-- Core Work Items
CREATE TABLE projects (
    id UUID PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    repo_url TEXT,
    primary_language TEXT,  -- java, python, typescript
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE features (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id),
    title TEXT NOT NULL,
    description TEXT,
    acceptance_criteria TEXT[],  -- JSON array
    status TEXT DEFAULT 'BACKLOG',
    -- Statuses: BACKLOG → PLANNING → APPROVED → DESIGNING → DESIGNED 
    -- → IMPLEMENTING → IMPLEMENTED → TESTING → TESTED → REVIEWING 
    -- → APPROVED_FOR_MERGE → MERGED → DEPLOYED
    priority INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(project_id, title)
);

CREATE TABLE tasks (
    id UUID PRIMARY KEY,
    feature_id UUID NOT NULL REFERENCES features(id),
    title TEXT NOT NULL,
    description TEXT,
    task_type TEXT,  -- 'DESIGN', 'IMPLEMENTATION', 'TEST', 'REFACTOR'
    status TEXT DEFAULT 'PENDING',
    -- Statuses: PENDING → IN_PROGRESS → REVIEW_PENDING → APPROVED 
    -- → MERGED → DEPLOYED
    sequence INTEGER,  -- execution order
    depends_on UUID REFERENCES tasks(id),
    estimated_tokens INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(feature_id, title)
);

-- Quality Gate Configuration & Results
CREATE TABLE quality_gates (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id),
    gate_type TEXT,  -- 'CODE_QUALITY', 'SECURITY', 'TESTING', 'ARCHITECTURE'
    name TEXT,  -- e.g., 'ruff-linting', 'semgrep-sast'
    enabled BOOLEAN DEFAULT true,
    config JSONB,  -- tool-specific config
    thresholds JSONB,  -- pass/warn/fail criteria
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE gate_results (
    id UUID PRIMARY KEY,
    task_id UUID NOT NULL REFERENCES tasks(id),
    gate_id UUID NOT NULL REFERENCES quality_gates(id),
    status TEXT,  -- 'PASS', 'WARN', 'FAIL'
    score FLOAT,  -- 0-100
    summary TEXT,
    evidence JSONB,  -- tool output, metrics, etc.
    created_at TIMESTAMP DEFAULT NOW()
);

-- Developer Approval Gates
CREATE TABLE approval_gates (
    id UUID PRIMARY KEY,
    task_id UUID NOT NULL REFERENCES tasks(id),
    gate_name TEXT,  -- 'PLANNING_REVIEW', 'DESIGN_REVIEW', 'PR_REVIEW'
    required_approvers INTEGER DEFAULT 1,
    status TEXT DEFAULT 'PENDING',  -- PENDING, APPROVED, REJECTED
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE approvals (
    id UUID PRIMARY KEY,
    gate_id UUID NOT NULL REFERENCES approval_gates(id),
    approver_email TEXT NOT NULL,
    decision TEXT,  -- 'APPROVE', 'APPROVE_WITH_SUGGESTIONS', 'REJECT'
    feedback TEXT,
    approved_at TIMESTAMP DEFAULT NOW()
);

-- Agent Runs & Workspace Tracking
CREATE TABLE agent_runs (
    id UUID PRIMARY KEY,
    task_id UUID NOT NULL REFERENCES tasks(id),
    agent_type TEXT,  -- 'PLANNING', 'DESIGN', 'CODE_GEN', 'PR_CREATION', 'BUILD_VERIFY'
    status TEXT DEFAULT 'RUNNING',  -- RUNNING, SUCCESS, FAILED, RETRY_QUEUED
    prompt TEXT,
    response_summary TEXT,
    tokens_used INTEGER,
    tokens_cached INTEGER,
    cost_usd DECIMAL(10, 4),
    started_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP,
    error_message TEXT
);

CREATE TABLE agent_run_events (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES agent_runs(id),
    event_type TEXT,  -- 'START', 'STREAM_CHUNK', 'TOOL_CALL', 'COMPLETION', 'ERROR'
    timestamp TIMESTAMP DEFAULT NOW(),
    details JSONB
);

CREATE TABLE workspaces (
    id UUID PRIMARY KEY,
    task_id UUID NOT NULL REFERENCES tasks(id),
    workspace_path TEXT UNIQUE NOT NULL,  -- git worktree path
    base_branch TEXT,
    worktree_branch TEXT,
    status TEXT DEFAULT 'CREATED',  -- CREATED, ACTIVE, RELEASED, ARCHIVED
    created_at TIMESTAMP DEFAULT NOW(),
    released_at TIMESTAMP
);
```

### REST API Endpoints

```
PROJECT MANAGEMENT
  POST   /api/projects
  GET    /api/projects
  GET    /api/projects/{id}
  PUT    /api/projects/{id}
  POST   /api/projects/{id}/sync-repo       # Sync git metadata

FEATURES (Board)
  POST   /api/features
  GET    /api/projects/{id}/features        # List with status counts
  GET    /api/features/{id}
  PUT    /api/features/{id}                 # Update status
  DELETE /api/features/{id}

TASKS
  POST   /api/features/{id}/tasks
  GET    /api/features/{id}/tasks
  GET    /api/tasks/{id}
  PUT    /api/tasks/{id}                    # Update status
  POST   /api/tasks/{id}/request-review     # Trigger approval gate

QUALITY GATES
  POST   /api/projects/{id}/quality-gates
  GET    /api/projects/{id}/quality-gates
  PUT    /api/quality-gates/{id}            # Update config
  GET    /api/quality-gates/{id}/results    # Recent results

GATE RESULTS
  GET    /api/tasks/{id}/gate-results       # All gates for task

APPROVALS
  GET    /api/approval-gates/{id}           # Pending approvals
  POST   /api/approvals                      # Submit approval
  GET    /api/approvals?pending=true        # List pending

AGENT RUNS
  GET    /api/tasks/{id}/runs               # Runs for task
  GET    /api/runs/{id}                     # Details + events
  POST   /api/runs/{id}/retry               # Retry failed run

WORKSPACES
  GET    /api/tasks/{id}/workspace
  POST   /api/tasks/{id}/workspace/release  # Release worktree

BOARD DASHBOARD
  GET    /api/projects/{id}/board           # Summary view
    Returns: { features: [...], stats: {...} }

REPORTS
  GET    /api/projects/{id}/metrics         # Quality metrics over time
  GET    /api/projects/{id}/cost-report     # Token spend
```

### Web Dashboard (HTMX-based)

```
Key Pages:
1. /dashboard/projects          — List projects, create new
2. /dashboard/{project}/board    — Kanban-style board view
   - Columns: BACKLOG | PLANNING | APPROVED | DESIGNING | 
             DESIGNED | IMPLEMENTING | TESTING | REVIEWING | DEPLOYED
   - Each card shows: title, assignee, priority, last gate status
   - Click → detail modal with full history

3. /dashboard/{project}/tasks/{task}    — Task detail
   - Status flow with timestamps
   - Agent run logs (streaming)
   - Quality gate results (collapsible)
   - PR link (when available)
   - Approval gate UI (for reviewers)

4. /dashboard/approvals          — Pending approvals inbox
   - Filter by type (PLANNING_REVIEW, DESIGN_REVIEW, PR_REVIEW)
   - Show summary + diff preview
   - Approve/Reject form

5. /dashboard/{project}/metrics   — Analytics
   - Feature cycle time (days)
   - Quality gate pass rates
   - Agent token spend
   - Cost vs. velocity
```

---

## 3. QUALITY GATE FRAMEWORK

### Gate Architecture

Each gate is a pluggable module implementing this interface:

```python
class QualityGate(ABC):
    """Base interface for all quality gates."""
    
    gate_type: str  # e.g., 'CODE_QUALITY', 'SECURITY'
    name: str       # e.g., 'ruff-linting'
    
    def configure(self, config: dict) -> None:
        """Load tool config (thresholds, patterns, etc.)."""
        pass
    
    def run(self, workspace_path: str) -> GateResult:
        """Execute gate on codebase. Return structured evidence."""
        pass
    
    def remediate(self, workspace_path: str) -> bool:
        """Attempt auto-fix. Return True if successful."""
        pass

@dataclass
class GateResult:
    status: str  # 'PASS', 'WARN', 'FAIL'
    score: float  # 0-100
    summary: str
    evidence: dict  # Tool-specific output
    remediation_possible: bool
    recommendations: list[str]
```

### Gate Implementations

#### **Code Quality Gate**

```python
class CodeQualityGate(QualityGate):
    gate_type = "CODE_QUALITY"
    name = "code-quality"
    
    tools: dict = {
        "python": {
            "name": "ruff",
            "config": "pyproject.toml",
            "check_cmd": ["ruff", "check", "."],
            "fix_cmd": ["ruff", "format", "."],
        },
        "typescript": {
            "name": "eslint",
            "config": ".eslintrc.json",
            "check_cmd": ["eslint", ".", "--format", "json"],
            "fix_cmd": ["eslint", ".", "--fix"],
        },
        "java": {
            "name": "checkstyle",
            "config": "checkstyle.xml",
            "check_cmd": ["mvn", "checkstyle:check"],
            "fix_cmd": None,  # No auto-fix
        },
    }
    
    complexity_tools: dict = {
        "python": {"name": "radon", "threshold": 10},  # cyclomatic complexity
        "typescript": {"name": "plato", "threshold": 10},
        "java": {"name": "pmd", "threshold": 10},
    }
    
    def run(self, workspace_path: str) -> GateResult:
        # 1. Detect language
        # 2. Run linter + capture output
        # 3. Run complexity analyzer
        # 4. Aggregate scores
        # 5. Return GateResult
        pass
```

**Evidence JSON**:
```json
{
  "linter": {
    "tool": "ruff",
    "violations": [
      {
        "file": "src/main.py",
        "line": 42,
        "rule": "E501",
        "message": "line too long (105 > 100)"
      }
    ],
    "total_violations": 3,
    "errors": 0,
    "warnings": 3
  },
  "complexity": {
    "tool": "radon",
    "functions": [
      {
        "name": "parse_config",
        "complexity": 12,
        "status": "FAIL"  # threshold 10
      }
    ]
  },
  "score": 75  # 100 - (violations + complexity issues)
}
```

#### **Security Gate**

```python
class SecurityGate(QualityGate):
    gate_type = "SECURITY"
    name = "security"
    
    def run(self, workspace_path: str) -> GateResult:
        results = {}
        
        # 1. SAST (Static Application Security Testing)
        results["sast"] = self._run_semgrep(workspace_path)
        
        # 2. Dependency Scanning
        results["dependencies"] = self._run_trivy(workspace_path)
        
        # 3. OWASP Checks
        results["owasp"] = self._check_owasp_patterns(workspace_path)
        
        return GateResult(
            status=self._aggregate_severity(results),
            score=self._calculate_security_score(results),
            evidence=results,
            remediation_possible=self._can_remediate(results),
        )
    
    def _run_semgrep(self, workspace_path: str) -> dict:
        """Run Semgrep SAST tool."""
        cmd = ["semgrep", "--json", "--config=p/owasp-top-ten", workspace_path]
        # Returns: { "findings": [...], "stats": {...} }
        pass
    
    def _run_trivy(self, workspace_path: str) -> dict:
        """Run Trivy for dependency scanning."""
        cmd = ["trivy", "fs", "--format", "json", workspace_path]
        # Returns: { "vulnerabilities": [...], "severity_counts": {...} }
        pass
```

**Evidence JSON**:
```json
{
  "sast": {
    "tool": "semgrep",
    "findings": [
      {
        "rule_id": "python.lang.security.injection.sql-injection",
        "severity": "CRITICAL",
        "file": "src/db.py",
        "line": 15,
        "code": "query = f\"SELECT * FROM users WHERE id = {user_id}\"",
        "fix": "Use parameterized queries"
      }
    ],
    "stats": { "critical": 1, "high": 2, "medium": 4 }
  },
  "dependencies": {
    "tool": "trivy",
    "vulnerabilities": [
      {
        "package": "requests",
        "version": "2.25.0",
        "vulnerability_id": "CVE-2021-28363",
        "severity": "HIGH",
        "fix_version": "2.28.0"
      }
    ],
    "stats": { "critical": 0, "high": 1, "medium": 0 }
  },
  "owasp": {
    "checks": [
      {
        "category": "A01:2021 - Broken Access Control",
        "status": "PASS",
        "details": "No hardcoded credentials found"
      }
    ]
  },
  "score": 45  # Based on severity counts
}
```

#### **Testing Gate**

```python
class TestingGate(QualityGate):
    gate_type = "TESTING"
    name = "testing"
    
    def run(self, workspace_path: str) -> GateResult:
        # 1. Detect language + test framework
        # 2. Run tests: pytest / jest / junit
        # 3. Measure coverage
        # 4. Check threshold (default ≥80%)
        pass

# Evidence JSON
{
  "tests": {
    "tool": "pytest",
    "total": 48,
    "passed": 46,
    "failed": 2,
    "skipped": 0,
    "duration_seconds": 12.5,
    "failures": [
      {
        "test": "test_auth_with_invalid_token",
        "error": "AssertionError: Expected 401, got 200"
      }
    ]
  },
  "coverage": {
    "lines": 87.5,
    "branches": 72.0,
    "functions": 91.0,
    "threshold": 80.0,
    "status": "PASS",
    "uncovered_lines": "src/migrations.py:10-25"
  },
  "score": 82
}
```

#### **Architecture Gate**

```python
class ArchitectureGate(QualityGate):
    gate_type = "ARCHITECTURE"
    name = "architecture"
    
    def run(self, workspace_path: str) -> GateResult:
        checks = {}
        
        # 1. Circular import detection
        checks["circular_imports"] = self._check_circular_imports(workspace_path)
        
        # 2. Layer violations
        checks["layer_violations"] = self._check_layer_violations(workspace_path)
        
        # 3. Naming conventions
        checks["naming"] = self._check_naming_conventions(workspace_path)
        
        # 4. Dependency graph
        checks["dependencies"] = self._analyze_dependency_graph(workspace_path)
        
        return GateResult(
            status=self._determine_status(checks),
            score=self._calculate_architecture_score(checks),
            evidence=checks,
            remediation_possible=False,  # Usually requires manual intervention
        )
```

### Gate Configuration (per-project)

```yaml
# .agent-builder/quality-gates.yaml
project:
  language: python
  
gates:
  code-quality:
    enabled: true
    thresholds:
      violations: 5  # warn if > 5
      complexity: 10  # cyclomatic complexity
    config:
      ruff:
        line-length: 100
        ignore: [D100, D104]  # ignore certain rules
  
  security:
    enabled: true
    thresholds:
      critical: 0  # fail if > 0 critical
      high: 1      # warn if > 1 high
    config:
      semgrep:
        rules: [p/owasp-top-ten, p/security-audit]
      trivy:
        severity: [HIGH, CRITICAL]
  
  testing:
    enabled: true
    thresholds:
      coverage: 80
      failure_rate: 0.05  # warn if > 5% fail
    config:
      pytest:
        min_python_version: 3.11
  
  architecture:
    enabled: true
    config:
      layer_rules:
        - layer: presentation
          can_import: [services]
        - layer: services
          can_import: [models, repositories, utils]
        - layer: models
          can_import: []
```

### Auto-Remediation Flow

```
Gate Result: WARN or FAIL
   ↓
Can remediate? (auto_fix_cmd exists)
   ├─ YES: Attempt remediation
   │   ├─ Success: Re-run gate, verify PASS
   │   │   └─ Continue pipeline
   │   └─ Failure: Escalate to Code Gen Agent
   │       └─ Agent reviews and fixes manually
   └─ NO: 
       ├─ WARN: Log as advisory, continue
       └─ FAIL: Block and notify team
```

---

## 4. AGENT RUNNER (Workspace Isolation & Execution)

### Runner Protocol

```python
class AgentRunner(ABC):
    """Base interface for agent execution."""
    
    @abstractmethod
    async def run(
        self,
        task: Task,
        prompt: str,
        context: AgentContext,
        callbacks: RunCallbacks,
    ) -> RunResult:
        """
        Execute agent with given prompt.
        - Stream output via callbacks
        - Track tokens, cost
        - Handle timeouts & retries
        """
        pass

@dataclass
class AgentContext:
    workspace_path: str
    task: Task
    project: Project
    codebase_summary: str  # LLM-friendly overview
    prior_runs: list[AgentRun]  # conversation history
    git_diff: str  # changes so far
    
@dataclass
class RunCallbacks:
    on_token: Callable[[str], None]  # Stream output
    on_error: Callable[[str], None]
    on_tool_call: Callable[[ToolCall], None]

@dataclass
class RunResult:
    status: str  # 'SUCCESS', 'FAILED', 'TIMEOUT', 'PARTIAL'
    output: str
    tokens_used: int
    tokens_cached: int
    cost_usd: Decimal
    artifacts: list[Artifact]  # Generated files
    error: Optional[str]
```

### Implementations

#### **Claude Code CLI Runner** (Primary)

```python
class ClaudeCodeRunner(AgentRunner):
    """Executes agents via Claude Code CLI."""
    
    async def run(
        self,
        task: Task,
        prompt: str,
        context: AgentContext,
        callbacks: RunCallbacks,
    ) -> RunResult:
        # 1. Build prompt with context
        full_prompt = self._build_prompt(task, context)
        
        # 2. Spawn claude-code subprocess
        process = await asyncio.create_subprocess_exec(
            "claude-code",
            "--task", task.id,
            "--workspace", context.workspace_path,
            "--stream",
            "--timeout", "900s",  # 15 min
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        # 3. Stream prompt, collect output
        tokens_used = 0
        output_lines = []
        
        async for line in process.stdout:
            callbacks.on_token(line.decode())
            output_lines.append(line)
            # Parse token count from headers
        
        # 4. Await completion
        _, stderr = await process.communicate()
        
        return RunResult(
            status='SUCCESS' if process.returncode == 0 else 'FAILED',
            output=''.join(output_lines),
            tokens_used=tokens_used,
            artifacts=self._extract_artifacts(context.workspace_path),
        )
```

#### **LiteLLM Router** (for aider, Continue.dev, etc.)

```python
class LiteLLMRunner(AgentRunner):
    """Routes to any LLM via LiteLLM (OpenAI, Anthropic, etc.)."""
    
    def __init__(self, model: str, provider: str):
        self.client = litellm.Completion(
            model=model,  # "gpt-4", "claude-3-sonnet", etc.
            api_key=os.getenv(f"{provider.upper()}_API_KEY"),
        )
    
    async def run(
        self,
        task: Task,
        prompt: str,
        context: AgentContext,
        callbacks: RunCallbacks,
    ) -> RunResult:
        # 1. Build prompt
        full_prompt = self._build_prompt(task, context)
        
        # 2. Call LLM via LiteLLM
        response = await self.client.acompletion(
            messages=[{"role": "user", "content": full_prompt}],
            stream=True,
            temperature=0.2,
            max_tokens=4000,
        )
        
        # 3. Stream and parse
        output = ""
        async for chunk in response:
            delta = chunk.choices[0].delta.content
            callbacks.on_token(delta)
            output += delta
        
        # 4. Execute output (code fixes, commits, etc.)
        return RunResult(...)
```

### Workspace Isolation (Git Worktrees)

```python
class WorkspaceManager:
    """Manages isolated worktrees per task."""
    
    async def create_workspace(self, task: Task) -> Workspace:
        """
        1. Create git worktree for task
        2. Check out feature branch
        3. Link to database
        """
        worktree_branch = f"feature/{task.id}-{slugify(task.title)}"
        worktree_path = f"./.claude/worktrees/{worktree_branch}"
        
        # Create worktree from main/develop
        subprocess.run([
            "git", "worktree", "add",
            "-b", worktree_branch,
            worktree_path,
            "origin/develop",
        ])
        
        # Record in database
        workspace = Workspace(
            task_id=task.id,
            workspace_path=worktree_path,
            base_branch="develop",
            worktree_branch=worktree_branch,
            status="CREATED",
        )
        db.session.add(workspace)
        db.session.commit()
        
        return workspace
    
    async def release_workspace(self, workspace: Workspace):
        """
        1. Verify all changes committed
        2. Push to remote
        3. Clean up worktree
        """
        # Verify no uncommitted changes
        result = subprocess.run(
            ["git", "-C", workspace.workspace_path, "status", "--porcelain"],
            capture_output=True,
            text=True,
        )
        if result.stdout:
            raise ValueError("Uncommitted changes in workspace")
        
        # Push to remote
        subprocess.run([
            "git", "-C", workspace.workspace_path,
            "push", "-u", "origin", workspace.worktree_branch,
        ])
        
        # Remove worktree
        subprocess.run(["git", "worktree", "remove", workspace.workspace_path])
        
        workspace.status = "RELEASED"
        workspace.released_at = datetime.utcnow()
        db.session.commit()
```

### Prompt Templates

```python
# templates/planning_agent.txt
You are a sprint planning expert for {project.name} ({project.primary_language}).

FEATURE:
{feature.title}

ACCEPTANCE CRITERIA:
{feature.acceptance_criteria}

CODEBASE CONTEXT:
{codebase_summary}

YOUR TASK:
Break this feature into implementation tasks. For each task:
1. Title and description
2. Estimated complexity (low/medium/high)
3. Dependencies (if any)
4. Type (DESIGN, IMPLEMENTATION, TEST, REFACTOR)

OUTPUT FORMAT:
Return ONLY valid JSON:
{
  "tasks": [
    {
      "title": "...",
      "description": "...",
      "complexity": "high",
      "type": "DESIGN",
      "depends_on": null
    }
  ]
}

---

# templates/design_agent.txt
You are a senior architect for {project.name} ({project.primary_language}).

TASK:
{task.title}

FEATURE CONTEXT:
{feature.description}

CODEBASE OVERVIEW:
{codebase_summary}

YOUR RESPONSIBILITIES:
1. Design the architecture for this feature
2. Generate database schema changes (SQL + ORM migrations)
3. Define API contracts (OpenAPI 3.0)
4. Document non-functional requirements
5. Identify risks and mitigation strategies

OUTPUT FORMAT:
Return a structured design document containing:
- Architecture diagram (ASCII or Mermaid)
- Schema changes
- API contract (JSON)
- Requirements

---

# templates/code_gen_agent.txt
You are an expert code generator for {project.primary_language}.

WORKSPACE: {context.workspace_path}

TASK:
{task.title}

DESIGN REFERENCE:
{prior_design_doc}

ACCEPTANCE CRITERIA:
{feature.acceptance_criteria}

EXISTING CODEBASE:
{codebase_summary}

YOUR RESPONSIBILITIES:
1. Implement the feature according to the design
2. Write unit tests (minimum 80% coverage)
3. Update configuration files
4. Commit changes with clear messages

CONSTRAINTS:
- Follow existing code style and patterns
- Use the existing testing framework
- Ensure no circular imports
- Write descriptive commit messages

OUTPUT:
Work in the git worktree: {context.workspace_path}
When done, stage and commit all changes.
```

---

## 5. ORCHESTRATOR

### Orchestrator Loop (Inspired by Symphony)

```python
class Orchestrator:
    """Main orchestration engine. Polls board, dispatches agents, manages lifecycle."""
    
    def __init__(
        self,
        board: BoardService,
        agent_runners: dict[str, AgentRunner],
        quality_gates: dict[str, QualityGate],
    ):
        self.board = board
        self.agents = agent_runners
        self.gates = quality_gates
        self.concurrency_limit = 3  # Max 3 parallel agent runs
        self.retry_config = {
            "max_retries": 2,
            "backoff_factor": 2,  # exponential: 30s, 60s
        }
    
    async def run_loop(self):
        """Main orchestrator loop (runs continuously)."""
        while True:
            try:
                # 1. Poll for ready work items
                ready_tasks = await self.board.get_ready_tasks(limit=10)
                
                # 2. Respect concurrency limits
                active_runs = await self.board.get_active_runs()
                available_slots = self.concurrency_limit - len(active_runs)
                
                for task in ready_tasks[:available_slots]:
                    # 3. Dispatch task
                    asyncio.create_task(self._process_task(task))
                
                # 4. Reconcile stale runs (>30 min without activity)
                await self._reconcile_stale_runs()
                
                # 5. Sleep until next poll
                await asyncio.sleep(30)
            
            except Exception as e:
                logger.error(f"Orchestrator loop error: {e}")
                await asyncio.sleep(60)
    
    async def _process_task(self, task: Task):
        """Process a single task through all required phases."""
        try:
            logger.info(f"Processing task {task.id}: {task.title}")
            
            # Phase 1: Planning (if feature in BACKLOG)
            if task.feature.status == "BACKLOG":
                await self._run_planning_phase(task.feature)
            
            # Phase 2: Design (if feature in DESIGNING)
            if task.feature.status == "DESIGNING":
                await self._run_design_phase(task)
            
            # Phase 3: Implementation (if task in PENDING)
            if task.status == "PENDING":
                await self._run_implementation_phase(task)
            
            # Phase 4: Quality Gates (after code generation)
            if task.status == "IN_PROGRESS":
                gate_results = await self._run_quality_gates(task)
                if self._gates_pass(gate_results):
                    task.status = "TESTING"
                else:
                    # Auto-remediate or escalate
                    await self._handle_gate_failures(task, gate_results)
            
            # Phase 5: PR Creation (if code ready)
            if task.status == "TESTING":
                pr_info = await self._run_pr_creation_phase(task)
                task.status = "REVIEW_PENDING"
            
            # Phase 6: Build Verification (if merged)
            if task.status == "APPROVED_FOR_MERGE":
                await self._run_build_verification(task)
            
            await self.board.update_task(task)
        
        except Exception as e:
            logger.error(f"Task processing error: {e}")
            await self._handle_task_error(task, e)
    
    async def _run_planning_phase(self, feature: Feature):
        """Planning Agent: break feature into tasks."""
        runner = self.agents["claude-code"]
        
        prompt = self._load_template("planning_agent.txt").format(
            project=feature.project,
            feature=feature,
            codebase_summary=await self._get_codebase_summary(feature.project),
        )
        
        context = AgentContext(
            workspace_path=feature.project.repo_url,
            task=None,
            project=feature.project,
            codebase_summary=await self._get_codebase_summary(feature.project),
            prior_runs=[],
        )
        
        run = await runner.run(None, prompt, context, self._make_callbacks(feature.id))
        
        # Parse task breakdown from JSON
        task_data = json.loads(run.output)
        for task_spec in task_data["tasks"]:
            task = Task(
                feature_id=feature.id,
                title=task_spec["title"],
                description=task_spec["description"],
                task_type=task_spec["type"],
                sequence=len(feature.tasks) + 1,
                estimated_tokens=self._estimate_tokens(task_spec["description"]),
            )
            await self.board.create_task(task)
        
        # Mark feature as PLANNING_REVIEW (developer approval gate)
        approval = ApprovalGate(
            feature_id=feature.id,
            gate_name="PLANNING_REVIEW",
            status="PENDING",
        )
        await self.board.create_approval_gate(approval)
        
        feature.status = "PLANNING"
        await self.board.update_feature(feature)
    
    async def _run_design_phase(self, task: Task):
        """Design Agent: create architecture, schema, API contract."""
        runner = self.agents["claude-code"]
        
        # Check if prior design exists (for multiple tasks under same feature)
        prior_design = await self.board.get_feature_design(task.feature_id)
        
        prompt = self._load_template("design_agent.txt").format(
            project=task.project,
            task=task,
            feature=task.feature,
            codebase_summary=await self._get_codebase_summary(task.project),
            prior_design=prior_design.design_doc if prior_design else "",
        )
        
        run = await runner.run(task, prompt, ..., self._make_callbacks(task.id))
        
        # Save design document
        design_doc = DesignDocument(
            feature_id=task.feature_id,
            design_doc=run.output,
            created_at=datetime.utcnow(),
        )
        await self.board.save_design_document(design_doc)
        
        # Mark task as DESIGN_REVIEW (developer approval gate)
        approval = ApprovalGate(
            task_id=task.id,
            gate_name="DESIGN_REVIEW",
            status="PENDING",
        )
        await self.board.create_approval_gate(approval)
        
        task.status = "REVIEW_PENDING"
        await self.board.update_task(task)
    
    async def _run_implementation_phase(self, task: Task):
        """Code Generation Agent: implement feature in isolated workspace."""
        runner = self.agents["claude-code"]
        
        # Create workspace
        workspace = await self._workspace_manager.create_workspace(task)
        
        # Get design reference
        design_doc = await self.board.get_feature_design(task.feature_id)
        
        prompt = self._load_template("code_gen_agent.txt").format(
            project=task.project.primary_language,
            workspace=workspace.workspace_path,
            task=task,
            design=design_doc.design_doc if design_doc else "",
            feature=task.feature,
            codebase_summary=await self._get_codebase_summary(task.project),
        )
        
        run = await runner.run(task, prompt, ..., self._make_callbacks(task.id))
        
        # Extract generated artifacts
        artifacts = self._extract_artifacts_from_workspace(workspace.workspace_path)
        
        task.status = "IN_PROGRESS"
        workspace.status = "ACTIVE"
        await self.board.update_task(task)
    
    async def _run_quality_gates(self, task: Task) -> list[GateResult]:
        """Run all configured quality gates."""
        workspace = await self.board.get_workspace(task.id)
        results = []
        
        for gate_name, gate in self.gates.items():
            if not await self.board.is_gate_enabled(task.project_id, gate_name):
                continue
            
            logger.info(f"Running {gate_name} gate for task {task.id}")
            result = gate.run(workspace.workspace_path)
            
            # Save result
            gate_result = GateResult(
                task_id=task.id,
                gate_id=gate.id,
                status=result.status,
                score=result.score,
                evidence=result.evidence,
            )
            await self.board.save_gate_result(gate_result)
            results.append(result)
        
        return results
    
    async def _handle_gate_failures(self, task: Task, results: list[GateResult]):
        """Auto-remediate or escalate failed gates."""
        failed = [r for r in results if r.status == "FAIL"]
        
        for result in failed:
            gate = self.gates[result.gate_name]
            
            if result.remediation_possible:
                logger.info(f"Attempting auto-remediation for {result.gate_name}")
                success = gate.remediate(task.workspace.workspace_path)
                
                if success:
                    # Re-run gate
                    new_result = gate.run(task.workspace.workspace_path)
                    if new_result.status != "FAIL":
                        logger.info(f"Auto-remediation succeeded for {result.gate_name}")
                        continue
            
            # Escalate: notify team
            logger.error(f"Gate {result.gate_name} failed and cannot auto-remediate")
            await self._notify_team(
                task,
                f"Quality gate '{result.gate_name}' failed with score {result.score}",
                result.evidence,
            )
            task.status = "GATE_FAILURE"
    
    async def _run_pr_creation_phase(self, task: Task):
        """PR Creation Agent: create PR with evidence package."""
        runner = self.agents["claude-code"]
        
        # Collect evidence
        gate_results = await self.board.get_gate_results(task.id)
        
        prompt = self._load_template("pr_creation_agent.txt").format(
            task=task,
            feature=task.feature,
            gate_results=self._format_gate_results(gate_results),
            diff=await self._get_git_diff(task.workspace.workspace_path),
        )
        
        run = await runner.run(task, prompt, ..., self._make_callbacks(task.id))
        
        # Extract PR info from output and create PR
        pr_info = self._parse_pr_info(run.output)
        
        task.pr_number = pr_info["number"]
        task.pr_url = pr_info["url"]
        task.status = "REVIEW_PENDING"
        
        # Mark task as PR_REVIEW (developer approval gate)
        approval = ApprovalGate(
            task_id=task.id,
            gate_name="PR_REVIEW",
            status="PENDING",
        )
        await self.board.create_approval_gate(approval)
        
        return pr_info
    
    async def _run_build_verification(self, task: Task):
        """Build Verification Agent: verify build + integration tests."""
        workspace = await self.board.get_workspace(task.id)
        
        # Detect build system
        build_cmd = self._detect_build_command(workspace.workspace_path, task.project)
        
        logger.info(f"Running build: {build_cmd}")
        result = subprocess.run(
            build_cmd,
            cwd=workspace.workspace_path,
            capture_output=True,
            text=True,
            timeout=300,  # 5 min
        )
        
        if result.returncode == 0:
            logger.info("Build succeeded")
            task.status = "DEPLOYED"
        else:
            logger.error(f"Build failed: {result.stderr}")
            task.status = "BUILD_FAILURE"
            await self._notify_team(task, "Build verification failed", result.stderr)
    
    async def _reconcile_stale_runs(self):
        """Detect and handle stale agent runs (>30 min without activity)."""
        stale_runs = await self.board.get_stale_runs(minutes=30)
        
        for run in stale_runs:
            logger.warning(f"Run {run.id} is stale, attempting recovery...")
            
            if run.retry_count < self.retry_config["max_retries"]:
                # Retry with exponential backoff
                backoff_seconds = 30 * (2 ** run.retry_count)
                await asyncio.sleep(backoff_seconds)
                
                run.status = "RETRY_QUEUED"
                run.retry_count += 1
                await self.board.update_run(run)
            else:
                # Give up
                run.status = "FAILED"
                run.error_message = "Max retries exceeded"
                await self.board.update_run(run)
                await self._notify_team(None, f"Task {run.task_id} exceeded max retries")
```

### Lifecycle Hooks

```python
class LifecycleHooks:
    """Execute custom code at key orchestrator events."""
    
    async def before_run(self, task: Task, phase: str):
        """Called before agent run."""
        # Example: notify Slack
        pass
    
    async def after_run(self, task: Task, phase: str, result: RunResult):
        """Called after agent run completion."""
        # Example: save artifacts to S3
        pass
    
    async def after_gate(self, task: Task, gate_result: GateResult):
        """Called after quality gate."""
        # Example: report to monitoring system
        pass
    
    async def on_approval(self, task: Task, gate: ApprovalGate):
        """Called when developer approves."""
        pass
```

---

## 6. DATA MODEL (Complete)

### SQLAlchemy Models

```python
# models/project.py
class Project(Base):
    __tablename__ = "projects"
    
    id = Column(UUID, primary_key=True, default=uuid4)
    slug = Column(String(50), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    repo_url = Column(String(500))
    repo_provider = Column(String(20))  # 'github', 'gitlab', 'gitea'
    primary_language = Column(String(20))  # java, python, typescript
    created_at = Column(DateTime, default=datetime.utcnow)
    
    features = relationship("Feature", back_populates="project")
    quality_gates = relationship("QualityGate", back_populates="project")
    agent_runs = relationship("AgentRun", back_populates="project")

# models/feature.py
class Feature(Base):
    __tablename__ = "features"
    
    id = Column(UUID, primary_key=True, default=uuid4)
    project_id = Column(UUID, ForeignKey("projects.id"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    acceptance_criteria = Column(JSON)
    status = Column(String(50), default="BACKLOG")
    priority = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
    
    project = relationship("Project", back_populates="features")
    tasks = relationship("Task", back_populates="feature", cascade="all, delete")
    design_document = relationship("DesignDocument", uselist=False, back_populates="feature")

# models/task.py
class Task(Base):
    __tablename__ = "tasks"
    
    id = Column(UUID, primary_key=True, default=uuid4)
    feature_id = Column(UUID, ForeignKey("features.id"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    task_type = Column(String(50))  # DESIGN, IMPLEMENTATION, TEST
    status = Column(String(50), default="PENDING")
    sequence = Column(Integer)
    depends_on = Column(UUID, ForeignKey("tasks.id"))
    estimated_tokens = Column(Integer)
    pr_number = Column(Integer)
    pr_url = Column(String(500))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
    
    feature = relationship("Feature", back_populates="tasks")
    agent_runs = relationship("AgentRun", back_populates="task")
    gate_results = relationship("GateResult", back_populates="task")
    approval_gates = relationship("ApprovalGate", back_populates="task")
    workspace = relationship("Workspace", uselist=False, back_populates="task")

# models/quality_gate.py
class QualityGate(Base):
    __tablename__ = "quality_gates"
    
    id = Column(UUID, primary_key=True, default=uuid4)
    project_id = Column(UUID, ForeignKey("projects.id"), nullable=False)
    gate_type = Column(String(50))  # CODE_QUALITY, SECURITY, TESTING, ARCHITECTURE
    name = Column(String(100))
    enabled = Column(Boolean, default=True)
    config = Column(JSON)
    thresholds = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    project = relationship("Project", back_populates="quality_gates")
    results = relationship("GateResult", back_populates="gate")

class GateResult(Base):
    __tablename__ = "gate_results"
    
    id = Column(UUID, primary_key=True, default=uuid4)
    task_id = Column(UUID, ForeignKey("tasks.id"), nullable=False)
    gate_id = Column(UUID, ForeignKey("quality_gates.id"), nullable=False)
    status = Column(String(20))  # PASS, WARN, FAIL
    score = Column(Float)
    summary = Column(Text)
    evidence = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    task = relationship("Task", back_populates="gate_results")
    gate = relationship("QualityGate", back_populates="results")

# models/approval.py
class ApprovalGate(Base):
    __tablename__ = "approval_gates"
    
    id = Column(UUID, primary_key=True, default=uuid4)
    task_id = Column(UUID, ForeignKey("tasks.id"), nullable=False)
    gate_name = Column(String(50))  # PLANNING_REVIEW, DESIGN_REVIEW, PR_REVIEW
    status = Column(String(20), default="PENDING")  # PENDING, APPROVED, REJECTED
    created_at = Column(DateTime, default=datetime.utcnow)
    
    task = relationship("Task", back_populates="approval_gates")
    approvals = relationship("Approval", back_populates="gate", cascade="all")

class Approval(Base):
    __tablename__ = "approvals"
    
    id = Column(UUID, primary_key=True, default=uuid4)
    gate_id = Column(UUID, ForeignKey("approval_gates.id"), nullable=False)
    approver_email = Column(String(255), nullable=False)
    decision = Column(String(50))  # APPROVE, APPROVE_WITH_SUGGESTIONS, REJECT
    feedback = Column(Text)
    approved_at = Column(DateTime, default=datetime.utcnow)
    
    gate = relationship("ApprovalGate", back_populates="approvals")

# models/agent_run.py
class AgentRun(Base):
    __tablename__ = "agent_runs"
    
    id = Column(UUID, primary_key=True, default=uuid4)
    task_id = Column(UUID, ForeignKey("tasks.id"), nullable=False)
    project_id = Column(UUID, ForeignKey("projects.id"), nullable=False)
    agent_type = Column(String(50))  # PLANNING, DESIGN, CODE_GEN, PR_CREATION
    status = Column(String(20), default="RUNNING")  # RUNNING, SUCCESS, FAILED, RETRY_QUEUED
    prompt = Column(Text)
    response_summary = Column(Text)
    tokens_used = Column(Integer)
    tokens_cached = Column(Integer)
    cost_usd = Column(Numeric(10, 4))
    retry_count = Column(Integer, default=0)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    error_message = Column(Text)
    
    task = relationship("Task", back_populates="agent_runs")
    project = relationship("Project", back_populates="agent_runs")
    events = relationship("AgentRunEvent", back_populates="run", cascade="all")

class AgentRunEvent(Base):
    __tablename__ = "agent_run_events"
    
    id = Column(UUID, primary_key=True, default=uuid4)
    run_id = Column(UUID, ForeignKey("agent_runs.id"), nullable=False)
    event_type = Column(String(50))  # START, STREAM_CHUNK, TOOL_CALL, COMPLETION
    timestamp = Column(DateTime, default=datetime.utcnow)
    details = Column(JSON)
    
    run = relationship("AgentRun", back_populates="events")

# models/workspace.py
class Workspace(Base):
    __tablename__ = "workspaces"
    
    id = Column(UUID, primary_key=True, default=uuid4)
    task_id = Column(UUID, ForeignKey("tasks.id"), nullable=False)
    workspace_path = Column(String(500), unique=True)
    base_branch = Column(String(100))
    worktree_branch = Column(String(100))
    status = Column(String(20), default="CREATED")  # CREATED, ACTIVE, RELEASED, ARCHIVED
    created_at = Column(DateTime, default=datetime.utcnow)
    released_at = Column(DateTime)
    
    task = relationship("Task", back_populates="workspace")

# models/design_document.py
class DesignDocument(Base):
    __tablename__ = "design_documents"
    
    id = Column(UUID, primary_key=True, default=uuid4)
    feature_id = Column(UUID, ForeignKey("features.id"), nullable=False)
    design_doc = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    feature = relationship("Feature", back_populates="design_document")
```

---

## 7. TECHNOLOGY STACK (All Open Source)

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Runtime** | Python 3.11+ | Core system |
| **API** | FastAPI | REST API + async |
| **ORM** | SQLAlchemy 2.0 | Database abstraction |
| **Migrations** | Alembic | Schema versioning |
| **Database** | SQLite (dev) / PostgreSQL (prod) | Persistent storage |
| **Task Queue** | Celery or in-process | Orchestration |
| **Web Dashboard** | HTMX + Vanilla JS | Minimal UI |
| **Code Quality** | Ruff (Python), ESLint (JS), Checkstyle (Java) | Linting |
| **Security** | Semgrep, Trivy, Bandit | SAST + deps |
| **Testing** | pytest, Jest, JUnit | Test runners |
| **Complexity** | radon (Python), plato (JS), PMD (Java) | Metrics |
| **Git** | git worktrees | Workspace isolation |
| **Agent Runtime** | Claude Code CLI (primary) + LiteLLM | LLM execution |
| **Logging** | structlog + JSON | Structured logs |
| **Monitoring** | Prometheus metrics | Observability |
| **Config** | Pydantic + YAML | Configuration |

---

## 8. DIRECTORY STRUCTURE

```
autonomous-agent-builder/
├── README.md
├── pyproject.toml                         # Dependencies, project metadata
├── .agent-builder.yaml                    # Global configuration
│
├── src/
│   └── autonomous_agent_builder/
│       ├── __init__.py
│       ├── main.py                        # Entry point
│       ├── config.py                      # Pydantic configuration
│       │
│       ├── api/
│       │   ├── __init__.py
│       │   ├── app.py                     # FastAPI app setup
│       │   ├── routes/
│       │   │   ├── __init__.py
│       │   │   ├── projects.py            # /api/projects
│       │   │   ├── features.py            # /api/features
│       │   │   ├── tasks.py               # /api/tasks
│       │   │   ├── quality_gates.py       # /api/quality-gates
│       │   │   ├── approvals.py           # /api/approvals
│       │   │   ├── runs.py                # /api/runs
│       │   │   ├── workspaces.py          # /api/workspaces
│       │   │   ├── board.py               # /api/board (dashboard)
│       │   │   └── metrics.py             # /api/metrics
│       │   └── schemas.py                 # Pydantic models for API
│       │
│       ├── dashboard/
│       │   ├── __init__.py
│       │   ├── static/
│       │   │   ├── css/
│       │   │   │   ├── main.css
│       │   │   │   ├── board.css
│       │   │   │   └── dashboard.css
│       │   │   ├── js/
│       │   │   │   ├── htmx.min.js
│       │   │   │   ├── main.js
│       │   │   │   ├── board.js
│       │   │   │   └── real-time.js       # WebSocket updates
│       │   │   └── img/
│       │   └── templates/
│       │       ├── base.html              # Base layout
│       │       ├── projects/
│       │       │   ├── list.html
│       │       │   └── detail.html
│       │       ├── board/
│       │       │   ├── board.html         # Kanban view
│       │       │   └── task_card.html
│       │       ├── tasks/
│       │       │   ├── detail.html        # Task modal
│       │       │   ├── run_logs.html      # Streaming logs
│       │       │   └── gates.html         # Gate results
│       │       ├── approvals/
│       │       │   ├── list.html
│       │       │   └── review.html        # Approval UI
│       │       └── metrics/
│       │           └── dashboard.html
│       │
│       ├── db/
│       │   ├── __init__.py
│       │   ├── models.py                  # SQLAlchemy models
│       │   ├── session.py                 # Database session management
│       │   ├── alembic/                   # Migrations
│       │   │   ├── env.py
│       │   │   ├── script.py.mako
│       │   │   └── versions/
│       │   │       ├── 0001_initial.py
│       │   │       ├── 0002_quality_gates.py
│       │   │       └── ...
│       │   └── repositories/              # Data access layer
│       │       ├── __init__.py
│       │       ├── project_repo.py
│       │       ├── feature_repo.py
│       │       ├── task_repo.py
│       │       ├── gate_repo.py
│       │       ├── approval_repo.py
│       │       ├── run_repo.py
│       │       └── workspace_repo.py
│       │
│       ├── orchestrator/
│       │   ├── __init__.py
│       │   ├── orchestrator.py            # Main orchestration loop
│       │   ├── phases/
│       │   │   ├── __init__.py
│       │   │   ├── planning.py            # Planning phase
│       │   │   ├── design.py              # Design phase
│       │   │   ├── implementation.py      # Code generation phase
│       │   │   ├── quality_gates.py       # Quality gate execution
│       │   │   ├── pr_creation.py         # PR creation phase
│       │   │   └── build_verification.py  # Build verification phase
│       │   ├── hooks.py                   # Lifecycle hooks
│       │   └── retry.py                   # Retry + backoff logic
│       │
│       ├── agents/
│       │   ├── __init__.py
│       │   ├── runner.py                  # Base agent runner interface
│       │   ├── claude_code_runner.py      # Claude Code CLI runner
│       │   ├── litellm_runner.py          # LiteLLM router
│       │   ├── context.py                 # Agent context builder
│       │   ├── prompt_templates.py        # Prompt template rendering
│       │   ├── artifact_extractor.py      # Extract files from workspace
│       │   └── callbacks.py               # Token streaming, error handling
│       │
│       ├── quality_gates/
│       │   ├── __init__.py
│       │   ├── base.py                    # Base QualityGate class
│       │   ├── code_quality.py            # Ruff, ESLint, Checkstyle
│       │   ├── security.py                # Semgrep, Trivy, OWASP
│       │   ├── testing.py                 # pytest, Jest, JUnit
│       │   ├── architecture.py            # Circular imports, layering
│       │   └── remediation.py             # Auto-fix logic
│       │
│       ├── workspace/
│       │   ├── __init__.py
│       │   ├── manager.py                 # Git worktree management
│       │   ├── git.py                     # Git operations
│       │   └── tools.py                   # Workspace utilities
│       │
│       ├── integrations/
│       │   ├── __init__.py
│       │   ├── github.py                  # GitHub API (PR creation)
│       │   ├── gitlab.py                  # GitLab API
│       │   ├── slack.py                   # Slack notifications
│       │   └── monitoring.py              # Prometheus export
│       │
│       ├── services/
│       │   ├── __init__.py
│       │   ├── board_service.py           # Board operations
│       │   ├── project_service.py         # Project management
│       │   ├── approval_service.py        # Approval workflow
│       │   ├── metrics_service.py         # Metrics calculation
│       │   └── git_service.py             # Git operations
│       │
│       ├── utils/
│       │   ├── __init__.py
│       │   ├── logger.py                  # Structured logging
│       │   ├── context_builder.py         # Codebase summary generation
│       │   ├── token_counter.py           # Token estimation
│       │   ├── cost_calculator.py         # Cost tracking
│       │   └── async_helpers.py           # Async utilities
│       │
│       └── exceptions.py                  # Custom exceptions
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                        # Pytest fixtures
│   ├── test_orchestrator.py               # Orchestrator tests
│   ├── test_agents.py                     # Agent runner tests
│   ├── test_quality_gates.py              # Gate tests
│   ├── test_api.py                        # API endpoint tests
│   ├── test_approval_workflow.py          # Approval logic tests
│   ├── integration/
│   │   ├── __init__.py
│   │   ├── test_planning_to_deployment.py # End-to-end flow
│   │   └── test_quality_gate_flow.py
│   └── fixtures/
│       ├── sample_projects/               # Test data
│       │   ├── java-api/
│       │   ├── python-ml/
│       │   └── nodejs-web/
│       └── mock_data.py
│
├── scripts/
│   ├── init_db.py                         # Initialize database
│   ├── init_project.py                    # Create new project
│   ├── run_orchestrator.py                # Start main loop
│   ├── run_api.py                         # Start API server
│   ├── run_dashboard.py                   # Start dashboard
│   └── migrate.py                         # Run migrations
│
├── docs/
│   ├── README.md                          # Getting started
│   ├── ARCHITECTURE.md                    # This design doc
│   ├── API.md                             # API documentation
│   ├── DEPLOYMENT.md                      # Production deployment
│   ├── CONFIGURATION.md                   # Configuration guide
│   ├── QUALITY_GATES.md                   # Gate documentation
│   ├── DEVELOPER_GUIDE.md                 # Contributing
│   ├── design-docs/                       # Architecture decisions
│   │   ├── 0001-workspace-isolation.md
│   │   ├── 0002-approval-gates.md
│   │   ├── 0003-quality-gate-framework.md
│   │   └── ...
│   ├── exec-plans/                        # Implementation plans
│   │   ├── active/
│   │   │   └── phase-1-mvp.md
│   │   └── completed/
│   └── references/                        # Symphony spec, etc.
│       └── SYMPHONY_SPEC.md
│
├── docker/
│   ├── Dockerfile                         # Production image
│   ├── docker-compose.yml                 # Local dev setup
│   └── .dockerignore
│
├── .agent-builder/                        # Project-specific config
│   ├── quality-gates.yaml                 # Gate configuration
│   ├── approval-gates.yaml                # Approval policy
│   ├── prompts/                           # Custom prompt templates
│   │   ├── planning.txt
│   │   ├── design.txt
│   │   ├── code_gen.txt
│   │   └── ...
│   └── hooks/                             # Custom hooks
│       ├── before_run.py
│       └── after_gate.py
│
├── .github/
│   ├── workflows/
│   │   ├── test.yml                       # Test pipeline
│   │   ├── lint.yml                       # Linting checks
│   │   └── release.yml                    # Release automation
│   └── ISSUE_TEMPLATE/
│       ├── feature_template.md
│       └── bug_template.md
│
├── CLAUDE.md                              # Claude Code metadata
├── .gitignore
└── LICENSE
```

---

## 9. FEATURE FLOW EXAMPLE

### Scenario: "Add user authentication with JWT for Node.js API project"

```
T+0:00 FEATURE CREATED
├─ Title: "Add user authentication with JWT"
├─ Description: "Implement JWT-based authentication for REST API"
├─ Acceptance Criteria:
│  • Users can register with email/password
│  • Users can login and receive JWT token
│  • Protected endpoints verify JWT signature
│  • Tokens expire after 24 hours
│  • Invalid tokens return 401
├─ Priority: High
└─ Status: BACKLOG

T+0:05 PLANNING PHASE (autonomous)
├─ Orchestrator polls board → BACKLOG features
├─ Planning Agent runs (Claude Code)
│  ├─ Input:
│  │  • Feature description
│  │  • Codebase summary (package.json, existing routes, structure)
│  │  • Project context (Node.js, Express, PostgreSQL)
│  └─ Output (JSON):
│     {
│       "tasks": [
│         {
│           "title": "Design JWT authentication schema",
│           "type": "DESIGN",
│           "complexity": "medium",
│           "sequence": 1,
│           "depends_on": null,
│           "description": "Design database schema for users table..."
│         },
│         {
│           "title": "Implement user registration endpoint",
│           "type": "IMPLEMENTATION",
│           "complexity": "high",
│           "sequence": 2,
│           "depends_on": "<design-task-id>",
│           "description": "POST /auth/register with email validation..."
│         },
│         {
│           "title": "Implement user login endpoint",
│           "type": "IMPLEMENTATION",
│           "complexity": "medium",
│           "sequence": 3,
│           "depends_on": "<task-2-id>",
│           "description": "POST /auth/login with credential verification..."
│         },
│         {
│           "title": "Implement JWT verification middleware",
│           "type": "IMPLEMENTATION",
│           "complexity": "medium",
│           "sequence": 4,
│           "depends_on": "<task-2-id>",
│           "description": "Middleware to verify JWT on protected routes..."
│         },
│         {
│           "title": "Write integration tests",
│           "type": "TEST",
│           "complexity": "high",
│           "sequence": 5,
│           "depends_on": "<task-4-id>",
│           "description": "Test full auth flow with Jest..."
│         }
│       ]
│     }
├─ AgentRun created:
│  • agent_type: PLANNING
│  • tokens_used: 1,200
│  • cost_usd: 0.05
├─ Feature status → PLANNING
├─ ApprovalGate created: PLANNING_REVIEW (PENDING)
└─ Developer notified: "Sprint planning ready for review"

T+0:10 DEVELOPER APPROVES PLANNING
├─ Developer reviews task breakdown
├─ Clicks "APPROVE" in dashboard
├─ ApprovalGate.status → APPROVED
├─ Feature status → APPROVED
└─ Orchestrator unblocked

T+0:15 DESIGN PHASE (autonomous) — Task 1
├─ Orchestrator polls board → APPROVED features
├─ Design Agent runs (Claude Code)
│  ├─ Input:
│  │  • Task: "Design JWT authentication schema"
│  │  • Feature context
│  │  • Codebase (existing models, database setup)
│  └─ Output:
│     ```
│     # JWT Authentication Design Document
│
│     ## Database Schema
│
│     ```sql
│     CREATE TABLE users (
│       id SERIAL PRIMARY KEY,
│       email VARCHAR(255) UNIQUE NOT NULL,
│       password_hash VARCHAR(255) NOT NULL,
│       created_at TIMESTAMP DEFAULT NOW(),
│       updated_at TIMESTAMP DEFAULT NOW()
│     );
│
│     CREATE INDEX idx_users_email ON users(email);
│     ```
│
│     ## API Contracts
│     - POST /auth/register
│       Request: { email, password }
│       Response: { id, email, created_at }
│
│     - POST /auth/login
│       Request: { email, password }
│       Response: { access_token, expires_in, token_type }
│
│     - GET /protected-route (with Authorization header)
│       Header: Authorization: Bearer <token>
│       Response: 200 if valid, 401 if invalid
│
│     ## JWT Payload
│     {
│       "sub": "<user-id>",
│       "email": "<email>",
│       "iat": 1234567890,
│       "exp": 1234654290
│     }
│
│     ## Security Considerations
│     - Use bcrypt for password hashing
│     - Set token expiration to 24 hours
│     - Use HS256 algorithm
│     - Validate token signature on every request
│     ```
│
├─ DesignDocument saved in database
├─ Task 1 status → REVIEW_PENDING
├─ ApprovalGate created: DESIGN_REVIEW (PENDING)
├─ AgentRun created:
│  • tokens_used: 900
│  • cost_usd: 0.04
└─ Developer notified: "Design ready for review"

T+0:20 DEVELOPER REVIEWS DESIGN
├─ Developer reads design doc
├─ Requests change: "Add refresh token endpoint"
├─ Approvals.decision → APPROVE_WITH_SUGGESTIONS
├─ Feedback: "Good design. Please also add refresh_token endpoint..."
├─ Task 1 status → APPROVED (with feedback)
└─ Design Agent triggered again with feedback

T+0:25 UPDATED DESIGN GENERATED
├─ Design Agent incorporates feedback
├─ Adds refresh_token endpoint to schema
├─ DesignDocument updated
└─ Task 1 status → APPROVED

T+0:30 IMPLEMENTATION PHASE — Task 2: User Registration
├─ Orchestrator validates Task 2 depends_on (Task 1) is APPROVED ✓
├─ Creates git worktree:
│  • Command: git worktree add -b feature/task-2-user-registration /.claude/worktrees/feature/task-2-...
│  • Workspace.status → CREATED
│  • Creates feature branch off develop
├─ Code Generation Agent runs (Claude Code CLI)
│  ├─ Input:
│  │  • Task: "Implement user registration endpoint"
│  │  • Design document (reference)
│  │  • Codebase context:
│  │    - src/models/User.ts (existing)
│  │    - src/routes/index.ts
│  │    - src/utils/db.ts
│  │    - package.json (dependencies: bcryptjs, jsonwebtoken)
│  │  • Acceptance criteria from feature
│  │
│  └─ Agent works in workspace:
│     1. Reads codebase structure
│     2. Generates User schema validation (Joi/Zod)
│     3. Implements POST /auth/register:
│        - Validate email format
│        - Check email not already used
│        - Hash password with bcrypt
│        - Insert user into database
│        - Return user object (no password)
│     4. Writes unit tests (Jest):
│        - Test valid registration
│        - Test duplicate email error
│        - Test weak password rejection
│        - Test hashed password storage
│     5. Commits: "feat: implement user registration with email validation"
│
├─ Workspace.status → ACTIVE
├─ Task 2 status → IN_PROGRESS
├─ AgentRun created:
│  • tokens_used: 3,200 (larger task)
│  • cost_usd: 0.12
└─ Real-time logs streamed to dashboard

T+0:45 QUALITY GATES EXECUTION (automated)
├─ Code Quality Gate (ESLint)
│  ├─ Runs: eslint src/ --format json
│  ├─ Findings:
│  │  • Unused import in test file (auto-fixable)
│  │  • One line too long (auto-fixable)
│  ├─ Status: WARN
│  ├─ GateResult.score: 92
│  └─ Remediation: Auto-fix triggered
│
├─ Security Gate (Semgrep)
│  ├─ Runs: semgrep --json --config=p/owasp-top-ten
│  ├─ Findings:
│  │  • Password comparison: Using == instead of constantTimeCompare
│  │  • Rule: security.comparison.insecure-bcrypt-comparison
│  ├─ Status: FAIL (critical)
│  ├─ Remediation possible: YES
│  └─ Recommendation: "Use bcryptjs.compareSync() for constant-time comparison"
│
│  └─ Auto-remediation triggered:
│     1. Code Gen Agent notified of finding
│     2. Agent fixes: "return bcryptjs.compare(password, user.password_hash)"
│     3. Security gate re-runs → PASS
│
├─ Testing Gate (Jest)
│  ├─ Runs: npm test -- --coverage
│  ├─ Results:
│  │  • 8 tests passed
│  │  • Coverage: 85% (registration endpoint)
│  ├─ Status: PASS
│  └─ GateResult.score: 100
│
├─ Architecture Gate
│  ├─ Checks:
│  │  • No circular imports ✓
│  │  • Naming conventions (camelCase functions) ✓
│  │  • Layer violations: None ✓
│  ├─ Status: PASS
│  └─ GateResult.score: 100
│
└─ All gates complete. Task 2 status → TESTING

T+1:00 PARALLEL: Task 3 & Task 4 (Orchestrator concurrency = 2)
├─ Task 3: User Login Endpoint
│  └─ Code Gen Agent starts (same flow as Task 2)
├─ Task 4: JWT Middleware
│  └─ Waits (concurrency limit reached)
└─ Task 5: Integration Tests
   └─ Depends on Task 4, still waiting

T+1:30 TASK 2 COMPLETE — PR CREATION PHASE
├─ Workspace releases:
│  • Git push -u origin feature/task-2-...
│  • Creates remote branch
│  • Workspace.status → RELEASED
├─ PR Creation Agent runs
│  ├─ Input:
│  │  • All changes (git diff)
│  │  • Quality gate results
│  │  • Test results + coverage report
│  │  • Security findings (all fixed)
│  │
│  └─ Creates PR via GitHub API:
│     ```markdown
│     # [Task 2] Implement user registration endpoint
│
│     ## Summary
│     Adds user registration with email validation and password hashing.
│
│     ## Quality Gates
│     | Gate | Status | Score | Details |
│     |------|--------|-------|---------|
│     | Code Quality | PASS | 95 | Fixed: unused imports, line length |
│     | Security | PASS | 100 | No vulnerabilities |
│     | Testing | PASS | 95 | 8/8 tests, 85% coverage |
│     | Architecture | PASS | 100 | No issues |
│
│     ## Changes
│     - src/routes/auth.ts: POST /auth/register endpoint
│     - src/models/User.ts: User schema validation
│     - tests/auth.test.ts: Unit tests for registration
│
│     ## Test Results
│     ```
│     PASS  tests/auth.test.ts
│       ✓ should register user with valid credentials
│       ✓ should reject duplicate email
│       ✓ should reject weak password
│       ✓ should hash password before storage
│
│     Test Suites: 1 passed, 1 total
│     Tests:       4 passed, 4 total
│     Coverage:    85%
│     ```
│
│     ✅ All quality gates passed
│     ```
│
├─ PR created: GitHub PR #147
│  • PR.url = https://github.com/acme/project/pull/147
│  • Task 2 pr_url → set
│  • Task 2 pr_number → 147
│  • Task 2 status → REVIEW_PENDING
│
├─ ApprovalGate created: PR_REVIEW (PENDING)
└─ Developer notified: "PR #147 ready for review"

T+1:40 DEVELOPER REVIEWS PR
├─ Developer clicks PR link (in dashboard or GitHub)
├─ Reviews changes:
│  ├─ Code looks good
│  ├─ Tests pass
│  ├─ Security gates passed
│  └─ Requests small change: "Add JSDoc comments"
├─ Posts feedback on GitHub
├─ Approvals.decision → APPROVE_WITH_SUGGESTIONS
└─ Code Gen Agent triggered again for refinement

T+1:50 CODE GEN AGENT ADDS JSDoc
├─ Agent adds documentation comments
├─ Commits: "docs: add JSDoc comments to auth functions"
├─ Pushes to same branch
├─ PR auto-updates on GitHub
└─ Orchestrator re-runs quality gates on new commit → All pass

T+2:00 DEVELOPER APPROVES & MERGES
├─ Developer clicks "Approve and Merge" in dashboard
├─ Approvals.decision → APPROVE
├─ GitHub API: Merge PR #147
├─ Task 2 status → APPROVED_FOR_MERGE

T+2:10 BUILD VERIFICATION PHASE
├─ Orchestrator waits for develop branch to update
├─ Runs build verification:
│  ├─ Checks out develop (with merge)
│  ├─ Runs: npm install
│  ├─ Runs: npm run build
│  ├─ Runs: npm run test:integration
│  ├─ All pass ✓
│  └─ Build artifact created
├─ AgentRun.status → SUCCESS
├─ Task 2 status → DEPLOYED
└─ Feature progress: 1/5 tasks complete (20%)

T+2:20 PARALLEL TASKS CONTINUE
├─ Task 3 (Login) now running (concurrency freed up)
├─ Task 4 (Middleware) queued
├─ Task 5 (Integration tests) still blocked by Task 4
└─ Dashboard shows: 1 deployed, 1 in progress, 3 pending

... (repeat cycle for Tasks 3-5) ...

T+4:00 FINAL TASK COMPLETE (Task 5: Integration Tests)
├─ All subtasks deployed
├─ Feature status → IMPLEMENTED
├─ All PRs merged into develop
└─ Dashboard shows: Feature 100% complete

T+4:15 FEATURE VERIFICATION
├─ Manual QA runs integration tests
├─ Test: "User registers → Logs in → Accesses protected route → Token expires"
├─ All scenarios pass ✓
├─ Feature approved for production
└─ Feature status → DEPLOYED

METRICS GENERATED
├─ Cycle time: 4.25 hours
├─ Code quality: avg 95 score
├─ Security: 100 (zero critical findings)
├─ Test coverage: 87%
├─ Agent cost: $2.15 total (1.2M tokens)
├─ Developer time: ~1 hour (reviews + approvals)
└─ Dashboard shows all metrics in /dashboard/metrics
```

---

## 10. PRODUCTION DEPLOYMENT CONSIDERATIONS

### Multi-Tenancy (Enterprise)
```
# One database per client (security isolation)
- Database name: client-{client-id}
- Connection string template: postgresql://user:pass@host/client-{client-id}
- API authentication via OAuth2 + JWT
- Dashboard multi-project support with role-based access

# Audit logging
- All state changes logged to audit table
- Immutable append-only log
- Exportable for compliance (SOC 2, ISO 27001)
```

### Scaling
```
# Orchestrator
- Horizontal scaling via job queue (Celery + Redis/RabbitMQ)
- Multiple orchestrator instances with leader election
- Lock-free task assignment (optimistic concurrency)

# API
- Stateless FastAPI servers behind load balancer
- Connection pooling for database
- Caching layer (Redis) for project metadata

# Agents
- Runs isolated in containers or VMs
- GPU support for future vision-based code review
- Resource limits (CPU, memory, timeout)
```

### Security
```
# Network
- TLS for all API communication
- Firewall: Only allow git + GitHub/GitLab webhooks from approved ranges
- Database: No public access, VPC only

# Secrets Management
- LLM API keys in AWS Secrets Manager / HashiCorp Vault
- Git credentials in Vault (not in env vars)
- Rotation policy: 90 days

# Code Isolation
- Agents run code in sandboxed containers
- No network access from agent workspace
- Filesystem isolation via Docker/Podman

# Approval Audit
- All approvals signed with developer's key
- Immutable approval records
- Exportable for compliance audits
```

---

## CRITICAL IMPLEMENTATION SEQUENCING

### Phase 1: MVP (Weeks 1-2)
1. Core data model + SQLite database
2. REST API (projects, features, tasks CRUD)
3. Simple approval gates (manual only)
4. Claude Code CLI runner
5. Basic HTMX dashboard
6. Single orchestrator loop (planning + design phases)

### Phase 2: Quality Gates (Weeks 3-4)
1. Code quality gate (ruff/eslint/checkstyle)
2. Testing gate (pytest/jest/junit)
3. Auto-remediation framework
4. Gate configuration system

### Phase 3: Security Gates (Week 5)
1. Semgrep SAST integration
2. Trivy dependency scanning
3. OWASP checks
4. Security evidence reporting

### Phase 4: Full SDLC (Week 6+)
1. Git worktree workspace isolation
2. Code generation phase
3. PR creation agent
4. Build verification
5. GitHub/GitLab integration
6. Metrics dashboard

### Phase 5: Enterprise Features (Week 7+)
1. Multi-tenancy
1. PostgreSQL migration
2. Advanced approval workflows
3. Audit logging
4. Performance monitoring
5. Cost tracking & reporting

---

### Critical Files for Implementation

- `/src/autonomous_agent_builder/db/models.py` — Core data model (Project, Feature, Task, QualityGate, Approval, AgentRun, Workspace)
- `/src/autonomous_agent_builder/api/app.py` — FastAPI application setup and route registration
- `/src/autonomous_agent_builder/orchestrator/orchestrator.py` — Main orchestration loop driving the SDLC phases
- `/src/autonomous_agent_builder/agents/runner.py` — Agent execution interface and Claude Code CLI implementation
- `/src/autonomous_agent_builder/quality_gates/base.py` — Quality gate framework and core implementations (code quality, security, testing, architecture)