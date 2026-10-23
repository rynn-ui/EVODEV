# EvoDev Architecture & Technical Design

## 1. Executive Summary
**EvoDev** is a local-first, self-improving developer experience layer that operates alongside modern AI coding agents (such as OpenCode, Gemini CLI/Antigravity, and generic LLM-based coding harnesses).

EvoDev does not train foundational model weights, require a cloud database, or rely on paid third-party embedding APIs. Instead, it captures structured operational observations (tasks, errors, attempted strategies, diffs, tool outputs, test/build outcomes), distills them into validated reusable lessons with explicit provenance, tracks statistical efficacy per strategy, and delivers contextually scoped knowledge across disparate projects.

Accumulated intelligence is packaged into **Portable Experience Profiles (`.vxp`)**—portable, versioned, tamper-evident archives that can be exported, shared, imported into fresh environments, rolled back, or extended.

---

## 2. Core Architectural Pillars

```
+-----------------------------------------------------------------------------------+
|                            AI Coding Agent Ecosystem                              |
|   +-------------------+    +--------------------+    +------------------------+   |
|   |  OpenCode Agent   |    | Gemini CLI / AGY   |    | Generic Adapter / Sim  |   |
|   +---------+---------+    +---------+----------+    +-----------+------------+   |
+-------------|------------------------|---------------------------|----------------+
              | (Hooks / MCP / DB)     | (hooks.json / MCP)        | (REST / IPC)
              v                        v                           v
+-----------------------------------------------------------------------------------+
|                                EvoDev Core Engine                                 |
|                                                                                   |
|  +-----------------------------------------------------------------------------+  |
|  |                            Connectors Layer                                 |  |
|  |  - OpenCodeConnector (MCP + DB reader)                                      |  |
|  |  - GeminiCLIConnector (hooks.json + MCP generator)                         |  |
|  |  - SimulationAdapter (deterministic multi-task verification)                |  |
|  |  - GenericAdapter (REST / stdin-stdout IPC)                                 |  |
|  +-----------------------------------------------------------------------------+  |
|                                      |                                            |
|                                      v                                            |
|  +-----------------------------------------------------------------------------+  |
|  |                   Collector & Security Boundary                             |  |
|  |  - Event Normalizer (TaskStarted, ToolInvocation, ToolResult, TestResult)   |  |
|  |  - Secret Redactor (regex + entropy filters: keys, tokens, ssh credentials) |  |
|  |  - Git Tracker (diff analysis, churn, AST-free file impacts)                |  |
|  |  - Input / Traversal Validator (archive limits, path sanitization)          |  |
|  +-----------------------------------------------------------------------------+  |
|                    |                                             ^                |
|                    v                                             |                |
|  +-----------------------------------+         +-------------------------------+  |
|  |         Learning Engine           |         |       Retrieval Engine        |  |
|  | - Lesson Extractor (Fact vs Hyp)  |         | - Multi-factor Scoring        |  |
|  | - Strategy Tracker (Beta dist)    |         | - Scoped Filtering            |  |
|  | - Consolidator & Conflict Detector|         | - Context Markdown Assembly   |  |
|  +-----------------------------------+         +-------------------------------+  |
|                    \                                             /                |
|                     v                                           v                 |
|  +-----------------------------------------------------------------------------+  |
|  |                 Profile Manager & Experience Store                          |  |
|  |  - Knowledge Scopes: Global, Domain, Tech, Prefs, Project, Task             |  |
|  |  - SQLite (WAL mode, parameterized transactions, schema migrations)         |  |
|  |  - .vxp Profile Engine: Manifest, Lessons, Stats, Signatures, AES-GCM       |  |
|  |  - Versioning & Rollback Ledger                                             |  |
|  +-----------------------------------------------------------------------------+  |
+-----------------------------------------------------------------------------------+
              |                                            |
              v                                            v
+-----------------------------+              +-----------------------------+
|    CLI & Diagnostics        |              |  Local Dashboard & REST     |
|  - evodev profiles ...      |              |  - FastAPI Daemon           |
|  - evodev experience ...    |              |  - Minimalist Dark UI       |
|  - evodev benchmark ...     |              |  - Live Health & Telemetry  |
+-----------------------------+              +-----------------------------+
```

---

## 3. Knowledge Scopes & Promotion Policy

A foundational rule of EvoDev: **A project-specific implementation detail must never automatically pollute global strategy advice.**

