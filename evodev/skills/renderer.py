"""Cross-agent skill rendering into Markdown, MCP tool specifications, and agent prompts."""

from typing import Any, Dict, Optional

from evodev.models.skills import Skill, SkillVersion


class SkillRenderer:
    """Renders normalized EvoDev skills into agent-specific formats."""

    @staticmethod
    def render_markdown(skill: Skill, version: Optional[SkillVersion] = None) -> str:
        """Render a skill into standardized Markdown documentation for agents like Claude, Gemini, or Antigravity."""
        v = version or (skill.versions[0] if skill.versions else None)
        ver_tag = v.version if v else skill.current_version

        lines = [
            f"# Skill: {skill.name} (v{ver_tag})",
            f"> Category: `{skill.category}` | Status: `{skill.status.value.upper()}` | Scope: `{skill.scope.value.upper()}`",
            "",
            f"**Description**: {skill.description}",
            "",
        ]

        if v:
            if v.prerequisites:
                lines.append("## Prerequisites")
                for p in v.prerequisites:
                    req_badge = "*(Required)*" if p.required else "*(Optional)*"
                    lines.append(f"- **{p.name}** {req_badge}: {p.description}")
                lines.append("")

            lines.append("## System Instructions")
            lines.append(v.instructions)
            lines.append("")

            if v.procedures:
                lines.append("## Actionable Procedure Steps")
                for step in v.procedures:
                    lines.append(f"{step.step_number}. {step.instruction}")
                    if step.validation:
                        lines.append(f"   - *Verification*: `{step.validation}`")
                lines.append("")

            if v.validation_steps:
                lines.append("## Verification Criteria")
                for val in v.validation_steps:
                    lines.append(f"- [ ] {val}")
                lines.append("")

            if v.expected_outcomes:
                lines.append("## Expected Outcomes")
                for out in v.expected_outcomes:
                    lines.append(f"- {out}")
                lines.append("")

        return "\n".join(lines)

    @staticmethod
    def render_mcp_tool_description(skill: Skill, version: Optional[SkillVersion] = None) -> Dict[str, Any]:
        """Render skill as an OpenCode / Kilo Code Model Context Protocol (MCP) tool schema."""
        v = version or (skill.versions[0] if skill.versions else None)
        steps_summary = "; ".join(f"{s.step_number}. {s.instruction}" for s in v.procedures) if (v and v.procedures) else ""
        tool_name = f"skill_{skill.name.lower().replace(' ', '_').replace('-', '_')}"
        desc = skill.description
        if steps_summary:
            desc += f" (Procedure: {steps_summary})"
        return {
            "name": tool_name,
            "description": desc,
            "parameters": {
                "type": "object",
                "properties": {
                    "task_context": {
                        "type": "string",
                        "description": "Specific project problem or task details",
                    },
                },
                "required": ["task_context"],
            },
            "inputSchema": {
                "type": "object",
                "properties": {
                    "task_context": {
                        "type": "string",
                        "description": "Specific project problem or task details",
                    },
                },
                "required": ["task_context"],
            },
        }

    @staticmethod
    def render_hermes_prompt(skill: Skill, version: Optional[SkillVersion] = None) -> str:
        """Render skill into Hermes Agent structured tool guidance block."""
        v = version or (skill.versions[0] if skill.versions else None)
        inst = v.instructions if v else ""
        return (
            f"<skill name=\"{skill.name}\" version=\"{skill.current_version}\">\n"
            f"  <purpose>{skill.description}</purpose>\n"
            f"  <instructions>\n{inst}\n  </instructions>\n"
            f"</skill>"
        )
