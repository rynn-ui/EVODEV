"""Gemini CLI / Antigravity connector: Hooks generator, MCP configuration, and adapter."""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from evodev.connectors.base import BaseAgentConnector
from evodev.retrieval.context_assembler import ContextAssembler
from evodev.retrieval.engine import RetrievalEngine
from evodev.storage.repositories import LessonRepository, ProfileRepository


class GeminiCLIConnector(BaseAgentConnector):
    """Integrates Gemini CLI and Antigravity via lifecycle hooks and MCP."""

    def __init__(
        self,
        lesson_repo: Optional[LessonRepository] = None,
        profile_repo: Optional[ProfileRepository] = None,
    ):
        self.lesson_repo = lesson_repo
        self.profile_repo = profile_repo
        self.engine = (
            RetrievalEngine(lesson_repo, profile_repo)
            if (lesson_repo and profile_repo)
            else None
        )
        self.assembler = ContextAssembler()

    def get_name(self) -> str:
        return "GeminiCLI"

    def is_available(self) -> bool:
        """Check if Antigravity or Gemini config directory exists."""
        home = Path.home()
        gemini_dir = home / ".gemini"
        return gemini_dir.is_dir()

    def get_status(self) -> Dict[str, Any]:
        return {
            "name": self.get_name(),
            "available": self.is_available(),
            "hook_mechanism": ".agents/hooks.json",
            "supported_events": ["PreInvocation", "PostToolUse", "Stop"],
        }

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def assemble_context(
        self,
        task_description: str,
        project_id: str,
        domain: str = "general",
        technologies: Optional[List[str]] = None,
    ) -> str:
        if not self.engine:
            return ""
        scored = self.engine.retrieve_relevant_lessons(
            task_description=task_description,
            project_id=project_id,
            domain=domain,
            technologies=technologies,
        )
        active_p = self.profile_repo.get_active() if self.profile_repo else None
        p_name = active_p.name if active_p else "Default"
        return self.assembler.assemble(scored, profile_name=p_name)

    def generate_hooks_config(self, python_executable: str = "python") -> Dict[str, Any]:
        """Generate hooks.json configuration matching Antigravity specifications."""
        return {
            "evodev-experience-layer": {
                "enabled": True,
                "PreInvocation": [
                    {
                        "type": "command",
                        "command": f"{python_executable} -m evodev.connectors.gemini_hook pre-invocation",
                        "timeout": 15,
                    }
                ],
                "PostToolUse": [
                    {
                        "matcher": "*",
                        "hooks": [
                            {
                                "type": "command",
                                "command": f"{python_executable} -m evodev.connectors.gemini_hook post-tool-use",
                                "timeout": 15,
                            }
                        ],
                    }
                ],
                "Stop": [
                    {
                        "type": "command",
                        "command": f"{python_executable} -m evodev.connectors.gemini_hook stop",
                        "timeout": 15,
                    }
                ],
            }
        }

    def generate_mcp_config(self, python_executable: str = "python") -> Dict[str, Any]:
        """Generate mcp_config.json configuration."""
        return {
            "mcpServers": {
                "evodev": {
                    "command": python_executable,
                    "args": ["-m", "evodev.connectors.opencode_mcp"],
                }
            }
        }

    def apply_to_workspace(
        self,
        workspace_dir: Path,
        python_executable: str = "python",
    ) -> Dict[str, Path]:
        """Install .agents/hooks.json and .agents/mcp_config.json into target workspace."""
        workspace_dir = Path(workspace_dir)
        agents_dir = workspace_dir / ".agents"
        agents_dir.mkdir(parents=True, exist_ok=True)

        hooks_file = agents_dir / "hooks.json"
        mcp_file = agents_dir / "mcp_config.json"

        hooks_cfg = self.generate_hooks_config(python_executable)
        mcp_cfg = self.generate_mcp_config(python_executable)

        with open(hooks_file, "w", encoding="utf-8") as f:
            json.dump(hooks_cfg, f, indent=2)

        with open(mcp_file, "w", encoding="utf-8") as f:
            json.dump(mcp_cfg, f, indent=2)

        return {"hooks": hooks_file, "mcp": mcp_file}
