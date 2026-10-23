"""EvoDev command line interface."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from evodev.collector.collector_service import CollectorService
from evodev.config import EvoDevConfig, load_config, save_config
from evodev.connectors.gemini import GeminiCLIConnector
from evodev.connectors.opencode import OpenCodeConnector
from evodev.evaluation.benchmark import BenchmarkSuiteRunner
from evodev.models.profile import ProfileManifest, ProfilePackage
from evodev.profiles.inspector import ProfileInspector
from evodev.profiles.manager import ProfileManager
from evodev.retrieval.engine import RetrievalEngine
from evodev.security.redactor import SecretRedactor
from evodev.storage.db import get_db
from evodev.storage.migrations import MigrationManager
from evodev.storage.repositories import (
    BenchmarkRepository,
    EventRepository,
    ExperienceRepository,
    LessonRepository,
    ProfileRepository,
    StrategyRepository,
)

app = typer.Typer(name="evodev", help="EvoDev: Self-Improving Developer Experience Layer")
profiles_app = typer.Typer(help="Manage portable experience profiles (.vxp)")
experience_app = typer.Typer(help="Inspect and manage stored experiences")
benchmark_app = typer.Typer(help="Benchmark and evaluate learning engine performance")
connectors_app = typer.Typer(help="Manage AI coding agent connectors")
retention_app = typer.Typer(help="Audit storage usage and clean aged data")

app.add_typer(profiles_app, name="profiles")
app.add_typer(experience_app, name="experience")
app.add_typer(benchmark_app, name="benchmark")
app.add_typer(connectors_app, name="connectors")
app.add_typer(retention_app, name="retention")

console = Console()


def _get_services():
    config = load_config()
    db = get_db(config)
    migrator = MigrationManager(db)
    migrator.run_migrations()

    p_repo = ProfileRepository(db)
    l_repo = LessonRepository(db)
    s_repo = StrategyRepository(db)
    e_repo = ExperienceRepository(db)
    ev_repo = EventRepository(db)
    b_repo = BenchmarkRepository(db)

    mgr = ProfileManager(p_repo, l_repo, s_repo, e_repo, b_repo, config)
    collector = CollectorService(ev_repo, e_repo, p_repo)
    engine = RetrievalEngine(l_repo, p_repo)

    return config, db, p_repo, l_repo, s_repo, e_repo, ev_repo, b_repo, mgr, collector, engine


def _get_inspector():
    config, db, p_repo, l_repo, s_repo, e_repo, ev_repo, b_repo, _, _, _ = _get_services()
    return ProfileInspector(p_repo, l_repo, s_repo, e_repo, b_repo, ev_repo, config)




# ==========================================
# Root Commands
# ==========================================

@app.command()
def init(
    name: str = typer.Option("Default", help="Name of initial experience profile"),
    data_dir: Optional[str] = typer.Option(None, help="Custom data directory path"),
):
    """Initialize EvoDev repository configuration and database."""
    config = load_config()
    if data_dir:
        config.data_dir = Path(data_dir)
    config.ensure_directories()
    save_config(config)

    _, _, p_repo, _, _, _, _, _, mgr, _, _ = _get_services()
    if not p_repo.get_by_name(name):
        mgr.create_profile(name=name, description="Default experience profile", activate=True)
        console.print(f"[bold green]Initialized EvoDev![/bold green] Active profile: [cyan]{name}[/cyan]")
    else:
        mgr.activate_profile(name)
        console.print(f"[green]EvoDev already initialized.[/green] Active profile: [cyan]{name}[/cyan]")


@app.command()
def status():
    """Display EvoDev active profile, database size, and registered knowledge."""
    config, _, p_repo, l_repo, s_repo, e_repo, _, _, _, _, _ = _get_services()

    active = p_repo.get_active()
    active_name = active.name if active else "[dim]None (deactivated)[/dim]"
    active_id = active.profile_id if active else "N/A"

    db_size_kb = 0
    if config.db_path.is_file():
        db_size_kb = round(config.db_path.stat().st_size / 1024, 1)

    table = Table(title=f"{config.product_name} Runtime Status")
    table.add_column("Property", style="cyan", no_wrap=True)
    table.add_column("Value", style="green")

    table.add_row("Product Name", config.product_name)
    table.add_row("Data Directory", str(config.data_dir))
    table.add_row("Database Path", str(config.db_path))
    table.add_row("Database File Size", f"{db_size_kb} KB")
    table.add_row("Active Profile", active_name)

    if active:
        lesson_count = l_repo.count_by_profile(active_id)
        strategy_count = len(s_repo.list_by_profile(active_id))
        experience_count = e_repo.count_by_profile(active_id)
        table.add_row("Active Lessons", str(lesson_count))
        table.add_row("Tracked Strategies", str(strategy_count))
        table.add_row("Stored Experiences", str(experience_count))

    console.print(table)


@app.command()
def doctor():
    """Run diagnostics on local storage, integrations, permissions, and security."""
    config, _, _, _, _, _, _, _, _, _, _ = _get_services()

    table = Table(title="EvoDev Diagnostic Doctor")
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Details")

    # 1. Database & Migrations
    try:
        db = get_db(config)
        migrator = MigrationManager(db)
        with db.session() as conn:
            versions = migrator.get_applied_versions(conn)
        table.add_row("SQLite Database", "[green]OK[/green]", f"WAL mode active. Applied migrations: {versions}")
    except Exception as e:
        table.add_row("SQLite Database", "[red]FAIL[/red]", str(e))

    # 2. Directory Write Permissions
    try:
        config.ensure_directories()
        test_file = config.data_dir / ".doctor_probe"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink()
        table.add_row("Storage Permissions", "[green]OK[/green]", f"Writable: {config.data_dir}")
    except Exception as e:
        table.add_row("Storage Permissions", "[red]FAIL[/red]", str(e))

    # 3. Secret Redaction Engine
    try:
        redactor = SecretRedactor()
        sample = "sk-proj-1234567890abcdef1234567890abcdef"
        masked = redactor.redact_text(sample)
        if "[REDACTED_OPENAI_KEY]" in masked:
            table.add_row("Secret Redactor", "[green]OK[/green]", "Regex and entropy patterns operational")
        else:
            table.add_row("Secret Redactor", "[yellow]WARN[/yellow]", "Redactor did not mask test token")
    except Exception as e:
        table.add_row("Secret Redactor", "[red]FAIL[/red]", str(e))

    # 4. OpenCode Installation
    opencode_conn = OpenCodeConnector()
    if opencode_conn.is_available():
        ver = opencode_conn.get_version()
        table.add_row("OpenCode Agent", "[green]FOUND[/green]", f"Installed version: {ver}")
    else:
        table.add_row("OpenCode Agent", "[yellow]NOT INSTALLED[/yellow]", "Install globally via 'npm i -g opencode-ai'")

    # 5. Gemini CLI / Antigravity Environment
    gemini_conn = GeminiCLIConnector()
    if gemini_conn.is_available():
        table.add_row("Gemini CLI / Antigravity", "[green]FOUND[/green]", f"Config detected in {Path.home() / '.gemini'}")
    else:
        table.add_row("Gemini CLI / Antigravity", "[dim]OPTIONAL[/dim]", "Antigravity config directory not present")

    console.print(table)


# ==========================================
# Profile Commands
# ==========================================

@profiles_app.command("list")
def profiles_list():
    """List all stored experience profiles."""
    _, _, p_repo, l_repo, s_repo, _, _, _, _, _, _ = _get_services()
    profiles = p_repo.list_all()

    if not profiles:
        console.print("[yellow]No profiles found. Run 'evodev profiles create <name>' to create one.[/yellow]")
        return

    active = p_repo.get_active()
    active_id = active.profile_id if active else ""

    table = Table(title="Experience Profiles (.vxp)")
    table.add_column("Name", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Version")
    table.add_column("Lessons", justify="right")
    table.add_column("Strategies", justify="right")
    table.add_column("Domains")

    for p in profiles:
        is_active = p.profile_id == active_id
        status_str = "[bold green]ACTIVE[/bold green]" if is_active else "[dim]INACTIVE[/dim]"
        lessons_cnt = l_repo.count_by_profile(p.profile_id)
        strat_cnt = len(s_repo.list_by_profile(p.profile_id))
        dom_str = ", ".join(p.domains) if p.domains else "general"

        table.add_row(p.name, status_str, p.version, str(lessons_cnt), str(strat_cnt), dom_str)

    console.print(table)


@profiles_app.command("create")
def profiles_create(
    name: str = typer.Argument(..., help="Name of profile"),
    description: str = typer.Option("", help="Short description"),
    domain: str = typer.Option("general", help="Primary domain (e.g. mobile, web, ml)"),
    activate: bool = typer.Option(False, help="Activate immediately"),
):
    """Create a new named experience profile."""
    _, _, _, _, _, _, _, _, mgr, _, _ = _get_services()
    p = mgr.create_profile(name=name, description=description, domains=[domain], activate=activate)
    console.print(f"[bold green]Created profile:[/bold green] [cyan]{p.name}[/cyan] (ID: {p.profile_id})")


@profiles_app.command("rename")
def profiles_rename(
    old_name: str = typer.Argument(..., help="Current profile name or ID"),
    new_name: str = typer.Argument(..., help="New profile name"),
):
    """Rename an experience profile."""
    _, _, _, _, _, _, _, _, mgr, _, _ = _get_services()
    if mgr.rename_profile(old_name, new_name):
        console.print(f"[bold green]Renamed profile[/bold green] [cyan]{old_name}[/cyan] -> [green]{new_name}[/green]")
    else:
        console.print(f"[red]Profile '{old_name}' not found.[/red]")
        raise typer.Exit(1)


@profiles_app.command("duplicate")
def profiles_duplicate(
    source_name: str = typer.Argument(..., help="Existing profile name or ID"),
    new_name: str = typer.Argument(..., help="Target profile name"),
):
    """Duplicate an experience profile."""
    _, _, _, _, _, _, _, _, mgr, _, _ = _get_services()
    try:
        new_p = mgr.duplicate_profile(source_name, new_name)
        console.print(f"[bold green]Duplicated profile[/bold green] [cyan]{source_name}[/cyan] -> [green]{new_p.name}[/green]")
    except Exception as e:
        console.print(f"[red]Error duplicating profile: {e}[/red]")
        raise typer.Exit(1)


@profiles_app.command("activate")
def profiles_activate(
    name: str = typer.Argument(..., help="Profile name or ID to activate"),
):
    """Activate an experience profile for current development tasks."""
    _, _, _, _, _, _, _, _, mgr, _, _ = _get_services()
    if mgr.activate_profile(name):
        console.print(f"[bold green]Activated profile:[/bold green] [cyan]{name}[/cyan]")
    else:
        console.print(f"[red]Profile '{name}' not found.[/red]")
        raise typer.Exit(1)


@profiles_app.command("deactivate")
def profiles_deactivate():
    """Deactivate all experience profiles."""
    _, _, _, _, _, _, _, _, mgr, _, _ = _get_services()
    mgr.deactivate_profile()
    console.print("[yellow]Deactivated all experience profiles.[/yellow]")


@profiles_app.command("export")
def profiles_export(
    name: str = typer.Argument(..., help="Profile name or ID to export"),
    path: Optional[str] = typer.Argument(None, help="Output .vxp file path"),
    password: Optional[str] = typer.Option(None, help="Optional AES-256-GCM encryption password"),
):
    """Export an experience profile to a portable .vxp archive file."""
    _, _, _, _, _, _, _, _, mgr, _, _ = _get_services()
    try:
        out_path = Path(path) if path else None
        target = mgr.export_profile(name, output_path=out_path, password=password)
        console.print(f"[bold green]Exported profile to:[/bold green] [cyan]{target}[/cyan]")
    except Exception as e:
        console.print(f"[red]Export failed: {e}[/red]")
        raise typer.Exit(1)


@profiles_app.command("import")
def profiles_import(
    path: str = typer.Argument(..., help="Path to .vxp archive file"),
    activate: bool = typer.Option(True, help="Activate immediately upon import"),
    password: Optional[str] = typer.Option(None, help="Password if archive is encrypted"),
    name: Optional[str] = typer.Option(None, help="Override profile name on import"),
):
    """Import an experience profile from a .vxp archive."""
    _, _, _, _, _, _, _, _, mgr, _, _ = _get_services()
    vxp_path = Path(path)
    if not vxp_path.is_file():
        console.print(f"[red]File not found: {vxp_path}[/red]")
        raise typer.Exit(1)
    try:
        manifest = mgr.import_profile(
            vxp_path=vxp_path,
            activate_on_import=activate,
            password=password,
            custom_name=name,
        )
        console.print(f"[bold green]Successfully imported profile:[/bold green] [cyan]{manifest.name}[/cyan] (Version {manifest.version})")
    except Exception as e:
        console.print(f"[red]Import failed: {e}[/red]")
        raise typer.Exit(1)


@profiles_app.command("history")
def profiles_history(
    name: str = typer.Argument(..., help="Profile name or ID"),
):
    """View version checkpoints for a profile."""
    _, _, _, _, _, _, _, _, mgr, _, _ = _get_services()
    versions = mgr.list_versions(name)
    if not versions:
        console.print(f"[yellow]No version checkpoints found for '{name}'.[/yellow]")
        return

    table = Table(title=f"Version History for {name}")
    table.add_column("Version", style="cyan")
    table.add_column("Created At")
    table.add_column("Message")

    for v in versions:
        table.add_row(v.version, v.created_at.strftime("%Y-%m-%d %H:%M:%S"), v.message)

    console.print(table)


@profiles_app.command("rollback")
def profiles_rollback(
    name: str = typer.Argument(..., help="Profile name or ID"),
    version: str = typer.Argument(..., help="Target version string to restore (e.g. 1.0.1)"),
):
    """Roll back profile state to an earlier version checkpoint."""
    _, _, _, _, _, _, _, _, mgr, _, _ = _get_services()
    try:
        restored = mgr.rollback_version(name, version)
        console.print(f"[bold green]Rolled back profile '{restored.name}' to version {version}[/bold green]")
    except Exception as e:
        console.print(f"[red]Rollback failed: {e}[/red]")
        raise typer.Exit(1)


@profiles_app.command("inspect")
def profiles_inspect(
    identifier: str = typer.Argument(..., help="Profile name, ID, or .vxp file path"),
    password: Optional[str] = typer.Option(None, help="Password if inspecting encrypted .vxp"),
):
    """Deep inspect experience profile, .vxp archive entries, and competence analytics."""
    inspector = _get_inspector()
    config, _, p_repo, _, _, _, _, _, mgr, _, _ = _get_services()

    # 1. Check if inspecting an external file path directly
    path_obj = Path(identifier)
    if path_obj.is_file():
        console.print(f"[bold cyan]Inspecting Archive File:[/bold cyan] {path_obj}")
        result = inspector.inspect_archive(path_obj, password=password)
    else:
        profile = p_repo.get_by_id(identifier) or p_repo.get_by_name(identifier)
        if not profile:
            console.print(f"[red]Profile '{identifier}' not found in database or filesystem.[/red]")
            raise typer.Exit(1)

        summary = inspector.get_profile_summary(profile.profile_id)
        table_sum = Table(title=f"Experience Profile: {summary.name} (v{summary.version})")
        table_sum.add_column("Property", style="cyan")
        table_sum.add_column("Value", style="green")

        table_sum.add_row("Profile ID", summary.profile_id)
        table_sum.add_row("Load State", summary.load_state)
        table_sum.add_row("Schema Version", f"v{summary.schema_version} ({'SUPPORTED' if summary.is_schema_supported else 'UNSUPPORTED'})")
        table_sum.add_row("Archive Size", f"{summary.file_size_bytes} bytes")
        table_sum.add_row("Uncompressed Payload", f"{summary.uncompressed_size_bytes} bytes")
        table_sum.add_row("Experiences Count", str(summary.experience_count))
        table_sum.add_row("Verified Lessons", f"[green]{summary.verified_lesson_count}[/green]")
        table_sum.add_row("Candidate Lessons", f"[yellow]{summary.candidate_lesson_count}[/yellow]")
        table_sum.add_row("Strategies Tracked", str(summary.strategy_count))
        table_sum.add_row("Domain Coverage", f"{summary.domain_coverage_pct}% ({', '.join(summary.domain_coverage)})")
        console.print(table_sum)

        # Inspect archive
        vxp_path = config.exports_dir / f"{profile.name}.vxp"
        if not vxp_path.is_file():
            vxp_path = config.profiles_dir / f"{profile.name}.vxp"
        if vxp_path.is_file():
            result = inspector.inspect_archive(vxp_path, password=password)
        else:
            package = ProfilePackage(
                manifest=profile,
                lessons=inspector.lesson_repo.list_by_profile(profile.profile_id, active_only=False),
                strategies=inspector.strategy_repo.list_by_profile(profile.profile_id),
                preferences={},
                benchmarks=inspector.benchmark_repo.get_metrics(profile.profile_id) if inspector.benchmark_repo else [],
            )
            temp_path = config.exports_dir / f"{profile.name}.vxp"
            mgr.archive_format.pack_to_vxp(package, temp_path)
            result = inspector.inspect_archive(temp_path, password=password)

    # Display Archive Entries
    if result.is_encrypted and not result.entries:
        console.print("[yellow]Archive is encrypted (AES-256-GCM). Pass --password to decrypt and view entries.[/yellow]")
        if result.encryption_details:
            console.print(f"Salt: {result.encryption_details.get('salt_hex')}")
            console.print(f"Nonce: {result.encryption_details.get('nonce_hex')}")
            console.print(f"Ciphertext: {result.encryption_details.get('ciphertext_bytes')} bytes")
        return

    table_ent = Table(title="Archive Entries (.vxp format)")
    table_ent.add_column("Entry", style="cyan")
    table_ent.add_column("Uncompressed", justify="right")
    table_ent.add_column("Compressed", justify="right")
    table_ent.add_column("Ratio", justify="right")
    table_ent.add_column("Records", justify="right")

    for e in result.entries:
        rec_str = str(e.record_count) if e.record_count is not None else "-"
        table_ent.add_row(e.name, f"{e.uncompressed_bytes} B", f"{e.compressed_bytes} B", f"{e.compression_ratio_pct:.1f}%", rec_str)

    console.print(table_ent)

    # Checksum status
    status_str = "[bold green]VALID SHA-256 DIGEST[/bold green]" if result.integrity_verified else "[bold red]INTEGRITY MISMATCH[/bold red]"
    console.print(f"Integrity Status: {status_str} (Expected: {result.integrity_checksum_expected})")



# ==========================================
# Experience Commands
# ==========================================

@experience_app.command("list")
def experience_list(
    limit: int = typer.Option(20, help="Maximum records to display"),
):
    """List recently recorded development task experiences."""
    _, _, p_repo, _, _, e_repo, _, _, _, _, _ = _get_services()
    active = p_repo.get_active()
    profile_id = active.profile_id if active else "default"

    records = e_repo.list_by_profile(profile_id, limit=limit)
    if not records:
        console.print("[yellow]No experiences recorded in current active profile yet.[/yellow]")
        return

    table = Table(title=f"Experiences in Active Profile ({active.name if active else 'Default'})")
    table.add_column("ID", style="dim", no_wrap=True)
    table.add_column("Project", style="cyan")
    table.add_column("Problem Summary")
    table.add_column("Outcome", style="bold")
    table.add_column("Verified")

    for r in records:
        out_style = "green" if r.outcome == "success" else "red"
        is_verified = "✓" if r.verification and r.verification.passed else "✗"
        prob_trunc = (r.initial_problem[:50] + "...") if len(r.initial_problem) > 50 else r.initial_problem
        table.add_row(r.id[:8], r.project_id, prob_trunc, f"[{out_style}]{r.outcome}[/{out_style}]", is_verified)

    console.print(table)


@experience_app.command("inspect")
def experience_inspect(
    exp_id: str = typer.Argument(..., help="Experience record ID or prefix"),
):
    """Display full details of a specific experience record."""
    _, _, _, _, _, e_repo, _, _, _, _, _ = _get_services()
    record = e_repo.get_by_id(exp_id)
    if not record:
        console.print(f"[red]Experience ID '{exp_id}' not found.[/red]")
        raise typer.Exit(1)

    console.print_json(record.model_dump_json())


@experience_app.command("delete")
def experience_delete(
    exp_id: str = typer.Argument(..., help="Experience record ID to delete"),
):
    """Delete a specific experience record."""
    _, _, _, _, _, e_repo, _, _, _, _, _ = _get_services()
    if e_repo.delete(exp_id):
        console.print(f"[green]Deleted experience {exp_id}[/green]")
    else:
        console.print(f"[red]Record {exp_id} not found.[/red]")
        raise typer.Exit(1)


# ==========================================
# Benchmark Commands
# ==========================================

@benchmark_app.command("run")
def benchmark_run(
    suite: str = typer.Option("standard_dev_challenges", help="Benchmark challenge suite name"),
    mode: str = typer.Option("evodev_experienced", help="Agent mode: base_agent or evodev_experienced"),
):
    """Run an empirical benchmark comparing base agent vs EvoDev experience performance."""
    _, _, p_repo, l_repo, _, _, _, b_repo, _, _, engine = _get_services()
    active = p_repo.get_active()
    profile_id = active.profile_id if active else "default"

    runner = BenchmarkSuiteRunner(engine, b_repo)
    console.print(f"[cyan]Running benchmark suite '{suite}' in mode '{mode}'...[/cyan]")
    metrics = runner.run_suite(suite_name=suite, profile_id=profile_id, agent_mode=mode)

    table = Table(title=f"Benchmark Results: {suite} ({mode})")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="bold green")

    table.add_row("Total Challenges", str(metrics.total_tasks))
    table.add_row("Passed Challenges", str(metrics.passed_tasks))
    table.add_row("Failed Challenges", str(metrics.failed_tasks))
    table.add_row("Regressed Challenges", str(metrics.regressed_tasks))
    table.add_row("Success Rate", f"{metrics.success_rate:.1%}")
    table.add_row("Regression Rate", f"{metrics.regression_rate:.1%}")
    table.add_row("Repeated Error Frequency", f"{metrics.repeated_error_frequency:.1%}")
    table.add_row("Average Duration", f"{metrics.avg_duration_seconds:.4f}s")

    console.print(table)


# ==========================================
# Retention Commands
# ==========================================

@retention_app.command("status")
def retention_status():
    """Inspect stored record counts and database footprint."""
    config, _, p_repo, l_repo, s_repo, e_repo, ev_repo, _, _, _, _ = _get_services()

    table = Table(title="Storage Retention & Footprint Status")
    table.add_column("Entity", style="cyan")
    table.add_column("Count / Size", style="green")

    active = p_repo.get_active()
    p_id = active.profile_id if active else "default"

    table.add_row("Database File", f"{round(config.db_path.stat().st_size / 1024, 1)} KB" if config.db_path.is_file() else "0 KB")
    table.add_row("Total Stored Events", str(ev_repo.count()))
    table.add_row("Total Experiences", str(e_repo.count_by_profile(p_id)))
    table.add_row("Active Lessons", str(l_repo.count_by_profile(p_id)))
    table.add_row("Configured Retention Window", f"{config.retention_days} days")

    console.print(table)


@retention_app.command("clean")
def retention_clean(
    days: Optional[int] = typer.Option(None, help="Retention window in days (defaults to config value)"),
):
    """Purge raw events and unpromoted experiences older than the retention threshold."""
    config, _, _, _, _, e_repo, ev_repo, _, _, _, _ = _get_services()
    window = days or config.retention_days

    ev_deleted = ev_repo.delete_older_than(window)
    exp_deleted = e_repo.delete_older_than(window)

    console.print(f"[green]Cleaned storage:[/green] Purged {ev_deleted} raw events and {exp_deleted} aged experiences older than {window} days.")


# ==========================================
# Connectors Commands
# ==========================================

@connectors_app.command("list")
def connectors_list():
    """List available AI coding agent connectors and status."""
    opencode = OpenCodeConnector()
    gemini = GeminiCLIConnector()

    table = Table(title="AI Coding Agent Connectors")
    table.add_column("Connector", style="cyan")
    table.add_column("Installed Status", style="bold")
    table.add_column("Integration Mechanism")

    op_status = "[green]AVAILABLE[/green]" if opencode.is_available() else "[yellow]NOT INSTALLED[/yellow]"
    table.add_row("OpenCode", op_status, "MCP stdio server (evodev_get_lessons, evodev_record_outcome)")

    gm_status = "[green]AVAILABLE[/green]" if gemini.is_available() else "[dim]OPTIONAL[/dim]"
    table.add_row("Gemini CLI / Antigravity", gm_status, ".agents/hooks.json (PreInvocation, PostToolUse, Stop)")

    table.add_row("Generic Adapter", "[green]READY[/green]", "REST / JSON-IPC for IDEs and scripts")

    console.print(table)


@connectors_app.command("install-opencode")
def connectors_install_opencode(
    project_dir: str = typer.Option(".", help="Target project root directory"),
):
    """Provision opencode.json MCP server configuration in target project."""
    connector = OpenCodeConnector()
    out = connector.apply_to_project(Path(project_dir))
    console.print(f"[bold green]Configured OpenCode MCP server at:[/bold green] [cyan]{out}[/cyan]")


@connectors_app.command("install-gemini")
def connectors_install_gemini(
    workspace_dir: str = typer.Option(".", help="Target workspace root directory"),
):
    """Provision .agents/hooks.json and .agents/mcp_config.json in target workspace."""
    connector = GeminiCLIConnector()
    res = connector.apply_to_workspace(Path(workspace_dir))
    console.print(f"[bold green]Configured Gemini CLI hooks at:[/bold green] [cyan]{res['hooks']}[/cyan]")


# ==========================================
# Server / Daemon Command
# ==========================================

@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Binding host (strictly local loopback by default)"),
    port: int = typer.Option(8765, help="HTTP port"),
):
    """Start local EvoDev REST API daemon and dashboard."""
    import uvicorn
    from evodev.api.server import create_api_app

    api_app = create_api_app()
    console.print(f"[bold green]Starting EvoDev service on http://{host}:{port}[/bold green]")
    uvicorn.run(api_app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    app()
