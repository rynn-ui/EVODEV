# EvoDev OpenCode Integration Guide

## 1. Overview
EvoDev provides first-class native integration with **OpenCode** (tested against OpenCode v1.19.0).

OpenCode communicates with EvoDev through two complementary channels:
1. **Model Context Protocol (MCP)**: EvoDev runs as a local stdio MCP server (`evodev-mcp`), exposing real-time lesson retrieval, outcome reporting, and verification recording tools directly to OpenCode's reasoning loop.
2. **Session Harvester & Importer**: EvoDev can ingest completed OpenCode sessions either from `opencode export <sessionID> --sanitize` or directly from OpenCode's local database (`~/.local/share/opencode/opencode.db`).

---

## 2. Setting Up OpenCode with EvoDev

### Automatic Setup via EvoDev CLI
Run inside any project repository:
```bash
evodev connectors opencode install
```
This generates an `opencode.json` configuration file in the project directory:
```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "evodev": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "evodev.connectors.opencode_mcp"]
    }
  }
}
```

### Verifying Connection
Verify that OpenCode recognizes the MCP server:
```bash
opencode mcp list
```
Expected output:
```
Server      Type     Status
───────────────────────────
evodev      stdio    Connected
```

---

## 3. Available MCP Tools Exposed to OpenCode

| Tool Name | Parameters | Purpose |
| :--- | :--- | :--- |
| `evodev_get_lessons` | `task_description` (str), `domain` (str, opt), `technologies` (list, opt) | Injects verified previous lessons, file targets, and anti-patterns relevant to current task. |
| `evodev_record_outcome` | `task_id` (str), `strategy_name` (str), `outcome` ("success" \| "failure" \| "regression") | Records execution outcome and updates Bayesian confidence scores. |
| `evodev_report_verification` | `task_id` (str), `passed` (bool), `details` (str, opt) | Records empirical verification (test suite pass, compiler exit 0). |

---

## 4. Ingesting OpenCode Sessions

To ingest an existing OpenCode conversation and extract verified lessons into your active profile:
```bash
# Export from OpenCode
opencode export ses_ea172f1e0ffeSeFNS3ytnWtjX1 > session.json

# Ingest into EvoDev
evodev experience ingest-opencode session.json --project my-project-id
```
EvoDev normalizes all tool calls, redacts credentials, extracts candidate lessons, and consolidates them into the active experience profile.
