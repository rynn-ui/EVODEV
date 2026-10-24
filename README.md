# EvoDev Evolution ⚡

> **Self-Improving, Multi-Agent Developer Experience Platform**
> **Persistent Memory · Self-Improving Skills · Unified Connectors · Specialist Delegation · Safe Checkpoints · Native Tkinter GUI**

EvoDev is a production-oriented, local-first engineering intelligence layer that connects multiple AI coding agents—including **OpenCode**, **Gemini CLI / Antigravity**, **Kilo Code**, **Nous Research Hermes Agent**, and custom harnesses—to a shared, evidence-backed knowledge repository.

As developers code—fixing bugs, configuring builds, resolving compilation errors, refactoring, and verifying tests—EvoDev observes verified actions, distills reusable lessons with explicit provenance, tracks empirical Bayesian strategy success rates, evolves verified procedures into versioned skills, and packages accumulated competence into portable **Experience Profiles (`.vxp`)**.

EvoDev does **NOT** require training a foundation model, downloading neural weights, or uploading proprietary code to third-party vector databases.

---

## Key Platform Capabilities

### 1. Persistent Memory & Intelligent Recall (8 Partitions)
EvoDev partitions developer and project memory into clearly separated categories:
- **`preferences`**: Developer habits, coding guidelines, formatting rules, test runners.
- **`architecture`**: Architecture decisions, module boundaries, database schemas, API paradigms.
- **`lessons`**: Verified technical patterns with empirical proof of passing builds/tests.
- **`anti_patterns`**: Failed approaches, known regressions, compiler traps, deprecations.
- **`task_summaries`**: Concise records of completed sessions derived from observable events.
- **`skills`**: Reusable multi-step procedures with prerequisites and validation steps.
- **`general`**: Reusable cross-project engineering knowledge.
- **`project_private`**: Context strictly isolated to a single project/repository (`ScopeViolationError` guard).

All memories are redacted for credentials/tokens before persistence, support intelligent recall, detect contradictions, and consolidate duplicates.

### 2. Self-Improving Skill Engine
Skills are reusable procedures distinct from individual lessons:
- **Structure**: Packages prerequisites, execution steps, validation commands, and expected outcomes.
- **Evaluation & Promotion**: Evaluated against repeatable test suites; versions are promoted only when passing criteria are met and zero regressions occur.
- **Untrusted Code Guardrails**: Agent-generated scripts are isolated and untrusted until explicitly approved and evaluated.
- **Multi-Agent Rendering**: Formatted on demand as Human Markdown, Model Context Protocol (MCP) tool schema (`evodev_execute_skill`), or Hermes system prompt.

### 3. Unified Multi-Agent Connector Architecture
A common adapter interface (`AgentConnector` protocol) coordinates AI coding agents:
- **OpenCode**: Model Context Protocol (MCP) stdio server (`evodev-mcp`) and session harvest integration.
- **Gemini CLI / Antigravity**: Lifecycle hooks (`.agents/hooks.json`) and MCP tool configuration.
- **Kilo Code**: Native `.kilo/mcp.json` tool integration.
- **Hermes Agent**: Tool schema generation (`evodev_retrieve_memory`, `evodev_report_outcome`) via `hermes_config.json`.
- **Connector Registry**: Failure isolation, LRU event deduplication, capability reporting, and automated secret redaction across all adapters.

### 4. Specialist Delegation & Orchestration
Optional multi-role task planner assigning specialized responsibilities to compatible agents:
- **Roles**: Implementer, Code Reviewer, Test Engineer, Debugging Specialist, Documentation Specialist, Security Reviewer.
- **Human Approval Gates**: Sensitive or high-impact steps enter `WAITING_APPROVAL` and require explicit authorization.
- **Guardrails**: Concurrency limits, timeouts, cancellation, and evidence recording. If no compatible agent runtime exists, delegation cleanly reports `UNSUPPORTED` rather than simulating success.

### 5. Safe Checkpoints & Rollback
Three distinct non-destructive recovery layers:
- **Git Checkpoints**: Captures uncommitted diffs, modified files, and patch snapshots without running destructive resets.
- **SQLite Database Checkpoints**: WAL-flushed atomic SQLite database snapshots with point-in-time restore.
- **Profile Checkpoints**: Versioned `.vxp` packages supporting audit and rollback.

### 6. Background Local Scheduler
Independent local background daemon managing automated developer tasks:
- **Supported Schedules**: `hourly`, `daily`, `weekly`, `every:30m`, or custom second intervals.
- **Built-in Tasks**: Health checks, stale memory consolidation, dependency audits, benchmark runs.
- **Resilience**: SQLite job store handles system reboots, prevents duplicate runs, and maintains execution history.

