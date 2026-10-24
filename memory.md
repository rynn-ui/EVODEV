# EvoDev Evolution — Project Memory & Architecture Context

## 1. Project Overview
- **Product Name**: **EvoDev** (configurable via config/env).
- **Version**: **1.0.0**
- **Author**: **ryn** (GitHub repository: [`rynn-ui/EVODEV`](https://github.com/rynn-ui/EVODEV))
- **Core Mission**: A persistent, local-first engineering intelligence and developer-experience platform operating alongside compatible AI coding agents (**OpenCode**, **Gemini CLI / Antigravity**, **Kilo Code**, **Nous Research Hermes Agent**, and custom IDE harnesses).
- **Primary Objective**: Accumulates verified software engineering lessons, empirical Bayesian strategy statistics, and self-improving reusable skills across development tasks. Intelligence learned on projects 1–6 is retrieved and applied on project 7 without foundation model fine-tuning or cloud dependencies.
- **Portability**: Preserves, versions, exports, and imports accumulated intelligence as standalone **Portable Experience Profiles (`.vxp` v2)** with AES-256-GCM encryption and SHA-256 integrity verification.
- **Core Invariant Principles**:
  1. *Core Independence*: Core learning engine, memory, retrieval, and database operate completely local and independent of desktop GUI or specific external agent runtimes.
  2. *Verification Gate*: The absence of an error is NOT proof of success. Evidence must be empirical (passing tests, compiler return code 0, linter clean, or explicit user feedback).
  3. *Zero Mock Success*: If an agent runtime is missing or delegation is unsupported, it reports `UNSUPPORTED` rather than simulating a successful result.
  4. *Safe Data Lifecycle*: Exported `.vxp` archives and backups are protected user data and are **never** deleted or modified by uninstallation.

---

## 2. Core Architectural Subsystems

### A. Persistent Categorized Memory (8 Partitions)
Managed by `MemoryManager` ([`evodev/memory/manager.py`](file:///d:/programming%20work/vibe%20extension%20profile/evodev/memory/manager.py)) with automated secret redaction, contradiction detection against anti-patterns, duplicate consolidation, and strict scope isolation:
1. **`preferences`**: Developer habits, coding guidelines, formatting rules, test runners.
2. **`architecture`**: Architecture decisions, module boundaries, database schemas, API paradigms.
3. **`lessons`**: Verified technical patterns supported by passing build/test evidence.
4. **`anti_patterns`**: Failed approaches, known regressions, compiler traps, deprecations.
5. **`task_summaries`**: Concise records of completed sessions derived from observable events.
6. **`skills`**: Reusable multi-step procedures with prerequisites and validation steps.
7. **`general`**: Reusable cross-project engineering knowledge.
8. **`project_private`**: Strictly repository-internal conventions; queries/writes without explicit `project_id` raise `ScopeViolationError`.

### B. Self-Improving Skill Engine
Managed by `SkillEngine`, `SkillEvaluator`, and `SkillRenderer` ([`evodev/skills/`](file:///d:/programming%20work/vibe%20extension%20profile/evodev/skills/)):
- **Skill Structure**: Packages instructions, prerequisites (`SkillPrerequisite`), procedure steps (`ProcedureStep`), validation commands, and expected outcomes.
- **Version Lifecycle**: SemVer versioning (`1.0.0` -> `1.1.0`), draft version proposing, automated evaluation against repeatable test suites, and rollback (`rollback_version`).
- **Promotion Gates**: A version is promoted to active only when passing empirical evaluation criteria (e.g. 100% test pass rate) with zero regressions.
- **Untrusted Code Guardrails**: AI-generated scripts are isolated and untrusted until explicitly approved and evaluated; arbitrary shell scripts are never automatically run.
- **Multi-Agent Rendering**: Formatted on demand as Human Markdown, Model Context Protocol (MCP) tool schema (`evodev_execute_skill`), or Hermes system prompt.

### C. Unified Multi-Agent Connector Architecture
Managed by `ConnectorManager` and `ConnectorRegistry` ([`evodev/connectors/manager.py`](file:///d:/programming%20work/vibe%20extension%20profile/evodev/connectors/manager.py)):
- **Unified Contract**: Common `AgentConnector` protocol ([`evodev/connectors/contract.py`](file:///d:/programming%20work/vibe%20extension%20profile/evodev/connectors/contract.py)) supporting `initialize`, `health_check`, `get_capabilities`, `get_context`, `ingest_event`, `report_outcome`, and `shutdown`.
- **Failure Isolation**: An exception or network timeout in one adapter never breaks the learning engine or other adapters.
- **Deduplication & Redaction**: Built-in LRU cache drops duplicate events; secret scrubber strips tokens prior to persistence.
- **Implemented Adapters**:
  - `OpenCodeConnector` ([`evodev/connectors/opencode.py`](file:///d:/programming%20work/vibe%20extension%20profile/evodev/connectors/opencode.py)): MCP stdio server (`evodev-mcp`) & session harvester.
  - `GeminiCLIConnector` ([`evodev/connectors/gemini.py`](file:///d:/programming%20work/vibe%20extension%20profile/evodev/connectors/gemini.py)): `.agents/hooks.json` lifecycle hooks & MCP integration.
  - `KiloCodeConnector` ([`evodev/connectors/kilocode.py`](file:///d:/programming%20work/vibe%20extension%20profile/evodev/connectors/kilocode.py)): `.kilo/mcp.json` tool integration.
  - `HermesConnector` ([`evodev/connectors/hermes.py`](file:///d:/programming%20work/vibe%20extension%20profile/evodev/connectors/hermes.py)): Tool schema generator (`evodev_retrieve_memory`, `evodev_report_outcome`) creating `hermes_config.json`.
  - `GenericAdapter` ([`evodev/connectors/generic.py`](file:///d:/programming%20work/vibe%20extension%20profile/evodev/connectors/generic.py)): Universal JSON-IPC and REST adapter.

### D. Specialist Delegation & Orchestration
Managed by `SpecialistOrchestrator` ([`evodev/orchestration/orchestrator.py`](file:///d:/programming%20work/vibe%20extension%20profile/evodev/orchestration/orchestrator.py)):
- **Specialist Roles**: `implementer`, `code_reviewer`, `test_engineer`, `debugging_specialist`, `documentation_specialist`, `security_reviewer`.
- **Human Approval Gates**: Sensitive or high-impact operations enter `WAITING_APPROVAL` and require explicit user authorization before execution.
- **Operational Guardrails**: Enforces concurrency limits (`max_concurrent_tasks`), step timeouts, task cancellation, and structured evidence aggregation. Returns `TaskStatus.UNSUPPORTED` if a suitable agent is unavailable.

### E. Safe Checkpoints & Rollback
Managed by `CheckpointManager` ([`evodev/checkpoints/manager.py`](file:///d:/programming%20work/vibe%20extension%20profile/evodev/checkpoints/manager.py)):
- **Git Checkpoints**: Captures reviewable uncommitted diffs, affected file lists, and patch snapshots without destructive repository resets (`git reset --hard` is forbidden).
- **SQLite Database Checkpoints**: Atomic SQLite WAL checkpoints with point-in-time snapshot backup and safe rollback.
- **Profile Checkpoints**: Standalone versioned `.vxp` packages preserving experience state.

### F. Persistent Local Background Scheduler
Managed by `SchedulerEngine` ([`evodev/scheduler/engine.py`](file:///d:/programming%20work/vibe%20extension%20profile/evodev/scheduler/engine.py)):
- Independent background daemon and persistent job store in SQLite table `scheduled_jobs`.
- Supported schedules: `hourly`, `daily`, `weekly`, `every:30m`, or custom second intervals.
- Handles reboots, prevents duplicate executions, logs execution history, and manages maintenance jobs (health checks, memory consolidation, benchmark runs).

### G. Model & Provider Routing
Managed by `ModelRouter` ([`evodev/routing/router.py`](file:///d:/programming%20work/vibe%20extension%20profile/evodev/routing/router.py)):
- Task-based selection for EvoDev-managed jobs across Anthropic, OpenAI, Gemini, Local Ollama, and DeepSeek.
- Factors in latency preference (`low`, `balanced`, `thorough`), model capabilities (`code_generation`, `security_audit`, `architecture`, `fast_edit`), cost estimation, and user-defined provider restrictions. Zero-cost local models receive preference where capability requirements are satisfied.

### H. Native Windows Desktop Application (Tkinter/ttk)
Located in [`evodev/gui/`](file:///d:/programming%20work/vibe%20extension%20profile/evodev/gui/):
- Professional dark slate theme (`#0f172a`, `#1e293b`), responsive layouts, and accessible navigation.
- **14 Modular Views**: Overview & Telemetry, Experience Inspector, Categorized Memory, Self-Improving Skills, Verified Lessons, Bayesian Strategies, Observable Experiences, Specialist Orchestration, Background Scheduler, Safe Checkpoints, Empirical Benchmarks, Multi-Agent Connectors, Diagnostic Doctor, and Safe Uninstallation.
- **Zero-Freeze Overview & Telemetry**:
  - *Cached CLI Discovery*: `OpenCodeConnector` and `KiloCodeConnector` cache executable detection and version lookups, eliminating repeated blocking 1.7s subprocess invocations on Windows.
  - *Async Diagnostics Dispatch*: `OverviewView.refresh()` offloads connector diagnostics to `WorkerPool.run_async()`, updating UI cards safely on the main thread without freezing.
  - *Optimized Storage Queries*: `StrategyRepository.count_by_profile` performs an immediate `SELECT COUNT(*)` query rather than loading full Pydantic model lists.
- Off-thread worker pool with thread-safe `queue.Queue` dispatch ensuring zero UI freeze across all views.
- Launchable via `evodev gui` or standalone Windows executable packaged with PyInstaller.


### I. Portable Experience Profiles (.vxp v2)
Managed by `ProfileArchiveFormat` ([`evodev/profiles/format.py`](file:///d:/programming%20work/vibe%20extension%20profile/evodev/profiles/format.py)) and `ProfileInspector` ([`evodev/profiles/inspector.py`](file:///d:/programming%20work/vibe%20extension%20profile/evodev/profiles/inspector.py)):
- ZIP container bundling `manifest.json`, `lessons.json`, `strategies.json`, `preferences.json`, `benchmarks.json`, `memories.json`, and `skills.json`.
- Dual cryptographic checksum verification (`integrity.sha256`) guaranteeing complete backwards compatibility with legacy v1 `.vxp` packages.
- Optional AES-256-GCM authenticated encryption with PBKDF2 key derivation.

### J. Safe Data Lifecycle & Uninstallation
Managed by `UninstallerEngine` ([`evodev/lifecycle/uninstaller.py`](file:///d:/programming%20work/vibe%20extension%20profile/evodev/lifecycle/uninstaller.py)):
- Dry-run preview (`evodev uninstall --dry-run`).
- Removes only EvoDev-owned database files, configuration, and EvoDev-specific keys in agent configs.
- **Never deletes or modifies external `.vxp` profile archives or backups.**

---

## 3. Implemented File & Directory Structure

```text
d:/programming work/vibe extension profile/
├── README.md                           # Platform documentation, architecture & quickstart
├── pyproject.toml                      # Package build configuration, deps & CLI scripts
├── memory.md                           # Persistent project context & architecture memory
├── evodev.spec                         # PyInstaller Windows standalone packaging spec
├── .gitignore                          # Exclusions for temporary, cache, and db files
├── docs/
│   ├── architecture.md                 # Technical design & scoring equations
│   ├── packaging.md                    # Windows PyInstaller build documentation
│   ├── threat_model.md                 # Security analysis & trust boundaries
│   ├── plan.md                         # Implementation phases & acceptance criteria
│   ├── profile_format_spec.md          # .vxp archive & cryptographic specification
│   ├── opencode_integration.md         # OpenCode MCP & session harvester guide
│   ├── gemini_cli_integration.md       # Gemini CLI hooks.json guide
│   └── user_guide.md                   # Operational walkthrough
├── evodev/
│   ├── __init__.py                     # Package version & product name
│   ├── __main__.py                     # Entry point for `python -m evodev`
│   ├── config.py                       # Global settings and environment overrides
│   ├── models/
│   │   ├── events.py                   # Normalized event hierarchy (Task, Tool, Error, Test, Finish)
│   │   ├── experience.py               # ExperienceRecord, Lesson, StrategyRecord, Evidence, Provenance
│   │   ├── memory.py                   # MemoryCategory, MemoryItem, EpistemicType
│   │   ├── skills.py                   # Skill, SkillVersion, SkillPrerequisite, ProcedureStep, SkillEvaluation
│   │   ├── checkpoints.py              # CheckpointRecord, CheckpointType (GIT, DATABASE, PROFILE)
│   │   ├── scheduler.py                # ScheduledJob, JobType, JobStatus
│   │   ├── orchestration.py            # OrchestrationTask, DelegationStep, SpecialistRole, TaskStatus
│   │   ├── routing.py                  # ModelCapability, LatencyTier, RoutingDecision
│   │   └── profile.py                  # ProfileManifest, ProfilePackage, ProfileVersion, ProfileStats
│   ├── storage/
│   │   ├── db.py                       # SQLite connection pool with WAL mode & multi-thread closure
│   │   ├── migrations.py               # Schema migrations (v1 base + v2 evolution tables)
│   │   └── repositories.py             # CRUD repos: Profiles, Lessons, Strategies, Events, Benchmarks, Memories, Skills, Checkpoints, Schedules
│   ├── security/
│   │   ├── redactor.py                 # Multi-pattern regex & Shannon entropy credential scrubber
│   │   ├── validator.py                # Zip-Slip, path sandbox, and archive size validator
│   │   └── crypto.py                   # SHA-256 digests, HMAC, and AES-256-GCM encryption
│   ├── collector/
│   │   ├── normalizer.py               # Ingestion normalizer for external agent events
│   │   ├── git_tracker.py              # Repository diff and branch status inspection
│   │   └── collector_service.py        # Active session buffer, task lifecycle, and experience synthesis
│   ├── learning/
│   │   ├── extractor.py                # Lesson extraction with verification gate & generalization
│   │   ├── strategy_tracker.py         # Bayesian success/failure/regression outcome engine
│   │   └── consolidator.py             # Deduplication, provenance merging, promotion, contradiction resolution
│   ├── memory/
│   │   ├── __init__.py                 # Export MemoryManager
│   │   └── manager.py                  # 8-partition memory engine with scope guards & redaction
│   ├── skills/
│   │   ├── __init__.py                 # Export SkillEngine, SkillRenderer, SkillEvaluator
│   │   ├── engine.py                   # Skill creation, version proposing, promotion, rollback
│   │   ├── evaluator.py                # Automated evaluation runs with untrusted script guardrails
│   │   └── renderer.py                 # Multi-agent rendering (Human Markdown, MCP tool, Hermes prompt)
│   ├── checkpoints/
│   │   ├── __init__.py                 # Export CheckpointManager
│   │   └── manager.py                  # Reviewable Git diffs, SQLite WAL snapshots, .vxp profile versions
│   ├── scheduler/
│   │   ├── __init__.py                 # Export SchedulerEngine
│   │   └── engine.py                   # Persistent SQLite-backed maintenance job runner
│   ├── orchestration/
│   │   ├── __init__.py                 # Export SpecialistOrchestrator
│   │   └── orchestrator.py             # 6-role specialist delegation with approval gates & concurrency limits
│   ├── routing/
│   │   ├── __init__.py                 # Export ModelRouter
│   │   └── router.py                   # Multi-provider model routing with latency & cost optimization
│   ├── retrieval/
│   │   ├── ranker.py                   # Multi-factor relevance scoring with privacy guard
│   │   ├── engine.py                   # Candidate querying and score thresholding
│   │   └── context_assembler.py        # Markdown context formatting for coding agents
│   ├── profiles/
│   │   ├── __init__.py                 # Export ProfileManager, ProfileInspector, and core models
│   │   ├── format.py                   # .vxp v2 archive format (memories + skills + dual checksum)
│   │   ├── manager.py                  # Profile lifecycle: create, rename, duplicate, export, import, rollback
│   │   └── inspector.py                # Experience Inspector & Profile Analytics service
│   ├── connectors/
│   │   ├── contract.py                 # Unified AgentConnector protocol & normalized schemas
│   │   ├── manager.py                  # Central ConnectorManager & ConnectorRegistry with failure isolation
│   │   ├── base.py                     # BaseAgentConnector helper
│   │   ├── simulation.py               # Deterministic developer workflow simulation adapter
│   │   ├── opencode.py                 # OpenCode connector (MCP configuration & session harvester)
│   │   ├── opencode_mcp.py             # Stdio MCP JSON-RPC 2.0 server for OpenCode
│   │   ├── gemini.py                   # Gemini CLI / Antigravity hooks & MCP generator
│   │   ├── gemini_hook.py              # Hook CLI dispatcher (PreInvocation, PostToolUse, Stop)
│   │   ├── kilocode.py                 # Kilo Code MCP tool connector
│   │   ├── hermes.py                   # Nous Research Hermes Agent tool connector & config generator
│   │   └── generic.py                  # Universal REST & JSON-IPC adapter for any IDE
│   ├── gui/
│   │   ├── __init__.py                 # GUI entry point `launch_gui`
│   │   ├── __main__.py                 # Direct module invocation: `python -m evodev.gui`
│   │   ├── app.py                      # Main desktop window with 14 modular views & background cleanup
│   │   ├── styles.py                   # Dark slate design system tokens (Colors, Fonts, Spacing)
│   │   ├── workers.py                  # Off-thread WorkerPool with thread-safe queue dispatch
│   │   ├── components/                 # Reusable components: MetricCard, ScrollableFrame, Dialogs
│   │   └── views/                      # 14 Modular views: Overview, Inspector, Memory, Skills, Lessons, Strategies, Experiences, Orchestration, Scheduler, Checkpoints, Benchmarks, Connectors, Doctor, Uninstall
│   ├── lifecycle/
│   │   ├── __init__.py                 # Export UninstallerEngine
│   │   └── uninstaller.py              # Safe uninstallation engine preserving external .vxp archives
│   ├── cli/
│   │   ├── __init__.py                 # CLI package init
│   │   └── main.py                     # Typer + Rich CLI application (all subcommands)
│   └── api/
│       ├── __init__.py                 # API package init
│       └── server.py                   # FastAPI daemon (REST API, inspector routes, dashboard)
└── tests/
    ├── test_benchmarks.py              # Unit tests for benchmark suite proving measurable improvement
    ├── test_checkpoints.py             # Unit tests for Git, Database, and Profile checkpoints
    ├── test_cli.py                     # Unit tests for CLI commands and FastAPI daemon endpoints
    ├── test_collector.py               # Unit tests for event normalization and session service
    ├── test_connectors.py              # Unit tests for OpenCode, OpenCode MCP, Gemini, and Generic
    ├── test_connectors_unified.py      # Contract compliance, registry, cross-agent learning, redaction
    ├── test_gui_native.py              # Tkinter app construction, view switching, worker thread safety
    ├── test_hermes_connector.py        # Hermes connector contract, tool schemas, outcome reporting
    ├── test_inspector.py               # Archive analysis, v2 schema, storage analytics, expertise metrics
    ├── test_learning.py                # Extraction with verification gate, consolidation, contradictions
    ├── test_memory.py                  # 8 memory partitions, scope guards, secret redaction, consolidation
    ├── test_models.py                  # Events, experience, strategy records, and profile serialization
    ├── test_orchestration.py           # Specialist delegation, approval gates, concurrency, cancellation
    ├── test_profiles.py                # Profile CRUD, encrypted export/import, version rollback
    ├── test_retrieval.py               # Multi-factor ranking, project isolation, promoted lesson retrieval
    ├── test_routing.py                 # ModelRouter capability matching, latency tiers, cost optimization
    ├── test_scenarios.py               # End-to-end scenarios A, B, C, D, E, F
    ├── test_scheduler.py               # Persistent SQLite job scheduling, run-pending, error isolation
    ├── test_security.py                # Secret redactor, Zip-Slip / Zip-Bomb validator, AES-GCM crypto
    ├── test_skills.py                  # Skill creation, rendering, untrusted guardrails, promotion, rollback
    ├── test_storage.py                 # SQLite WAL mode, migrations, profile version history
    ├── test_uninstall.py               # Safe uninstallation, dry-run, external archive preservation
    └── test_vxp_v2.py                  # .vxp v2 format packing/unpacking & v1 backwards compatibility
```

---

## 4. Installed Coding Agent Status
- **OpenCode**: Installed globally (`v1.19.0`) at `C:\Users\rudraksh\AppData\Roaming\npm\node_modules\opencode-ai`.
  - Configured via `opencode.json` with MCP stdio server `python -m evodev.connectors.opencode_mcp`.
  - Tool calls supported: `evodev_get_lessons`, `evodev_record_outcome`, `evodev_report_verification`.
- **Gemini CLI / Antigravity**: Config detected in `C:\Users\rudraksh\AppData\Roaming` / `.gemini`.
  - Integrates via `.agents/hooks.json` (`PreInvocation`, `PostToolUse`, `Stop`) running `python -m evodev.connectors.gemini_hook`.
  - Also integrates via `.agents/mcp_config.json`.
- **Kilo Code**:
  - Integrates via `.kilo/mcp.json` running `evodev-mcp` stdio server.
- **Nous Research Hermes Agent**:
  - Integrates via `hermes_config.json` exposing tool schemas `evodev_retrieve_memory` and `evodev_report_outcome`.

---

## 5. Automated Verification Status
- **Total Tests**: **110 passed**, 0 failed (100% passing across all 23 test suites).
- **Test Suite Breakdown**:
  - `tests/test_benchmarks.py`: 1 passed
  - `tests/test_checkpoints.py`: 3 passed
  - `tests/test_cli.py`: 5 passed
  - `tests/test_collector.py`: 2 passed
  - `tests/test_connectors.py`: 5 passed
  - `tests/test_connectors_unified.py`: 10 passed
  - `tests/test_gui_native.py`: 9 passed
  - `tests/test_hermes_connector.py`: 3 passed
  - `tests/test_inspector.py`: 12 passed
  - `tests/test_learning.py`: 3 passed
  - `tests/test_memory.py`: 5 passed
  - `tests/test_models.py`: 4 passed
  - `tests/test_orchestration.py`: 4 passed
  - `tests/test_profiles.py`: 4 passed
  - `tests/test_retrieval.py`: 2 passed
  - `tests/test_routing.py`: 3 passed
  - `tests/test_scenarios.py`: 6 passed
  - `tests/test_scheduler.py`: 3 passed
  - `tests/test_security.py`: 6 passed
  - `tests/test_skills.py`: 4 passed
  - `tests/test_storage.py`: 4 passed
  - `tests/test_uninstall.py`: 10 passed
  - `tests/test_vxp_v2.py`: 2 passed

---

## 6. Architecture Visualization (Archify)
- **Active Diagram**: [EvoDev System Architecture v1.0.0](file:///d:/programming%20work/vibe%20extension%20profile/.archify/architecture-evodev-system-20261023-192800/evodev-system.html)
- **Candidate Specification**: [candidate.json](file:///d:/programming%20work/vibe%20extension%20profile/.archify/architecture-evodev-system-20261023-192800/candidate.json)
- **Quality Profile**: `showcase` (validated with zero crossings, proper corridors, and passing real-browser delivery check).
- **Topology**:
  - **External**: AI Coding Agents (`OpenCode`, `Gemini CLI / Antigravity`, `Kilo Code`, `Nous Research Hermes Agent`).
  - **Boundary Frame**: EvoDev Core Engine encompassing:
    - *Column 1*: Native Desktop GUI (`evodev.gui`), Unified Connectors (`evodev.connectors`), Security Boundary (`evodev.security`), Collector Service (`evodev.collector`).
    - *Column 2*: Specialist Delegation Orchestrator (`evodev.orchestration`), Multi-factor Bayesian Retrieval Engine (`evodev.retrieval`), Learning Engine (`evodev.learning`), Empirical Verification Gate (`evodev.learning.extractor`).
    - *Column 3*: Self-Improving Skills Engine (`evodev.skills`), Persistent Categorized Memory (`evodev.memory`), SQLite WAL Store (`evodev.storage.db`), Automation Scheduler (`evodev.scheduler`).
    - *Column 4*: Safe Checkpoints (`evodev.checkpoints`), Portable Profile Engine (`.vxp` v2) (`evodev.profiles`).

---

## 7. Common Operations Quick Reference (Windows PowerShell)

```powershell
# 1. Native Desktop GUI
evodev gui
python -m evodev.gui

# 2. System Diagnostics & Health
evodev doctor
evodev status

# 3. Persistent Memory Operations
evodev memory list [--category architecture]
evodev memory search "FastAPI memory leak"
evodev memory add "Hexagonal Architecture rule" --category architecture --content '{"pattern": "ports_and_adapters"}'
evodev memory consolidate
evodev memory delete <memory_id> [--hard]

# 4. Self-Improving Skills
evodev skills list
evodev skills create "TDD Workflow" --description "Test-driven development procedure" --instructions "1. Red, 2. Green, 3. Refactor"
evodev skills view <skill_id> --format [markdown|mcp|hermes]
evodev skills evaluate <skill_id>

# 5. Safe Checkpoints & Rollback
evodev checkpoints list
evodev checkpoints create "Pre-refactor snapshot" --type [git|database|profile]
evodev checkpoints restore <checkpoint_id> -y

# 6. Background Scheduler
evodev schedule list
evodev schedule add "Daily Maintenance" --job-type health_check --schedule daily
evodev schedule run-pending
evodev schedule delete <job_id>

# 7. Agent Connectors
evodev connectors list
evodev connectors install-opencode
evodev connectors install-gemini
evodev connectors install-kilo
evodev connectors install-hermes

# 8. Profile Portability (.vxp v2)
evodev profiles list
evodev profiles create WorkProfile --domain backend
evodev profiles activate WorkProfile
evodev profiles export WorkProfile ./work.vxp [--password SecretKey123]
evodev profiles import ./work.vxp --activate
evodev profiles inspect ./work.vxp
evodev profiles history WorkProfile
evodev profiles rollback WorkProfile 1.0.0

# 9. Safe Uninstallation
evodev uninstall --dry-run
evodev uninstall --backup -y

# 10. Run Full Automated Test Suite
python -m pytest tests/ -v
```
