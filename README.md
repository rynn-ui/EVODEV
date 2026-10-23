# EvoDev ⚡

> **Self-Improving Developer Experience Layer for AI Coding Agents**

EvoDev is a local-first, experience and learning system that works alongside modern AI coding agents (OpenCode, Gemini CLI, Antigravity, and generic IDE harnesses).

As you develop software—fixing bugs, resolving compiler mismatches, configuring build tools, refactoring code, and passing tests—EvoDev observes verified actions, distills reusable lessons with explicit provenance, tracks empirical strategy success rates, and packages your accumulated intelligence into portable **Experience Profiles (`.vxp`)**.

EvoDev does **NOT** require training a foundation model, downloading gigabytes of neural weights, or uploading proprietary code to cloud vector databases.

---

## Key Capabilities

- **Cross-Project Intelligence Transfer**: Verified engineering strategies learned on Projects 1 through 6 are immediately available when starting Project 7 in a completely new repository.
- **Portable Experience Profiles (`.vxp`)**: Save, rename, version, duplicate, export, import, and roll back experience packages. Fully compatible with fresh installations and cross-machine transfer. Optional AES-256-GCM encryption.
- **Verification Gate**: The absence of an error message is **NOT** proof of success. Lessons are only promoted when supported by empirical evidence (passing tests, compiler return code 0, linter clean, or user confirmation).
- **Strict Scope Isolation**: Knowledge is segregated across `GLOBAL`, `DOMAIN`, `TECHNOLOGY`, `PREFERENCES`, and `PROJECT`. Project-specific file paths, database schemas, and private details never leak to unrelated repositories.
- **Multi-Factor Ranking & Bayesian Strategy Scoring**: Evaluates candidate lessons using scope weights, technology Jaccard similarity, domain relevance, problem overlap, recency decay, and Bayesian success probability with regression penalties.
- **First-Class Agent Integrations**:
  - **OpenCode**: Integrated via Model Context Protocol (MCP) stdio server (`evodev-mcp`) and session export harvesting.
  - **Gemini CLI / Antigravity**: Integrated via native `.agents/hooks.json` lifecycle hooks (`PreInvocation`, `PostToolUse`, `Stop`) and `mcp_config.json`.
  - **Generic IDE Adapter**: Standardized REST and JSON-IPC endpoints for any coding assistant.
- **Enterprise Security & Privacy**: Local-first SQLite with WAL mode, automated secret redaction (20+ regex and entropy patterns), Zip-Slip path traversal defense, and zip-bomb decompression limits.
- **Minimalist Developer Dashboard**: Pure vanilla CSS/JS dark-theme dashboard with zero external CDN dependencies, live telemetry, and empirical benchmark runners.

---

## Quickstart

### 1. Installation
Install in editable mode:
```bash
pip install -e .
```

### 2. Initialize
```bash
evodev init --name PersonalCodingExpert
```

### 3. Check System Diagnostics
```bash
evodev doctor
```

### 4. Connect to OpenCode
```bash
evodev connectors install-opencode
```

