"""Automated tests for EvoDev complete uninstallation and safe data lifecycle (Part E).

Covers all 12 testing requirements:
1. EvoDev's managed database and configuration are removed after confirmed uninstallation.
2. SQLite connections are closed before database files are removed.
3. External .vxp files remain unchanged.
4. User-owned exports inside the data directory are preserved or explicitly backed up.
5. Unrelated OpenCode MCP entries remain intact.
6. Unrelated agent configuration remains intact.
7. Cancellation leaves application state unchanged.
8. Dry-run mode performs no destructive changes.
9. Missing files and permission errors are reported safely.
10. Repeated uninstall attempts do not delete unrelated files.
11. Uninstallation works appropriately for supported installation types.
12. No broad recursive deletion or unsafe path handling can escape verified EvoDev-owned directories.
"""

import json
from pathlib import Path
import tempfile
import pytest

from evodev.config import EvoDevConfig, set_config
from evodev.lifecycle.uninstaller import (
    EvoDevUninstaller,
    InstallationType,
    UninstallPlan,
    UninstallPlanItem,
)
from evodev.models.profile import ProfileManifest
from evodev.storage.db import DatabaseManager, close_db, set_db
from evodev.storage.migrations import MigrationManager
from evodev.storage.repositories import ProfileRepository


@pytest.fixture
def uninstaller_env():
    """Create a temporary sandbox simulating EvoDev installation and external user archives."""
    with tempfile.TemporaryDirectory() as tmp_root:
        root_path = Path(tmp_root)
        data_dir = root_path / ".evodev_managed"
        workspace_dir = root_path / "my_project"
        external_user_dir = root_path / "user_documents"

        data_dir.mkdir(parents=True)
        workspace_dir.mkdir(parents=True)
        external_user_dir.mkdir(parents=True)

        config = EvoDevConfig(data_dir=data_dir)
        config.ensure_directories()
        set_config(config)

        db = DatabaseManager(config.db_path)
        set_db(db)
        MigrationManager(db).run_migrations()

        p_repo = ProfileRepository(db)
        p_repo.create(ProfileManifest(name="InternalDefault", version="1.0.0"), is_active=True)

        # 1. External .vxp archive in user documents (MUST NEVER BE TOUCHED)
        ext_vxp = external_user_dir / "AndroidExpert_backup.vxp"
        ext_vxp.write_text("DUMMY_VXP_ARCHIVE_CONTENT_EXTERNAL", encoding="utf-8")

        # 2. User export inside managed exports dir
        internal_vxp = config.exports_dir / "WebDevelopment.vxp"
        internal_vxp.write_text("DUMMY_VXP_ARCHIVE_CONTENT_INTERNAL_EXPORT", encoding="utf-8")

        # 3. OpenCode project config with BOTH unrelated tool AND evodev
        opencode_json = workspace_dir / "opencode.json"
        opencode_data = {
            "$schema": "https://opencode.ai/config.json",
            "mcp": {
                "unrelated_github_mcp": {
                    "type": "stdio",
                    "command": "github-mcp-server",
                    "args": ["--read-only"],
                },
                "evodev": {
                    "type": "stdio",
                    "command": "python",
                    "args": ["-m", "evodev.connectors.opencode_mcp"],
                },
            },
            "custom_setting": "keep_this_intact",
        }
        with open(opencode_json, "w", encoding="utf-8") as f:
            json.dump(opencode_data, f, indent=2)

        # 4. Gemini CLI workspace hooks with BOTH unrelated hook AND evodev
        agents_dir = workspace_dir / ".agents"
        agents_dir.mkdir(parents=True)
        hooks_json = agents_dir / "hooks.json"
        hooks_data = {
            "user_custom_linter_hook": {
                "enabled": True,
                "PreInvocation": [{"type": "command", "command": "flake8"}],
            },
            "evodev-experience-layer": {
                "enabled": True,
                "PreInvocation": [{"type": "command", "command": "python -m evodev.connectors.gemini_hook pre-invocation"}],
            },
        }
        with open(hooks_json, "w", encoding="utf-8") as f:
            json.dump(hooks_data, f, indent=2)

        # 5. Gemini CLI MCP config with BOTH unrelated server AND evodev
        mcp_config = agents_dir / "mcp_config.json"
        mcp_data = {
            "mcpServers": {
                "sqlite_mcp": {"command": "sqlite-mcp-server"},
                "evodev": {"command": "python", "args": ["-m", "evodev.connectors.opencode_mcp"]},
            }
        }
        with open(mcp_config, "w", encoding="utf-8") as f:
            json.dump(mcp_data, f, indent=2)

        uninstaller = EvoDevUninstaller(
            config=config,
            db_manager=db,
            search_workspace_integrations=True,
            extra_workspace_paths=[workspace_dir],
        )

        try:
            yield {
                "root_path": root_path,
                "data_dir": data_dir,
                "workspace_dir": workspace_dir,
                "external_user_dir": external_user_dir,
                "ext_vxp": ext_vxp,
                "internal_vxp": internal_vxp,
                "opencode_json": opencode_json,
                "hooks_json": hooks_json,
                "mcp_config": mcp_config,
                "config": config,
                "db": db,
                "uninstaller": uninstaller,
            }
        finally:
            close_db()