### 7. Model and Provider Routing
Task-based routing for EvoDev-managed jobs:
- Matches task requirements against models from Anthropic, OpenAI, Gemini, Local Ollama, and DeepSeek.
- Factors in latency tiers (`low`, `balanced`, `thorough`), capabilities (`code_generation`, `security_audit`, `architecture`, `fast_edit`), cost, and user-defined provider restrictions.

### 8. Native Windows Desktop Application (Tkinter/ttk)
A responsive desktop GUI operating completely local and independent of the Core:
- **14 Modular Views**: Overview, Experience Inspector, Categorized Memory, Self-Improving Skills, Verified Lessons, Bayesian Strategies, Observable Experiences, Specialist Orchestration, Background Scheduler, Safe Checkpoints, Empirical Benchmarks, Multi-Agent Connectors, Diagnostic Doctor, and Safe Uninstallation.
- Off-thread worker pool with thread-safe `queue.Queue` dispatch ensuring responsive UI interactions.

### 9. Safe Uninstallation & Data Lifecycle
- **What is removed**: Managed database files (`~/.evodev/evodev.db*`), configuration, and EvoDev-owned entries in agent configuration files.
- **What is protected**: **External `.vxp` profile archives and user-owned backups are NEVER deleted or modified.**
- Preview mode via `evodev uninstall --dry-run` and optional backup via `evodev uninstall --backup`.

---

## Architecture Diagram

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                   AI Coding Agents                                     │
│   ┌────────────────┐   ┌───────────────────────────┐   ┌───────────┐   ┌───────────┐   │
│   │    OpenCode    │   │  Gemini CLI / Antigravity │   │ Kilo Code │   │  Hermes   │   │
│   │  (evodev-mcp)  │   │   (.agents/hooks.json)    │   │  (.kilo)  │   │ (.hermes) │   │
│   └───────┬────────┘   └─────────────┬─────────────┘   └─────┬─────┘   └─────┬─────┘   │
└───────────┼──────────────────────────┼───────────────────────┼───────────────┼─────────┘
            ▼                          ▼                       ▼               ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                           Connector Registry & Manager                                 │
│   • Typed AgentConnector Contract (initialize, context, events, outcomes, shutdown)   │
│   • Failure Isolation, LRU Deduplication Cache & Automatic Secret Redaction             │
└──────────────────────────────────────────┬─────────────────────────────────────────────┘
                                           │
                                           ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                     EvoDev Core                                        │
│   ┌───────────────────────────────────┐    ┌───────────────────────────────────────┐   │
│   │ Persistent Memory (8 Partitions)  │    │ Self-Improving Skill Engine           │   │
│   │ - Strict Scope & Privacy Isolation│    │ - Evaluation, Promotion & Rollback    │   │
│   │ - Contradiction & Redaction Engine│    │ - Multi-Agent Script Rendering        │   │
│   └───────────────────────────────────┘    └───────────────────────────────────────┘   │
│   ┌───────────────────────────────────┐    ┌───────────────────────────────────────┐   │
│   │ Storage & Retrieval Engine        │    │ Specialist Orchestrator & Delegation  │   │
│   │ - SQLite WAL & Schema Migrations  │    │ - Human Approval Gates                │   │
│   │ - Scoped Multi-Factor Ranker      │    │ - Role Decomposition (6 roles)        │   │
│   └───────────────────────────────────┘    └───────────────────────────────────────┘   │
│   ┌───────────────────────────────────┐    ┌───────────────────────────────────────┐   │
│   │ Safe Checkpoint & Rollback Mgr    │    │ Local Background Scheduler            │   │
│   │ - Git diff, SQLite WAL, .vxp v2   │    │ - Persistent SQLite Job Store         │   │
│   └───────────────────────────────────┘    └───────────────────────────────────────┘   │
└──────────────────────────────────────────▲─────────────────────────────────────────────┘
                                           │
                                           │ In-Process Service APIs
                                           │ (Thread-Safe Off-Thread Workers)
┌──────────────────────────────────────────┴─────────────────────────────────────────────┐
│                          Native Desktop Application (Tkinter/ttk)                      │
│   14 Modular Views: Overview · Inspector · Memory · Skills · Lessons · Strategies      │
│   Experiences · Orchestration · Scheduler · Checkpoints · Benchmarks · Connectors      │
│   Doctor Diagnostics · Safe Uninstallation Dialog                                      │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Installation & Quickstart

### Option A: Use EvoDev in Any Project (from GitHub)
To bring EvoDev into any existing or cloned project:

1. **Install EvoDev directly from GitHub**:
   ```powershell
   pip install git+https://github.com/rynn-ui/EVODEV.git
   ```

2. **Initialize in your project repository**:
   Navigate to your project directory and initialize:
   ```powershell
   cd /path/to/your-project
   evodev init --name "MyProject"
   ```

