# EvoDev Comprehensive User Guide

## 1. Introduction
Welcome to **EvoDev**, a local-first persistent experience and learning layer that works alongside existing AI coding agents (OpenCode, Gemini CLI, Antigravity, and generic IDE harnesses).

As you develop software—fixing bugs, resolving compiler mismatches, configuring build tools, refactoring code, and passing tests—EvoDev observes verified actions, extracts generalized lessons with provenance, tracks empirical strategy success rates, and packages your accumulated intelligence into portable **Experience Profiles (`.vxp`)**.

When you switch from your first six projects to a seventh, brand-new project, EvoDev immediately retrieves relevant, verified strategies learned previously without foundation model training.

---

## 2. Quickstart

### Step 1: Initialize EvoDev
Run in your terminal:
```bash
python -m evodev.cli.main init --name PersonalCodingExpert
```
This creates your local SQLite database (`~/.evodev/evodev.db`) in WAL mode and activates your initial profile.

### Step 2: Check System Health
```bash
python -m evodev.cli.main doctor
```
Verifies SQLite connectivity, write permissions, secret redaction engine, and agent connectors.

---

## 3. Working with Portable Profiles (`.vxp`)

Profiles allow you to preserve, name, version, export, and transfer accumulated experience across machines.

### Creating and Switching Profiles
```bash
# Create dedicated domain profiles
python -m evodev.cli.main profiles create AndroidExpert --domain mobile
python -m evodev.cli.main profiles create WebDevPro --domain web

# List profiles
python -m evodev.cli.main profiles list

# Activate a profile
python -m evodev.cli.main profiles activate AndroidExpert
```

### Exporting and Importing
```bash
# Export active profile to .vxp archive
python -m evodev.cli.main profiles export AndroidExpert ./AndroidExpert.vxp

# Export with authenticated AES-256-GCM encryption
python -m evodev.cli.main profiles export AndroidExpert ./AndroidExpert.vxp --password "SecretKey123!"

# Import on a fresh machine
python -m evodev.cli.main profiles import ./AndroidExpert.vxp --activate
```

### Version Checkpoints and Rollback
When experimenting with risky workflows, you can create version checkpoints and restore previous states:
```bash
# Save checkpoint
python -m evodev.cli.main profiles history AndroidExpert

# Roll back to earlier version
python -m evodev.cli.main profiles rollback AndroidExpert 1.0.1
```

---

## 4. Coding Agent Integrations

### OpenCode (First-Class Integration)
1. In your project repository:
   ```bash
   python -m evodev.cli.main connectors install-opencode
   ```
2. OpenCode will now recognize EvoDev MCP tools:
   - `evodev_get_lessons`: Queries applicable lessons.
   - `evodev_record_outcome`: Records strategy success/failure.
   - `evodev_report_verification`: Records verified test runs.

### Gemini CLI / Antigravity
1. In your workspace root:
   ```bash
   python -m evodev.cli.main connectors install-gemini
   ```
2. Automatically installs `.agents/hooks.json` to inject lessons on `PreInvocation`, track executions on `PostToolUse`, and finalize sessions on `Stop`.

---

## 5. Running the Local Dashboard

Start the local service and visual telemetry dashboard:
```bash
python -m evodev.cli.main serve --port 8765
```
Open [http://127.0.0.1:8765](http://127.0.0.1:8765) in your browser to view:
- Live active profile status and storage consumption.
- Recently learned lessons with confidence badges and scope tags.
- Bayesian strategy rankings.
- Empirical benchmark runner comparing Base Agent vs Experienced Agent.
- Real-time diagnostic health probes.

---

## 6. Experience Inspector & Profile Analytics

The **Experience Inspector** (`🔍 Experience Inspector` in the dashboard sidebar, or `evodev profiles inspect <name>` in CLI) provides full diagnostic transparency into your accumulated developer knowledge without cloud telemetry.

### Interface Overview

```
+-----------------------------------------------------------------------------------------+
| [⚡ EvoDev]  Profile: AndroidExpert (v1.0.0) [ACTIVE RUNTIME] [Schema v1.0.0] [SHA-256] |
+-----------------------------------------------------------------------------------------+
|  ARCHIVE SIZE  |  UNCOMPRESSED  |  EXPERIENCES  |  VERIFIED  |  CANDIDATE  |  STRATEGIES|
|    2.2 KB      |     3.8 KB     |       1       |     1      |      1      |     1      |
+-----------------------------------------------------------------------------------------+
| [📦 Archive Analysis] [📊 Expertise] [🔎 Knowledge Explorer] [💾 Storage] [⏱️ Timeline]  |
+-----------------------------------------------------------------------------------------+
```

### 1. Real `.vxp` Archive Analysis
- Inspects real ZIP container entries: `manifest.json`, `lessons.json`, `strategies.json`, `preferences.json`, `benchmarks.json`, and `integrity.sha256`.
- Shows real measured uncompressed sizes, compressed sizes, compression ratio savings, and parsed record counts.
- Recomputes and verifies the canonical SHA-256 payload digest.
- Detects corrupt archives, encrypted archives (AES-256-GCM), and unsupported schema versions.

### 2. Expertise & Competence Visualizations
- Interactive breakdown by **Domains**, **Technologies**, **Frameworks**, and **Task Categories**.
- **Observed Activity**: Total task runs, attempts, and observations accumulated over development sessions.
- **Verified Competence**: Rigorously calculated verified success percentage based on passing empirical verification evidence (tests, clean compiler, linter) and Bayesian strategy scores:
  $$\text{Competence} = \frac{\text{Verified Units} + 1}{\text{Observed Units} + 2} \times 100\%$$

### 3. Knowledge Explorer
- Search and filter lessons, strategies, projects, technologies, preferences, and benchmarks.
- Filters by text query, scope (`GLOBAL`, `DOMAIN`, `TECHNOLOGY`, `PREFERENCES`, `PROJECT`), and verification status (`Verified Only` vs `Candidate Only`).

### 4. Detailed Record Inspector & Contradiction Detection
- Clicking **Inspect** on any record opens the detailed record inspector drawer.
- Displays full historical lineage: origin task IDs, origin project IDs, verification runs, failure count, and timestamps.
- Displays concrete verification evidence records (verification type, pass/fail state, test counts, compiler exit code, and redacted snippets).
- Automatically runs conflict detection against other lessons in the profile to report direct contradictions or anti-pattern collisions.

### 5. Safe Non-Silent Profile Mutations
- Allows modifying strategies, toggling active states, or deleting records.
- **Zero Silent Edits**: Any modification or deletion requires explicit user confirmation and automatically records an immutable version checkpoint before applying changes. You can restore prior states anytime via the rollback system.

### 6. Storage & Process Telemetry
- Measures the exact physical footprint of:
  - Compressed `.vxp` packages
  - Uncompressed JSON models
  - Primary SQLite database file
  - SQLite Write-Ahead Log (WAL) and Shared Memory (SHM) journals
  - Cache directories
  - Host process physical RAM (RSS) and Virtual Memory (VMS)

---

## 7. Security and Privacy Guarantees
- **Local-First**: EvoDev never sends source code or transcripts to external remote servers.
- **Automated Credential Masking**: 20+ secret patterns (OpenAI, Anthropic, GitHub, Google, AWS, private keys, JWTs) are scrubbed before storage.
- **Strict Scope Isolation**: Project-specific schema details and paths are strictly isolated and never leaked to other projects.
- **Archive Safety**: `.vxp` packages are protected against Zip-Slip path traversal attacks and zip-bomb decompression limits (max 50MB).

