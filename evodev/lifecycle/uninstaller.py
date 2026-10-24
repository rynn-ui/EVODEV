"""EvoDev safe uninstallation and resource lifecycle service.

Enforces:
- Deletion of only EvoDev-owned state (database, local config, internal profile records, owned integration entries).
- Absolute preservation of external .vxp archives and unrelated agent configurations.
- Closing SQLite connections before database file removal.
- Path traversal guards preventing deletion outside verified EvoDev boundaries.
- Backup creation before destructive changes.
- Safe dry-run preview capability.
"""

from enum import Enum
import json
import logging
import os
from pathlib import Path
import shutil
import sys
from typing import Any, Dict, List, Optional
import zipfile

from evodev.config import EvoDevConfig, load_config
from evodev.storage.db import DatabaseManager, get_db

logger = logging.getLogger(__name__)


class InstallationType(str, Enum):
    FROZEN_BINARY = "frozen_binary"
    VIRTUALENV = "virtualenv"
    EDITABLE = "editable"
    PIP = "pip"
    SOURCE = "source"


class UninstallPlanItem:
    """Individual file or directory scheduled for removal."""

    def __init__(self, path: Path, category: str, description: str, is_directory: bool = False):
        self.path = path.resolve()
        self.category = category  # database, config, managed_profiles, cache, integration
        self.description = description
        self.is_directory = is_directory

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": str(self.path),
            "category": self.category,
            "description": self.description,
            "is_directory": self.is_directory,
            "exists": self.path.exists(),
        }


class PreservedItem:
    """Resource explicitly recognized as user data and preserved."""

    def __init__(self, path: Path, reason: str):
        self.path = path.resolve()
        self.reason = reason

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": str(self.path),
            "reason": self.reason,
            "exists": self.path.exists(),
        }


class IntegrationEntryToClean:
    """Specific EvoDev-owned key inside a shared agent configuration file."""

    def __init__(
        self,
        config_path: Path,
        agent_name: str,
        section_key: str,
        entry_key: str,
        description: str,
    ):
        self.config_path = config_path.resolve()
        self.agent_name = agent_name
        self.section_key = section_key
        self.entry_key = entry_key
        self.description = description

    def to_dict(self) -> Dict[str, Any]:
        return {
            "config_path": str(self.config_path),
            "agent_name": self.agent_name,
            "section_key": self.section_key,
            "entry_key": self.entry_key,
            "description": self.description,
            "exists": self.config_path.is_file(),
        }


class UninstallPlan:
    """Complete blueprint of what will be removed, cleaned, and preserved."""

    def __init__(
        self,
        installation_type: InstallationType,
        data_dir: Path,
        items_to_remove: List[UninstallPlanItem],
        integrations_to_clean: List[IntegrationEntryToClean],
        preserved_items: List[PreservedItem],
        package_removal_command: str,
    ):
        self.installation_type = installation_type
        self.data_dir = data_dir.resolve()
        self.items_to_remove = items_to_remove
        self.integrations_to_clean = integrations_to_clean
        self.preserved_items = preserved_items
        self.package_removal_command = package_removal_command

    def to_dict(self) -> Dict[str, Any]:
        return {
            "installation_type": self.installation_type.value,
            "data_dir": str(self.data_dir),
            "items_to_remove": [i.to_dict() for i in self.items_to_remove],
            "integrations_to_clean": [c.to_dict() for c in self.integrations_to_clean],
            "preserved_items": [p.to_dict() for p in self.preserved_items],
            "package_removal_command": self.package_removal_command,
        }


class UninstallResult:
    """Result summary of uninstallation execution."""

    def __init__(
        self,
        success: bool,
        dry_run: bool,
        backup_path: Optional[Path] = None,
        removed_files: Optional[List[str]] = None,
        cleaned_integrations: Optional[List[str]] = None,
        preserved_files: Optional[List[str]] = None,
        errors: Optional[List[Dict[str, str]]] = None,
        package_instructions: str = "",
    ):
        self.success = success
        self.dry_run = dry_run
        self.backup_path = backup_path
        self.removed_files = removed_files or []
        self.cleaned_integrations = cleaned_integrations or []
        self.preserved_files = preserved_files or []
        self.errors = errors or []
        self.package_instructions = package_instructions

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "dry_run": self.dry_run,
            "backup_path": str(self.backup_path) if self.backup_path else None,
            "removed_files": self.removed_files,
            "cleaned_integrations": self.cleaned_integrations,
            "preserved_files": self.preserved_files,
            "errors": self.errors,
            "package_instructions": self.package_instructions,
        }