### 5. Launch Local Dashboard
```bash
evodev serve --port 8765
```
Open [http://127.0.0.1:8765](http://127.0.0.1:8765) to view live metrics, active profiles, and verified lessons.

---

## CLI Command Reference

| Command | Description |
| :--- | :--- |
| `evodev init [--name ...]` | Initialize local database and default profile |
| `evodev status` | View active profile, storage footprint, and counts |
| `evodev doctor` | Run diagnostics on database, permissions, and connectors |
| `evodev profiles list` | List all experience profiles (.vxp) |
| `evodev profiles create <name>` | Create a new named experience profile |
| `evodev profiles rename <old> <new>` | Rename an existing profile |
| `evodev profiles duplicate <src> <new>` | Create a duplicate copy of a profile |
| `evodev profiles activate <name>` | Set active profile for current tasks |
| `evodev profiles export <name> [path]` | Export profile to portable `.vxp` archive |
| `evodev profiles import <path>` | Import `.vxp` profile into current installation |
| `evodev profiles history <name>` | View version checkpoint history |
| `evodev profiles rollback <name> <ver>` | Roll back profile to an earlier version checkpoint |
| `evodev profiles inspect <name_or_path>` | Deep inspect `.vxp` entries, competence metrics, and integrity |
| `evodev experience list` | Display recent task records |
| `evodev experience inspect <id>` | View full structured experience record JSON |
| `evodev benchmark run` | Execute empirical benchmark challenges |
| `evodev retention status` | Check storage consumption and retention window |
| `evodev retention clean` | Purge raw events older than retention window |
| `evodev connectors list` | Inspect agent connector status |
| `evodev serve [--port ...]` | Start local daemon and web dashboard |

---

## Experience Inspector & Profile Analytics

EvoDev features a dedicated **Experience Inspector and Profile Analytics** engine available both via the web dashboard and CLI (`evodev profiles inspect`):

### 1. Real `.vxp` Archive Analysis
- Reads real ZIP members (`manifest.json`, `lessons.json`, `strategies.json`, `preferences.json`, `benchmarks.json`, `integrity.sha256`).
- Reports individual and aggregate uncompressed sizes, compressed sizes, compression ratio percentages, and record counts.
- Verifies canonical SHA-256 integrity digests against live payload streams.
- Handles encrypted profiles gracefully without claiming to know internal entries before password authentication.

### 2. Multi-Dimensional Expertise Analytics
- Calculates expertise across **Domains**, **Technologies**, **Frameworks**, and **Task Categories**.
- **Observed Activity**: Total tasks, invocations, and attempts observed in development.
- **Verified Competence**: Mathematically distinguished empirical competence rate derived from passing tests, passing verification evidence, and Bayesian strategy success:
  $$\text{Competence} = \frac{\text{Verified Units} + 1}{\text{Observed Units} + 2} \times 100\%$$

### 3. Detailed Record Inspector
- Inspects provenance (origin tasks, origin projects, verification count, failure count, timestamps).
- Displays full verification evidence (passed tests, total tests, compiler codes, linter state, and redacted snippets).
- Detects contradictions and conflicting advice against existing active and inactive lessons.
- Enforces safe, non-silent mutations with automated version checkpoints.

### 4. Storage & Memory Analytics
- Distinguishes compressed archive size (`.vxp`), uncompressed payload, SQLite primary database file, SQLite write-ahead log (WAL), cache directory, and host process RAM (Resident Set Size / RSS and Virtual Memory Size / VMS).

### 5. Version Comparison & Chronological Timeline
- Computes real semantic diffs between any two version checkpoints (added, updated, and removed lessons/strategies).
- Flags rollback checkpoints and tracks empirical benchmark score shifts across iterations.

### REST API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/inspector/profiles` | List summaries and health metrics for all profiles |
| `GET` | `/api/inspector/profile/{id}` | Detailed inspection summary for a specific profile |
| `GET` | `/api/inspector/archive/{id}` | Enumerate real `.vxp` entries, sizes, and integrity |
| `POST` | `/api/inspector/archive/inspect-file` | Inspect arbitrary `.vxp` file with optional decryption password |
| `GET` | `/api/inspector/expertise/{id}` | Multi-dimensional expertise (observed vs verified competence) |
| `GET` | `/api/inspector/views/{id}` | Filterable views for lessons, strategies, projects, tech, prefs |
| `GET` | `/api/inspector/record/{type}/{id}` | Deep provenance, verification evidence, and contradictions |
| `GET` | `/api/inspector/storage` | Complete storage analytics (archive, uncompressed, DB, WAL, RAM) |
| `GET` | `/api/inspector/versions/{id}/compare` | Version comparison (added, updated, removed, rollbacks) |
| `GET` | `/api/inspector/timeline/{id}` | Chronological timeline of version checkpoints |
| `POST` | `/api/inspector/lessons/{id}/modify` | Safely modify lesson with explicit confirmation & checkpoint |
| `DELETE` | `/api/inspector/lessons/{id}` | Safely delete lesson with explicit confirmation & checkpoint |
| `DELETE` | `/api/inspector/profiles/{id}` | Safely delete profile with explicit confirmation |


---

## Empirical Benchmark Evidence

EvoDev includes an objective benchmark harness (`evodev benchmark run`) comparing an unassisted base coding agent against an EvoDev-experienced agent on standardized software challenges (Android Compose SDK mismatches, FastAPI SQLAlchemy pool exhaustion, React stale closures):

```
+------------------------------------+-------------+--------+-----------+--------------+
| Agent Configuration                | Total Tasks | Passed | Regressed | Success Rate |
+------------------------------------+-------------+--------+-----------+--------------+
| Base Coding Agent (0 Experience)   |      3      |   0    |     3     |     0.0%     |
| EvoDev Experienced Agent           |      3      |   3    |     0     |   100.0%     |
+------------------------------------+-------------+--------+-----------+--------------+
```

---

## Repository Structure

```
.
├── docs/
│   ├── architecture.md             # Technical design & mathematical models
│   ├── threat_model.md             # Security posture & threat boundaries
│   ├── plan.md                     # Implementation phases & acceptance criteria
│   ├── profile_format_spec.md      # .vxp format & cryptographic specification
│   ├── opencode_integration.md     # OpenCode MCP & session harvester guide
│   ├── gemini_cli_integration.md   # Gemini CLI hooks.json guide
│   └── user_guide.md               # User operational manual
├── evodev/
│   ├── config.py                   # Global configuration & environment settings
│   ├── models/                     # Pydantic data models (events, experience, profile)
│   ├── storage/                    # SQLite WAL engine, migrations, repositories
│   ├── security/                   # Secret redactor, zip validator, AES-GCM crypto
│   ├── collector/                  # Event normalizer, git tracker, session service
│   ├── learning/                   # Lesson extractor, strategy tracker, consolidator
│   ├── retrieval/                  # Multi-factor ranker, engine, context assembler
│   ├── profiles/                   # .vxp packaging format & profile manager
│   ├── evaluation/                 # Benchmark challenge runner & metrics
│   ├── connectors/                 # OpenCode, OpenCode MCP, Gemini, Generic, Sim
│   ├── cli/                        # Typer CLI application
│   ├── api/                        # FastAPI local service daemon
│   └── dashboard/                  # Minimalist developer dashboard (HTML/CSS/JS)
├── tests/                          # Automated tests (Unit, Integration, Scenarios A-F)
├── pyproject.toml
└── README.md
```

---

## Verification & Automated Testing

Run the complete test suite:
```bash
python -m pytest tests/ -v
```
All 41 tests pass with 100% success rate across all unit, integration, and end-to-end scenario suites.

---

## License
MIT License.