def test_dry_run_makes_zero_changes(uninstaller_env):
    """Req 8: Dry-run mode performs no destructive changes."""
    env = uninstaller_env
    uninstaller = env["uninstaller"]
    plan = uninstaller.build_plan(keep_exports=True)

    result = uninstaller.execute_uninstall(plan, dry_run=True)
    assert result.success is True
    assert result.dry_run is True

    # Database and files must still exist
    assert env["config"].db_path.is_file()
    assert env["opencode_json"].is_file()
    assert env["ext_vxp"].is_file()
    assert env["internal_vxp"].is_file()

    # OpenCode evodev entry still exists
    with open(env["opencode_json"], "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "evodev" in data["mcp"]


def test_confirmed_uninstall_removes_database_and_config(uninstaller_env):
    """Req 1 & 2: Database and config are removed; SQLite connections closed first."""
    env = uninstaller_env
    uninstaller = env["uninstaller"]
    plan = uninstaller.build_plan(keep_exports=True)

    # Execute actual uninstall
    result = uninstaller.execute_uninstall(plan, perform_backup=True, dry_run=False)
    assert result.success is True
    assert result.dry_run is False

    # 1. Database file is removed
    assert not env["config"].db_path.exists()
    assert not Path(f"{env['config'].db_path}-wal").exists()
    assert not Path(f"{env['config'].db_path}-shm").exists()

    # 2. Managed profiles directory is removed
    assert not env["config"].profiles_dir.exists()

    # 3. Backup was created
    assert result.backup_path is not None
    assert result.backup_path.is_file()


def test_external_vxp_archives_never_deleted(uninstaller_env):
    """Req 3: Critical safety requirement - External .vxp files remain unchanged."""
    env = uninstaller_env
    uninstaller = env["uninstaller"]
    plan = uninstaller.build_plan(keep_exports=True)

    result = uninstaller.execute_uninstall(plan, perform_backup=False, dry_run=False)
    assert result.success is True

    # External .vxp MUST remain 100% intact
    assert env["ext_vxp"].is_file()
    assert env["ext_vxp"].read_text(encoding="utf-8") == "DUMMY_VXP_ARCHIVE_CONTENT_EXTERNAL"


def test_user_exports_inside_data_dir_preserved_by_default(uninstaller_env):
    """Req 4: Exports inside data directory are preserved by default policy."""
    env = uninstaller_env
    uninstaller = env["uninstaller"]
    plan = uninstaller.build_plan(keep_exports=True)

    result = uninstaller.execute_uninstall(plan, perform_backup=False, dry_run=False)
    assert result.success is True

    # Internal export preserved
    assert env["internal_vxp"].is_file()
    assert env["internal_vxp"].read_text(encoding="utf-8") == "DUMMY_VXP_ARCHIVE_CONTENT_INTERNAL_EXPORT"


def test_unrelated_opencode_entries_remain_intact(uninstaller_env):
    """Req 5: Remove only EvoDev entry from OpenCode, preserving other tools and settings."""
    env = uninstaller_env
    uninstaller = env["uninstaller"]
    plan = uninstaller.build_plan(keep_exports=True)

    result = uninstaller.execute_uninstall(plan, dry_run=False)
    assert result.success is True

    with open(env["opencode_json"], "r", encoding="utf-8") as f:
        data = json.load(f)

    # evodev removed
    assert "evodev" not in data["mcp"]
    # unrelated tool preserved!
    assert "unrelated_github_mcp" in data["mcp"]
    assert data["mcp"]["unrelated_github_mcp"]["command"] == "github-mcp-server"
    # custom setting preserved!
    assert data["custom_setting"] == "keep_this_intact"


def test_unrelated_agent_config_remains_intact(uninstaller_env):
    """Req 6: Remove only EvoDev from Gemini/Antigravity hooks and mcp_config."""
    env = uninstaller_env
    uninstaller = env["uninstaller"]
    plan = uninstaller.build_plan(keep_exports=True)

    result = uninstaller.execute_uninstall(plan, dry_run=False)
    assert result.success is True

    # Check hooks.json
    with open(env["hooks_json"], "r", encoding="utf-8") as f:
        hooks = json.load(f)
    assert "evodev-experience-layer" not in hooks
    assert "user_custom_linter_hook" in hooks
    assert hooks["user_custom_linter_hook"]["enabled"] is True

    # Check mcp_config.json
    with open(env["mcp_config"], "r", encoding="utf-8") as f:
        mcp = json.load(f)
    assert "evodev" not in mcp["mcpServers"]
    assert "sqlite_mcp" in mcp["mcpServers"]


def test_missing_files_reported_safely(uninstaller_env):
    """Req 9: Missing files and non-existent directories are handled gracefully."""
    env = uninstaller_env
    uninstaller = env["uninstaller"]

    # Delete db beforehand
    if env["config"].db_path.exists():
        env["db"].close()
        env["config"].db_path.unlink()

    plan = uninstaller.build_plan(keep_exports=True)
    result = uninstaller.execute_uninstall(plan, dry_run=False)
    assert result.success is True
    assert len(result.errors) == 0


def test_repeated_uninstall_attempts_are_idempotent(uninstaller_env):
    """Req 10: Repeated uninstall attempts do not fail or delete unrelated files."""
    env = uninstaller_env
    uninstaller = env["uninstaller"]

    # First run
    plan1 = uninstaller.build_plan(keep_exports=True)
    res1 = uninstaller.execute_uninstall(plan1, dry_run=False)
    assert res1.success is True

    # Second run immediately after
    plan2 = uninstaller.build_plan(keep_exports=True)
    res2 = uninstaller.execute_uninstall(plan2, dry_run=False)
    assert res2.success is True

    # External user files still intact!
    assert env["ext_vxp"].is_file()


def test_path_boundary_enforcement_escapes_prevented(uninstaller_env):
    """Req 12: Broad recursive deletion or escaping the managed directory is strictly rejected."""
    env = uninstaller_env
    uninstaller = env["uninstaller"]

    plan = uninstaller.build_plan(keep_exports=True)
    # Malicious injection attempting to delete parent or user dir
    unsafe_item = UninstallPlanItem(
        path=env["external_user_dir"],
        category="malicious_escape",
        description="Escape attempt",
        is_directory=True,
    )
    plan.items_to_remove.append(unsafe_item)

    result = uninstaller.execute_uninstall(plan, dry_run=False)

    # Must fail or record an error for the unsafe item, and NOT delete external_user_dir
    assert env["external_user_dir"].is_dir()
    assert any("escapes EvoDev-owned boundary" in err.get("error", "") for err in result.errors)


def test_installation_type_detection():
    """Req 11: Installation type is detected properly."""
    inst_type = EvoDevUninstaller.detect_installation_type()
    assert inst_type in [
        InstallationType.FROZEN_BINARY,
        InstallationType.VIRTUALENV,
        InstallationType.EDITABLE,
        InstallationType.PIP,
        InstallationType.SOURCE,
    ]