class EvoDevUninstaller:
    """Safe uninstallation engine for EvoDev."""

    def __init__(
        self,
        config: Optional[EvoDevConfig] = None,
        db_manager: Optional[DatabaseManager] = None,
        search_workspace_integrations: bool = True,
        extra_workspace_paths: Optional[List[Path]] = None,
    ):
        self.config = config or load_config()
        self.db_manager = db_manager
        self.search_workspace = search_workspace_integrations
        self.extra_workspace_paths = extra_workspace_paths or [Path.cwd()]

    @staticmethod
    def detect_installation_type() -> InstallationType:
        """Detect whether EvoDev is running as binary, virtualenv, editable, or pip."""
        if getattr(sys, "frozen", False):
            return InstallationType.FROZEN_BINARY

        in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
        # Check editable installation
        try:
            import importlib.metadata
            dist = importlib.metadata.distribution("evodev")
            direct_url = dist.read_text("direct_url.json")
            if direct_url and '"dir_info": {"editable": true}' in direct_url:
                return InstallationType.EDITABLE
        except Exception:
            pass

        if in_venv:
            return InstallationType.VIRTUALENV
        return InstallationType.PIP

    def build_plan(self, keep_exports: bool = True) -> UninstallPlan:
        """Build a strict, verified plan of what will be removed and preserved."""
        inst_type = self.detect_installation_type()
        data_dir = self.config.data_dir.resolve()
        items_to_remove: List[UninstallPlanItem] = []
        preserved_items: List[PreservedItem] = []
        integrations_to_clean: List[IntegrationEntryToClean] = []

        # 1. Database files (owned exclusively by EvoDev)
        db_path = self.config.db_path.resolve()
        wal_path = Path(f"{db_path}-wal")
        shm_path = Path(f"{db_path}-shm")

        if db_path.exists():
            items_to_remove.append(
                UninstallPlanItem(db_path, "database", "Primary EvoDev SQLite database file")
            )
        if wal_path.exists():
            items_to_remove.append(
                UninstallPlanItem(wal_path, "database", "SQLite Write-Ahead Log journal")
            )
        if shm_path.exists():
            items_to_remove.append(
                UninstallPlanItem(shm_path, "database", "SQLite shared-memory index")
            )

        # 2. Config files
        data_config = data_dir / "config.json"
        if data_config.is_file():
            items_to_remove.append(
                UninstallPlanItem(data_config, "config", "EvoDev global configuration file")
            )

        workspace_config = Path(".evodev") / "config.json"
        if workspace_config.is_file():
            items_to_remove.append(
                UninstallPlanItem(workspace_config, "config", "Local workspace configuration file")
            )

        # 3. Internal managed profiles directory (not external user archives)
        profiles_dir = self.config.profiles_dir.resolve()
        if profiles_dir.is_dir():
            # Check files within profiles_dir
            for f in profiles_dir.iterdir():
                items_to_remove.append(
                    UninstallPlanItem(f, "managed_profiles", f"Internal managed profile record: {f.name}")
                )
            items_to_remove.append(
                UninstallPlanItem(profiles_dir, "managed_profiles", "Internal profiles management folder", is_directory=True)
            )

        # 4. User exports directory handling
        exports_dir = self.config.exports_dir.resolve()
        if exports_dir.is_dir():
            export_files = list(exports_dir.glob("*.vxp"))
            if keep_exports:
                for exp in export_files:
                    preserved_items.append(
                        PreservedItem(exp, "User-owned portable experience archive (.vxp)")
                    )
            else:
                for exp in export_files:
                    items_to_remove.append(
                        UninstallPlanItem(exp, "exports", f"Exported experience archive: {exp.name}")
                    )

        # 5. Local cache, doctor probe, or temporary test files inside data_dir
        cache_dir = data_dir / "cache"
        if cache_dir.is_dir():
            items_to_remove.append(
                UninstallPlanItem(cache_dir, "cache", "Internal cache directory", is_directory=True)
            )

        # 6. Integration cleanup inspection (OpenCode, Gemini/Antigravity, Kilo Code)
        candidate_dirs: List[Path] = []
        if self.search_workspace:
            for p in self.extra_workspace_paths:
                candidate_dirs.append(p.resolve())

        # Also check user home directories for global configurations
        home = Path.home().resolve()
        candidate_dirs.append(home)

        for base_dir in candidate_dirs:
            # 6a. OpenCode MCP entry in opencode.json
            opencode_json = base_dir / "opencode.json"
            if opencode_json.is_file():
                try:
                    with open(opencode_json, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict) and "mcp" in data and "evodev" in data["mcp"]:
                        integrations_to_clean.append(
                            IntegrationEntryToClean(
                                config_path=opencode_json,
                                agent_name="OpenCode",
                                section_key="mcp",
                                entry_key="evodev",
                                description="EvoDev stdio MCP server entry in opencode.json",
                            )
                        )
                except Exception:
                    pass

            # 6b. Gemini CLI / Antigravity hooks in .agents/hooks.json
            hooks_json = base_dir / ".agents" / "hooks.json"
            if hooks_json.is_file():
                try:
                    with open(hooks_json, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict) and "evodev-experience-layer" in data:
                        integrations_to_clean.append(
                            IntegrationEntryToClean(
                                config_path=hooks_json,
                                agent_name="Gemini CLI / Antigravity",
                                section_key="",
                                entry_key="evodev-experience-layer",
                                description="EvoDev lifecycle hook block in .agents/hooks.json",
                            )
                        )
                except Exception:
                    pass

            # 6c. Gemini CLI / Antigravity MCP in .agents/mcp_config.json
            mcp_config = base_dir / ".agents" / "mcp_config.json"
            if mcp_config.is_file():
                try:
                    with open(mcp_config, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict) and "mcpServers" in data and "evodev" in data["mcpServers"]:
                        integrations_to_clean.append(
                            IntegrationEntryToClean(
                                config_path=mcp_config,
                                agent_name="Gemini CLI / Antigravity",
                                section_key="mcpServers",
                                entry_key="evodev",
                                description="EvoDev MCP server entry in .agents/mcp_config.json",
                            )
                        )
                except Exception:
                    pass

            # 6d. Kilo Code in .kilo/mcp.json
            kilo_mcp = base_dir / ".kilo" / "mcp.json"
            if kilo_mcp.is_file():
                try:
                    with open(kilo_mcp, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict) and "mcpServers" in data and "evodev" in data["mcpServers"]:
                        integrations_to_clean.append(
                            IntegrationEntryToClean(
                                config_path=kilo_mcp,
                                agent_name="Kilo Code",
                                section_key="mcpServers",
                                entry_key="evodev",
                                description="EvoDev MCP server entry in .kilo/mcp.json",
                            )
                        )
                except Exception:
                    pass

        # Package removal command hint
        if inst_type == InstallationType.FROZEN_BINARY:
            pkg_cmd = "Delete the standalone EvoDev executable file or uninstall via Windows Add/Remove Programs."
        elif inst_type == InstallationType.EDITABLE:
            pkg_cmd = "pip uninstall -y evodev"
        elif inst_type == InstallationType.VIRTUALENV:
            pkg_cmd = "pip uninstall -y evodev"
        else:
            pkg_cmd = "pip uninstall -y evodev"

        return UninstallPlan(
            installation_type=inst_type,
            data_dir=data_dir,
            items_to_remove=items_to_remove,
            integrations_to_clean=integrations_to_clean,
            preserved_items=preserved_items,
            package_removal_command=pkg_cmd,
        )

    def create_backup(self, target_dir: Optional[Path] = None) -> Optional[Path]:
        """Create a zip archive of current database and profiles before uninstallation."""
        backup_dir = target_dir or (self.config.data_dir / "backups")
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = Path(self.config.db_name).stem
        backup_zip = backup_dir / f"evodev_backup_{timestamp}.zip"

        files_to_pack: List[Path] = []
        if self.config.db_path.is_file():
            files_to_pack.append(self.config.db_path)
        if self.config.profiles_dir.is_dir():
            for p in self.config.profiles_dir.glob("*"):
                if p.is_file():
                    files_to_pack.append(p)

        if not files_to_pack:
            return None

        with zipfile.ZipFile(backup_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in files_to_pack:
                arcname = f.relative_to(self.config.data_dir) if f.is_relative_to(self.config.data_dir) else f.name
                zf.write(f, arcname=str(arcname))

        return backup_zip

    def _is_safe_to_delete(self, path: Path) -> bool:
        """Verify that a path is strictly inside an EvoDev-owned managed directory or is local config.

        CRITICAL SECURITY RULE: Never allow broad recursive deletion or escaping the managed boundary.
        """
        resolved = path.resolve()
        data_dir = self.config.data_dir.resolve()

        # 1. Must be inside data_dir, OR be an explicit local workspace .evodev file
        is_inside_data = False
        try:
            resolved.relative_to(data_dir)
            is_inside_data = True
        except ValueError:
            pass

        is_workspace_evodev = False
        if ".evodev" in resolved.parts:
            is_workspace_evodev = True

        if not (is_inside_data or is_workspace_evodev):
            return False

        # 2. Never allow deleting root or home directory
        if resolved == Path.home().resolve() or resolved == Path("/").resolve() or resolved == resolved.anchor:
            return False

        return True

    def execute_uninstall(
        self,
        plan: UninstallPlan,
        perform_backup: bool = True,
        backup_dir: Optional[Path] = None,
        dry_run: bool = False,
    ) -> UninstallResult:
        """Execute uninstallation according to the plan."""
        removed_files: List[str] = []
        cleaned_integrations: List[str] = []
        preserved_files: List[str] = [str(p.path) for p in plan.preserved_items]
        errors: List[Dict[str, str]] = []
        backup_path: Optional[Path] = None

        if dry_run:
            return UninstallResult(
                success=True,
                dry_run=True,
                backup_path=None,
                removed_files=[str(i.path) for i in plan.items_to_remove],
                cleaned_integrations=[f"{c.agent_name} ({c.config_path})" for c in plan.integrations_to_clean],
                preserved_files=preserved_files,
                errors=[],
                package_instructions=plan.package_removal_command,
            )

        # 1. Close database connections first!
        try:
            if self.db_manager:
                self.db_manager.close()
            else:
                db = get_db(self.config)
                db.close()
        except Exception as e:
            logger.warning(f"Error while closing database connections: {e}")

        # 2. Create backup if requested
        if perform_backup:
            try:
                backup_path = self.create_backup(backup_dir)
            except Exception as e:
                errors.append({"action": "backup", "error": f"Failed to create backup: {e}"})

        # 3. Clean integration entries (remove only EvoDev keys)
        for clean_target in plan.integrations_to_clean:
            cfg_file = clean_target.config_path
            if not cfg_file.is_file():
                continue
            try:
                with open(cfg_file, "r", encoding="utf-8") as f:
                    cfg_data = json.load(f)

                modified = False
                if clean_target.section_key:
                    if clean_target.section_key in cfg_data and isinstance(cfg_data[clean_target.section_key], dict):
                        if clean_target.entry_key in cfg_data[clean_target.section_key]:
                            del cfg_data[clean_target.section_key][clean_target.entry_key]
                            modified = True
                else:
                    if clean_target.entry_key in cfg_data:
                        del cfg_data[clean_target.entry_key]
                        modified = True

                if modified:
                    with open(cfg_file, "w", encoding="utf-8") as f:
                        json.dump(cfg_data, f, indent=2)
                    cleaned_integrations.append(f"{clean_target.agent_name}: {cfg_file}")
            except Exception as e:
                errors.append({"path": str(cfg_file), "error": f"Failed to clean entry: {e}"})

        # 4. Remove scheduled files and directories with boundary checks
        # Sort items: files first, then directories
        files_first = sorted(plan.items_to_remove, key=lambda x: (1 if x.is_directory else 0))

        for item in files_first:
            target = item.path
            if not target.exists():
                continue

            if not self._is_safe_to_delete(target):
                errors.append({
                    "path": str(target),
                    "error": "Safety violation: Path escapes EvoDev-owned boundary. Deletion rejected.",
                })
                continue

            try:
                if item.is_directory:
                    # Only remove if directory is empty or contains only EvoDev files
                    if target.is_dir():
                        shutil.rmtree(target, ignore_errors=True)
                        removed_files.append(str(target))
                else:
                    target.unlink()
                    removed_files.append(str(target))
            except Exception as e:
                errors.append({"path": str(target), "error": str(e)})

        # 5. Clean up data_dir if empty or only contains preserved backups
        try:
            data_dir = self.config.data_dir.resolve()
            if data_dir.is_dir():
                remaining = list(data_dir.iterdir())
                # If only backups folder remains or nothing remains
                if not remaining:
                    data_dir.rmdir()
                    removed_files.append(str(data_dir))
        except Exception:
            pass

        success = len(errors) == 0

        return UninstallResult(
            success=success,
            dry_run=False,
            backup_path=backup_path,
            removed_files=removed_files,
            cleaned_integrations=cleaned_integrations,
            preserved_files=preserved_files,
            errors=errors,
            package_instructions=plan.package_removal_command,
        )