3. **Connect your AI coding agent**:
   Provision the configuration files for your agent in one command:
   ```powershell
   # For Gemini CLI / Google Antigravity (.agents/hooks.json & mcp_config.json)
   evodev connectors install-gemini

   # For OpenCode (opencode.json MCP stdio)
   evodev connectors install-opencode

   # For Kilo Code (.kilo/mcp.json)
   evodev connectors install-kilo

   # For Nous Research Hermes Agent (hermes_config.json)
   evodev connectors install-hermes
   ```

---

### Option B: Clone & Develop EvoDev Locally
To clone the EvoDev source repository directly for development:

1. **Clone the repository**:
   ```powershell
   git clone https://github.com/rynn-ui/EVODEV.git
   cd EVODEV
   ```

2. **Install dependencies in editable mode**:
   ```powershell
   pip install -e .
   ```

3. **Initialize the default profile & database**:
   ```powershell
   evodev init --name PersonalCodingExpert
   ```

---

### Launching the Desktop GUI & Diagnostics

1. **Open the Desktop Application**:
   ```powershell
   evodev gui
   ```
   *Or launch directly via Python module:*
   ```powershell
   python -m evodev.gui
   ```

2. **Run System Health Diagnostics**:
   ```powershell
   evodev doctor
   ```
   *Verify database WAL mode, write permissions, connector readiness, and secret scrubber health.*

---

## CLI Command Reference

### Memory Management
```powershell
# List stored memories
evodev memory list [--category architecture]

# Search memories with strict scope enforcement
evodev memory search "FastAPI memory leak"

# Add verified memory item
evodev memory add "Hexagonal Architecture rule" --category architecture --content '{"pattern": "ports_and_adapters"}'

# Consolidate duplicate memories
evodev memory consolidate

# Delete or deactivate memory
evodev memory delete <memory_id> [--hard]
```

### Self-Improving Skills
```powershell
# List registered skills
evodev skills list

# Create a new skill
evodev skills create "TDD Workflow" --description "Test-driven development procedure" --instructions "1. Red, 2. Green, 3. Refactor"

# Render skill for human or agent consumption
evodev skills view <skill_id> --format [markdown|mcp|hermes]

# Run repeatable automated evaluation
evodev skills evaluate <skill_id>
```

### Safe Checkpoints & Rollback
```powershell
# List existing checkpoints
evodev checkpoints list

# Create a checkpoint before risky tasks
evodev checkpoints create "Pre-refactor snapshot" --type [git|database|profile]

# Restore database state from checkpoint
evodev checkpoints restore <checkpoint_id> -y
```

### Background Scheduler
```powershell
# List registered scheduled tasks
evodev schedule list

# Register background maintenance task
evodev schedule add "Daily Maintenance" --job-type health_check --schedule daily

# Run due tasks immediately
evodev schedule run-pending

# Remove scheduled task
evodev schedule delete <job_id>
```

### Profile Portability & Versioning
```powershell
# List experience profiles
evodev profiles list

# Create, duplicate, or activate profile
evodev profiles create WorkProfile
evodev profiles activate WorkProfile

# Export and import portable .vxp archives
evodev profiles export WorkProfile ./work.vxp [--password SecretKey123]
evodev profiles import ./work.vxp

# Inspect archive entries and integrity
evodev profiles inspect ./work.vxp

# Version history and rollback
evodev profiles history WorkProfile
evodev profiles rollback WorkProfile 1.0.0
```

### Safe Uninstallation
```powershell
# Dry-run preview of files that would be removed
evodev uninstall --dry-run

# Confirmed uninstall with automatic backup
evodev uninstall --backup -y
```

---

## Automated Verification & Test Results

Run the full automated test suite:
```powershell
python -m pytest tests/ -v
```

**110 tests passing with 100% success rate across all 23 test suites:**
- `test_benchmarks.py`: 1 passed
- `test_checkpoints.py`: 3 passed
- `test_cli.py`: 5 passed
- `test_collector.py`: 2 passed
- `test_connectors.py`: 5 passed
- `test_connectors_unified.py`: 10 passed
- `test_gui_native.py`: 9 passed
- `test_hermes_connector.py`: 3 passed
- `test_inspector.py`: 12 passed
- `test_learning.py`: 3 passed
- `test_memory.py`: 5 passed
- `test_models.py`: 4 passed
- `test_orchestration.py`: 4 passed
- `test_profiles.py`: 4 passed
- `test_retrieval.py`: 2 passed
- `test_routing.py`: 3 passed
- `test_scenarios.py`: 6 passed
- `test_scheduler.py`: 3 passed
- `test_security.py`: 6 passed
- `test_skills.py`: 4 passed
- `test_storage.py`: 4 passed
- `test_uninstall.py`: 10 passed
- `test_vxp_v2.py`: 2 passed

---

## License

MIT License.
