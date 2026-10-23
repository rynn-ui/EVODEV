# EvoDev Phased Implementation Plan & Acceptance Criteria

## Project Structure Overview
```
d:/programming work/vibe extension profile/
├── docs/
│   ├── architecture.md
│   ├── threat_model.md
│   ├── plan.md
│   ├── profile_format_spec.md
│   ├── opencode_integration.md
│   ├── gemini_cli_integration.md
│   └── user_guide.md
├── evodev/
│   ├── __init__.py
│   ├── config.py                 # Core configurations and environment settings
│   ├── models/
│   │   ├── __init__.py
│   │   ├── events.py             # Event definitions (Task, Tool, Verification, Error, Feedback)
│   │   ├── experience.py         # ExperienceRecord, Lesson, StrategyScore, Scope, Evidence
│   │   └── profile.py            # ProfileManifest, ProfilePackage, Versioning models
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── db.py                 # SQLite WAL connection manager, thread safety
│   │   ├── migrations.py         # Schema versioning & migrations engine
│   │   └── repositories.py       # CRUD for experiences, lessons, strategies, profiles
│   ├── security/
│   │   ├── __init__.py
│   │   ├── redactor.py           # Multi-pattern regex & entropy credential sanitizer
│   │   ├── validator.py          # Zip Slip, path traversal, size limit & schema guards
│   │   └── crypto.py             # SHA-256 integrity, optional AES-256-GCM encryption
│   ├── collector/
│   │   ├── __init__.py
│   │   ├── normalizer.py         # Ingestion adapter for heterogenous agent events
│   │   ├── git_tracker.py        # Repository diff and file modification analyzer
│   │   └── collector_service.py  # Session tracking, idempotency, event lifecycle
│   ├── learning/
│   │   ├── __init__.py
│   │   ├── extractor.py          # Lesson extraction with distinction of facts/hypotheses
│   │   ├── strategy_tracker.py   # Bayesian success/failure/regression outcome engine
│   │   └── consolidator.py       # Deduplication, provenance merge, conflict detection
│   ├── retrieval/
│   │   ├── __init__.py
│   │   ├── ranker.py             # Multi-factor scoring (relevance, efficacy, recency)
│   │   ├── engine.py             # Hybrid lexical, semantic & scope retrieval
│   │   └── context_assembler.py  # Concise agent-ready context markdown generator
│   ├── profiles/
│   │   ├── __init__.py
│   │   ├── format.py             # .vxp archive packing/unpacking & validation
│   │   └── manager.py            # Profile lifecycle (create, export, import, rollback)
│   ├── evaluation/
│   │   ├── __init__.py
│   │   ├── benchmark.py          # Comparative evaluation (Base vs EvoDev vs Imported)
│   │   └── metrics.py            # Success rate, regression rate, latency, coverage
│   ├── connectors/
│   │   ├── __init__.py
│   │   ├── base.py               # Abstract connector interface
│   │   ├── simulation.py         # Deterministic simulated coding agent adapter
│   │   ├── opencode.py           # OpenCode connector (MCP + session DB harvester)
│   │   ├── gemini.py             # Gemini CLI connector (hooks.json + MCP injector)
│   │   └── generic.py            # Generic REST/CLI adapter
│   ├── cli/
│   │   ├── __init__.py
│   │   └── main.py               # Typer/Click CLI implementation
│   ├── api/
│   │   ├── __init__.py
│   │   └── server.py             # FastAPI local service for daemon & REST endpoints
│   └── dashboard/
│       ├── __init__.py
│       └── static/
│           ├── index.html        # High-aesthetic dark developer dashboard
│           ├── style.css         # Modern minimalist CSS
│           └── app.js            # Reactive vanilla JS (no external CDNs needed)
├── tests/
│   ├── __init__.py
│   ├── test_models.py
│   ├── test_storage.py
│   ├── test_security.py
│   ├── test_collector.py
│   ├── test_learning.py
│   ├── test_retrieval.py
│   ├── test_profiles.py
│   ├── test_benchmarks.py
│   ├── test_connectors.py
│   ├── test_cli.py
│   └── test_scenarios.py         # Full Scenarios A, B, C, D, E, F
├── pyproject.toml
└── README.md
```

---

## Phases & Acceptance Criteria

