"""Model Context Protocol (MCP) server for OpenCode integration over stdio."""

import json
import sys
from typing import Any, Dict, Optional

from evodev.config import load_config
from evodev.connectors.contract import ContextRequest, OutcomeReport
from evodev.connectors.opencode import OpenCodeConnector
from evodev.models.experience import StrategyOutcome
from evodev.retrieval.context_assembler import ContextAssembler
from evodev.retrieval.engine import RetrievalEngine
from evodev.storage.db import get_db
from evodev.storage.migrations import MigrationManager
from evodev.storage.repositories import (
    ExperienceRepository,
    LessonRepository,
    ProfileRepository,
    StrategyRepository,
)


class OpenCodeMCPServer:
    """Implements standard MCP JSON-RPC 2.0 protocol over stdio for OpenCode."""

    def __init__(self):
        self.config = load_config()
        self.db = get_db(self.config)
        MigrationManager(self.db).run_migrations()

        self.p_repo = ProfileRepository(self.db)
        self.l_repo = LessonRepository(self.db)
        self.s_repo = StrategyRepository(self.db)
        self.e_repo = ExperienceRepository(self.db)

        # Ensure active default profile exists
        if not self.p_repo.get_active():
            existing = self.p_repo.get_by_name("Default")
            if not existing:
                from evodev.models.profile import ProfileManifest
                self.p_repo.create(ProfileManifest(name="Default"), is_active=True)
            else:
                self.p_repo.activate(existing.profile_id)

        self.engine = RetrievalEngine(self.l_repo, self.p_repo)
        self.assembler = ContextAssembler()
        self.connector = OpenCodeConnector(
            lesson_repo=self.l_repo,
            profile_repo=self.p_repo,
            strategy_repo=self.s_repo,
        )

    def handle_request(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process incoming JSON-RPC request."""
        req_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {})

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "evodev", "version": "2.0.0"},
                },
            }

        elif method == "notifications/initialized":
            return None

        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": [
                        {
                            "name": "evodev_get_lessons",
                            "description": "Query EvoDev for verified lessons, recommended strategies, and anti-patterns relevant to a task.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "task_description": {
                                        "type": "string",
                                        "description": "Description of current task or error",
                                    },
                                    "domain": {
                                        "type": "string",
                                        "description": "Domain (mobile, backend, web, ml, general)",
                                    },
                                    "technologies": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "Applicable languages and frameworks",
                                    },
                                    "project_id": {
                                        "type": "string",
                                        "description": "Current repository or project identifier",
                                    },
                                },
                                "required": ["task_description"],
                            },
                        },
                        {
                            "name": "evodev_record_outcome",
                            "description": "Record the outcome of applying a strategy to update Bayesian statistics.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "strategy_name": {
                                        "type": "string",
                                        "description": "Name of attempted strategy",
                                    },
                                    "outcome": {
                                        "type": "string",
                                        "enum": ["success", "failure", "regression"],
                                    },
                                    "domain": {"type": "string"},
                                },
                                "required": ["strategy_name", "outcome"],
                            },
                        },
                        {
                            "name": "evodev_report_verification",
                            "description": "Report explicit test or build verification results.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "verification_type": {
                                        "type": "string",
                                        "description": "test, build, or lint",
                                    },
                                    "passed": {"type": "boolean"},
                                    "details": {"type": "string"},
                                },
                                "required": ["passed"],
                            },
                        },
                    ]
                },
            }

        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})

            if tool_name == "evodev_get_lessons":
                task_desc = arguments.get("task_description", "")
                domain = arguments.get("domain", "general")
                techs = arguments.get("technologies", [])
                proj_id = arguments.get("project_id", "current-project")

                active_profile = self.p_repo.get_active()
                profile_name = active_profile.name if active_profile else "Default"

                ctx_req = ContextRequest(
                    task_description=task_desc,
                    project_id=proj_id,
                    domain=domain,
                    technologies=techs,
                )
                ctx_resp = self.connector.get_context(ctx_req)

                text = ctx_resp.advisory_markdown
                if not text:
                    text = f"No prior verified lessons found for '{task_desc[:60]}' in profile '{profile_name}'."

                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"content": [{"type": "text", "text": text}]},
                }

            elif tool_name == "evodev_record_outcome":
                strat_name = arguments.get("strategy_name", "generic_strategy")
                outcome_str = arguments.get("outcome", "success")
                domain = arguments.get("domain", "general")

                report = OutcomeReport(
                    strategy_name=strat_name,
                    outcome=outcome_str,
                    domain=domain,
                )
                resp = self.connector.report_outcome(report)

                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Recorded strategy outcome for '{strat_name}'. New Bayesian score: {resp.bayesian_score:.2f} (Attempts: {resp.attempts_count}, Successes: {resp.success_count}).",
                            }
                        ]
                    },
                }

            elif tool_name == "evodev_report_verification":
                passed = arguments.get("passed", True)
                v_type = arguments.get("verification_type", "test")
                details = arguments.get("details", "")

                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Verification ({v_type}) recorded. Passed: {passed}. {details}",
                            }
                        ]
                    },
                }

        # Unknown method or error
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method '{method}' not implemented."},
        }

    def run_stdio(self) -> None:
        """Run the stdio JSON-RPC loop until EOF."""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
                response = self.handle_request(request)
                if response:
                    sys.stdout.write(json.dumps(response) + "\n")
                    sys.stdout.flush()
            except Exception as e:
                err_resp = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": f"Parse error: {e}"},
                }
                sys.stdout.write(json.dumps(err_resp) + "\n")
                sys.stdout.flush()


def main():
    server = OpenCodeMCPServer()
    server.run_stdio()


if __name__ == "__main__":
    main()