Knowledge is segregated into explicit hierarchical scopes:
1. **`Task / Session`**: Transient operational state during an active session (e.g., intermediate syntax errors, scratch edits).
2. **`Project-Specific`**: Local conventions, schemas, internal paths, and project-locked quirks. Active only within that repository.
3. **`User Preferences`**: User-defined style requirements (e.g., "prefer pytest over unittest", "never use single-letter variables").
4. **`Technology & Framework`**: Reusable rules tied to specific runtimes, frameworks, and libraries (e.g., Python 3.11 typing quirks, Android Jetpack Compose state pitfalls, React 19 hook constraints).
5. **`Domain-Specific`**: Methodologies and patterns tied to problem domains (e.g., "OAuth2 token refresh race condition handling", "REST idempotency", "Android memory leak prevention in coroutine scopes").
6. **`Global Reusable Experience`**: Fundamental software engineering strategies that have repeatedly succeeded across multiple domains with zero regression.

### Deliberate Promotion Pipeline
- **Observation**: Action taken during a session + output recorded.
- **Candidate Lesson**: Inferred when a task transitions from failed/error to verified pass.
- **Verification Gate**: A lesson requires explicit verification evidence (passing tests, compiler exit 0, linter clear, or user confirmation). An absence of error messages does NOT suffice.
- **Promotion to Technology/Domain/Global**: Requires verified success across >= 2 independent sessions or tasks without negative regressions, meeting a confidence threshold ($\ge 0.70$).

---

## 4. Multi-Factor Strategy Scoring & Retrieval Algorithm

Retrieval balances relevance, proven efficacy, verification depth, and age:

$$\text{Score}(L, T) = w_s \cdot S_{\text{scope}} + w_t \cdot S_{\text{tech}} + w_d \cdot S_{\text{domain}} + w_p \cdot S_{\text{problem}} + w_e \cdot E_{\text{strategy}} - w_r \cdot R_{\text{penalty}} + \delta_{\text{recency}}$$

Where:
- $S_{\text{scope}}$: Scope match weight (Active project = 1.0, Tech match = 0.9, Domain match = 0.8, Global = 0.7).
- $S_{\text{tech}}$: Jaccard similarity between target project technologies and lesson applicable tech tags.
- $S_{\text{domain}}$: Match between current task domain and lesson domain.
- $S_{\text{problem}}$: Tokenized BM25 / trigram similarity between task problem description and lesson triggers.
- $E_{\text{strategy}}$: Historical success rate computed using Laplace-smoothed empirical Bayes:
  $$E = \frac{N_{\text{success}} + 1}{N_{\text{success}} + N_{\text{failure}} + 2}$$
- $R_{\text{penalty}}$: Regression penalty based on how often applying this strategy caused subsequent tests or builds to break.
- $\delta_{\text{recency}}$: Exponential time decay dampener for stale advice older than 180 days.

---

## 5. Portable Experience Profile (`.vxp`) Specification

A `.vxp` file is a ZIP archive containing:
1. `manifest.json`: Profile UUID, name, schema version, creation/export timestamps, parent profile lineage, checksums, author/agent metadata.
2. `lessons.json`: Array of verified, generalized lessons with provenance records, triggers, conditions, and recommendations.
3. `strategies.json`: Aggregate strategy statistics (attempts, successes, failures, regression rates).
4. `preferences.json`: Encoded user guidelines and scope constraints.
5. `benchmarks.json`: Measured empirical evaluations from baseline comparisons.
6. `integrity.sha256`: SHA-256 digest of payload contents to verify authenticity.
7. Optional authenticated encryption via AES-256-GCM with PBKDF2 key derivation.

Import Safety Guarantees:
- Never executes code during import.
- Validates all file paths against directory traversal (`../` or absolute path exploits).
- Limits decompression size (zip-bomb defense: max 50MB uncompressed limit).
- Validates schema against Pydantic models.

---

## 6. Integration Mechanisms

### 1. OpenCode
- **MCP Server (`evodev-mcp`)**: Exposes MCP tools (`evodev_get_lessons`, `evodev_record_outcome`, `evodev_report_verification`).
- **Session Harvester**: Ingests session transcripts and tool executions from OpenCode's local database (`~/.local/share/opencode/opencode.db`) or exported JSON.
- **Config Injector**: Automates adding EvoDev to project-level or global `opencode.json`.

### 2. Gemini CLI / Antigravity
- **Lifecycle Hooks (`hooks.json`)**:
  - `PreInvocation`: Injects active profile lessons into agent context via `injectSteps: [ { "ephemeralMessage": ... } ]`.
  - `PostToolUse`: Records tool outcomes, errors, and test executions.
  - `Stop`: Intercepts session termination to log final outcomes and trigger extraction.
- **MCP Integration (`mcp_config.json`)**: Exposes experience queries as native tools.

### 3. Generic Adapter & Local Simulation
- **CLI / REST Interface**: Enables any agent or test harness to send structured JSON events.
- **Simulation Harness**: Provides end-to-end multi-project reproduction tests without requiring active third-party LLM API keys.