### Phase 1: Repository & Technical Design (Current)
- [x] Workspace tooling audit (Python 3.11, OpenCode 1.19.0, Gemini CLI / Antigravity custom root).
- [x] Technical Architecture document (`docs/architecture.md`).
- [x] Threat Model and security analysis (`docs/threat_model.md`).
- [x] Phased implementation plan with explicit acceptance criteria.

### Phase 2: Functional Core
- [ ] Pydantic validated data models (`models/events.py`, `models/experience.py`, `models/profile.py`).
- [ ] SQLite persistence with WAL mode and schema migration runner (`storage/db.py`, `storage/migrations.py`).
- [ ] Secret redaction engine (`security/redactor.py`) with 20+ credential patterns.
- [ ] Event collector and normalization pipeline (`collector/normalizer.py`, `collector/collector_service.py`).
- [ ] File change & Git diff tracker (`collector/git_tracker.py`).
- [ ] Local simulation adapter (`connectors/simulation.py`).
- [ ] Unit tests verifying event ingestion, redaction, persistence, and basic retrieval.

### Phase 3: Learning Engine
- [ ] Lesson extractor (`learning/extractor.py`) separating verified facts, user preferences, observed outcomes, and inferred lessons.
- [ ] Strategy tracker (`learning/strategy_tracker.py`) calculating Bayesian success probability, failure counts, regression frequency, and verification coverage.
- [ ] Multi-factor relevance ranker (`retrieval/ranker.py`) and context assembler (`retrieval/context_assembler.py`).
- [ ] Consolidator (`learning/consolidator.py`) merging duplicate lessons, updating provenance, and flagging contradictory advice.
- [ ] Comparative benchmark harness (`evaluation/benchmark.py`, `evaluation/metrics.py`).
- [ ] Tests verifying iterative learning, strategy ranking adjustment, and conflict detection.

### Phase 4: Portable Experience Profiles (`.vxp`)
- [ ] Profile format specification (`docs/profile_format_spec.md`).
- [ ] Profile archive packing/unpacking with Zip-Slip defense and zip-bomb size caps (`profiles/format.py`, `security/validator.py`).
- [ ] Profile lifecycle manager (`profiles/manager.py`): create, rename, duplicate, export, import, activate, deactivate, rollback version history.
- [ ] Optional cryptographic checksum verification and AES-256-GCM authenticated encryption (`security/crypto.py`).
- [ ] Tests verifying fresh database import, cross-environment activation, version history, and rollback.

### Phase 5: OpenCode Integration
- [ ] First-class OpenCode integration module (`connectors/opencode.py`).
- [ ] MCP Server for OpenCode exposing lesson query and outcome reporting tools.
- [ ] Session harvester parsing OpenCode JSON exports and direct SQLite db ingestion.
- [ ] Integration guide (`docs/opencode_integration.md`) and automated end-to-end tests.

### Phase 6: Gemini CLI / Antigravity Integration
- [ ] Gemini CLI integration module (`connectors/gemini.py`).
- [ ] Auto-generator for `hooks.json` supporting `PreInvocation` (context injection), `PostToolUse` (tool outcome recording), and `Stop` (session finalization).
- [ ] Integration guide (`docs/gemini_cli_integration.md`) and automated hook contract tests.

### Phase 7: CLI, Diagnostics & Dashboard
- [ ] Full Typer/Click CLI (`cli/main.py`) implementing `init`, `status`, `doctor`, `profiles *`, `experience *`, `benchmark *`, `retention *`.
- [ ] Health diagnostic system (`evodev doctor`) checking storage, file permissions, agent hooks, and database integrity.
- [ ] Local FastAPI server (`api/server.py`) and clean dark developer dashboard (`dashboard/static/*`).
- [ ] Tests verifying CLI commands, exit codes, and API endpoints.

### Phase 8: Comprehensive Evaluation & Release
- [ ] End-to-end test suite (`tests/test_scenarios.py`):
  - Scenario A: Cross-project learning across separate repositories.
  - Scenario B: Portable profile export, fresh database import, and activation.
  - Scenario C: Continued learning after import, versioning, and rollback.
  - Scenario D: Storage consumption, retention policies, and retrieval latency under load.
  - Scenario E: Malicious archive rejection, secret redaction, and malformed input safety.
  - Scenario F: Real/simulated coding agent execution.
- [ ] Complete documentation: `README.md`, `pyproject.toml`, user manuals, and configuration reference.
