# EvoDev Gemini CLI & Antigravity Integration Guide

## 1. Overview
EvoDev integrates with **Gemini CLI** and **Antigravity** through the official **Lifecycle Hooks (`hooks.json`)** and **MCP (`mcp_config.json`)** extension architectures.

This allows EvoDev to:
1. Ingest real-time tool executions, errors, and verification results without polling.
2. Inject verified lessons directly into the agent context via `PreInvocation` ephemeral messages.
3. Automatically finalize experience records when a conversation terminates (`Stop` hook).

---

## 2. Setting Up Gemini CLI / Antigravity

Run inside your workspace:
```bash
evodev connectors gemini install
```
This automatically provisions `.agents/hooks.json` and `.agents/mcp_config.json` in your project root.

### `hooks.json` Structure
```json
{
  "evodev-experience-layer": {
    "enabled": true,
    "PreInvocation": [
      {
        "type": "command",
        "command": "python -m evodev.connectors.gemini_hook pre-invocation",
        "timeout": 15
      }
    ],
    "PostToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "python -m evodev.connectors.gemini_hook post-tool-use",
            "timeout": 15
          }
        ]
      }
    ],
    "Stop": [
      {
        "type": "command",
        "command": "python -m evodev.connectors.gemini_hook stop",
        "timeout": 15
      }
    ]
  }
}
```

---

## 3. Hook Execution Flow

```
[Agent Start / User Prompt]
           |
           v
+--------------------------+
| PreInvocation Hook       | ---> Injects verified lessons from active profile
+--------------------------+      into agent context via `ephemeralMessage`
           |
           v
[Agent Executes Tool]
           |
           v
+--------------------------+
| PostToolUse Hook         | ---> Records tool args, exit code, stdout/stderr,
+--------------------------+      errors observed, or test runs into EvoDev
           |
           v
[Agent Concludes / Stop]
           |
           v
+--------------------------+
| Stop Hook                | ---> Finalizes ExperienceRecord, triggers lesson
+--------------------------+      extractor, updates strategy Bayesian statistics
```

---

## 4. MCP Server Registration (`mcp_config.json`)

To also expose explicit EvoDev tools to Gemini CLI / Antigravity:
```json
{
  "mcpServers": {
    "evodev": {
      "command": "python",
      "args": ["-m", "evodev.connectors.opencode_mcp"]
    }
  }
}
```
Tools exposed:
- `evodev_get_lessons`: Search verified lessons manually during complex workflows.
- `evodev_record_outcome`: Record strategy success, failure, or regression.
- `evodev_report_verification`: Report passing build/test suite evidence.
