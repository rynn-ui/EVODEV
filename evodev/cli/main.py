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
from evodev.connectors.hermes import HermesConnector
from evodev.connectors.kilocode import KiloCodeConnector
from evodev.connectors.opencode import OpenCodeConnector
from evodev.evaluation.benchmark import BenchmarkSuiteRunner
from evodev.lifecycle.uninstaller import EvoDevUninstaller, InstallationType
from evodev.checkpoints.manager import CheckpointManager
from evodev.memory.manager import MemoryManager
from evodev.models.checkpoints import CheckpointType
from evodev.models.memory import MemoryCategory
from evodev.models.profile import ProfileManifest, ProfilePackage
from evodev.models.scheduler import JobType
from evodev.profiles.inspector import ProfileInspector
from evodev.profiles.manager import ProfileManager
from evodev.retrieval.engine import RetrievalEngine
from evodev.scheduler.engine import SchedulerEngine
from evodev.security.redactor import SecretRedactor
from evodev.skills.engine import SkillEngine
from evodev.storage.db import get_db
from evodev.storage.migrations import MigrationManager
from evodev.storage.repositories import (
    BenchmarkRepository,
    CheckpointRepository,
    EventRepository,
    ExperienceRepository,
    LessonRepository,
    MemoryRepository,
    ProfileRepository,
    ScheduleRepository,
    SkillRepository,
    StrategyRepository,
)

app = typer.Typer(name="evodev", help="EvoDev: Self-Improving Developer Experience Layer")
profiles_app = typer.Typer(help="Manage portable experience profiles (.vxp)")
experience_app = typer.Typer(help="Inspect and manage stored experiences")
benchmark_app = typer.Typer(help="Benchmark and evaluate learning engine performance")
connectors_app = typer.Typer(help="Manage AI coding agent connectors")
retention_app = typer.Typer(help="Audit storage usage and clean aged data")
schedule_app = typer.Typer(help="Manage background maintenance schedules")
checkpoints_app = typer.Typer(help="Manage safe Git, DB, and Profile checkpoints")
skills_app = typer.Typer(help="Inspect and manage self-improving skills")
memory_app = typer.Typer(help="Inspect and manage categorized persistent memory")

app.add_typer(profiles_app, name="profiles")
app.add_typer(experience_app, name="experience")
app.add_typer(benchmark_app, name="benchmark")
app.add_typer(connectors_app, name="connectors")
app.add_typer(retention_app, name="retention")
app.add_typer(schedule_app, name="schedule")
app.add_typer(checkpoints_app, name="checkpoints")
app.add_typer(skills_app, name="skills")
app.add_typer(memory_app, name="memory")

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
    mem_repo = MemoryRepository(db)
    skill_repo = SkillRepository(db)

    mgr = ProfileManager(
        p_repo, l_repo, s_repo, e_repo, b_repo, config,
        memory_repo=mem_repo, skill_repo=skill_repo
    )
    collector = CollectorService(ev_repo, e_repo, p_repo)
    engine = RetrievalEngine(l_repo, p_repo)

    return config, db, p_repo, l_repo, s_repo, e_repo, ev_repo, b_repo, mgr, collector, engine


def _get_extended_services():
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
    mem_repo = MemoryRepository(db)
    skill_repo = SkillRepository(db)
    cp_repo = CheckpointRepository(db)
    sched_repo = ScheduleRepository(db)

    mgr = ProfileManager(
        p_repo, l_repo, s_repo, e_repo, b_repo, config,
        memory_repo=mem_repo, skill_repo=skill_repo
    )
    mem_mgr = MemoryManager(mem_repo, l_repo, p_repo)
    skill_engine = SkillEngine(skill_repo, p_repo)
    cp_mgr = CheckpointManager(cp_repo, config, db, mgr)
    sched_engine = SchedulerEngine(sched_repo)

    return config, db, p_repo, l_repo, mgr, mem_repo, skill_repo, cp_repo, sched_repo, mem_mgr, skill_engine, cp_mgr, sched_engine


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
    kilo = KiloCodeConnector()

    table = Table(title="AI Coding Agent Connectors")
    table.add_column("Connector", style="cyan")
    table.add_column("Installed Status", style="bold")
    table.add_column("Integration Mechanism")

    op_status = "[green]AVAILABLE[/green]" if opencode.is_available() else "[yellow]NOT INSTALLED[/yellow]"
    table.add_row("OpenCode", op_status, "MCP stdio server (evodev_get_lessons, evodev_record_outcome)")

    gm_status = "[green]AVAILABLE[/green]" if gemini.is_available() else "[dim]OPTIONAL[/dim]"
    table.add_row("Gemini CLI / Antigravity", gm_status, ".agents/hooks.json (PreInvocation, PostToolUse, Stop)")

    kilo_status = "[green]AVAILABLE[/green]" if kilo.is_available() else "[dim]STANDBY[/dim]"
    table.add_row("Kilo Code", kilo_status, ".kilo/mcp.json stdio MCP server")

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


@connectors_app.command("install-kilo")
def connectors_install_kilo(
    project_dir: str = typer.Option(".", help="Target project root directory"),
):
    """Provision .kilo/mcp.json MCP server configuration in target project."""
    connector = KiloCodeConnector()
    out = connector.apply_to_project(Path(project_dir))
    console.print(f"[bold green]Configured Kilo Code MCP server at:[/bold green] [cyan]{out}[/cyan]")


@connectors_app.command("install-hermes")
def connectors_install_hermes(
    project_dir: str = typer.Option(".", help="Target project root directory"),
):
    """Provision hermes_config.json tool schemas and hooks in target project."""
    connector = HermesConnector()
    out = connector.generate_hermes_config(Path(project_dir))
    console.print(f"[bold green]Configured Hermes Agent tools at:[/bold green] [cyan]{out}[/cyan]")


# ==========================================
# Categorized Memory Commands
# ==========================================

@memory_app.command("list")
def memory_list(
    category: Optional[str] = typer.Option(None, help="Filter by memory category (preferences, architecture, lessons, etc.)"),
    project_id: Optional[str] = typer.Option(None, help="Filter by project ID"),
    limit: int = typer.Option(50, help="Maximum number of memories to display"),
):
    """List categorized persistent memories."""
    _, _, p_repo, _, _, mem_repo, _, _, _, _, _, _, _ = _get_extended_services()
    active = p_repo.get_active()
    profile_id = active.profile_id if active else "default"

    cat_enum = MemoryCategory(category) if category else None
    memories = mem_repo.list_by_profile(profile_id, category=cat_enum, project_id=project_id, active_only=True)

    table = Table(title=f"Categorized Persistent Memory ({len(memories[:limit])} items)")
    table.add_column("ID", style="dim", no_wrap=True)
    table.add_column("Category", style="cyan")
    table.add_column("Title", style="bold", no_wrap=True)
    table.add_column("Scope", style="green")
    table.add_column("Confidence", style="yellow")
    table.add_column("Project", style="dim")

    for m in memories[:limit]:
        table.add_row(
            m.id[:8] + "...",
            m.category.value,
            m.title,
            m.scope.value,
            f"{m.confidence:.2f}",
            m.project_id or "global",
        )

    console.print(table)


@memory_app.command("search")
def memory_search(
    query: str = typer.Argument(..., help="Search query for memories"),
    project_id: str = typer.Option("default", help="Current project ID for scope enforcement"),
    category: Optional[str] = typer.Option(None, help="Optional category filter"),
    limit: int = typer.Option(10, help="Max results"),
):
    """Search categorized persistent memory with strict scope enforcement."""
    _, _, p_repo, _, _, _, _, _, _, mem_mgr, _, _, _ = _get_extended_services()
    active = p_repo.get_active()
    profile_id = active.profile_id if active else "default"

    categories = [MemoryCategory(category)] if category else None
    results = mem_mgr.retrieve_context(
        query=query,
        project_id=project_id,
        profile_id=profile_id,
        categories=categories,
        limit=limit,
    )

    table = Table(title=f"Memory Search Results for '{query}' ({len(results)} found)")
    table.add_column("Category", style="cyan")
    table.add_column("Title", style="bold", no_wrap=True)
    table.add_column("Content Snippet")
    table.add_column("Scope", style="green")

    for m in results:
        snippet = json.dumps(m.content)
        if len(snippet) > 60:
            snippet = snippet[:57] + "..."
        table.add_row(m.category.value, m.title, snippet, m.scope.value)

    console.print(table)


@memory_app.command("add")
def memory_add(
    title: str = typer.Argument(..., help="Short title/summary of the memory"),
    content: str = typer.Option("{}", help="JSON content or text details"),
    category: str = typer.Option("preferences", help="Memory category"),
    project_id: Optional[str] = typer.Option(None, help="Project ID (required if project-private)"),
):
    """Add a verified memory item."""
    _, _, _, _, _, _, _, _, _, mem_mgr, _, _, _ = _get_extended_services()
    try:
        content_dict = json.loads(content)
        if not isinstance(content_dict, dict):
            content_dict = {"text": content}
    except Exception:
        content_dict = {"text": content}

    cat_enum = MemoryCategory(category)
    item = mem_mgr.record_memory(
        category=cat_enum,
        title=title,
        content=content_dict,
        project_id=project_id,
    )
    console.print(f"[bold green]Saved memory item:[/bold green] [cyan]{item.id}[/cyan] ({item.category.value}: {item.title})")


@memory_app.command("delete")
def memory_delete(
    memory_id: str = typer.Argument(..., help="Memory item ID"),
    hard: bool = typer.Option(False, "--hard", help="Permanently delete instead of deactivating"),
):
    """Deactivate or remove a memory item."""
    _, _, _, _, _, _, _, _, _, mem_mgr, _, _, _ = _get_extended_services()
    if hard:
        ok = mem_mgr.delete_memory(memory_id)
        action = "Permanently deleted"
    else:
        ok = mem_mgr.deactivate_memory(memory_id)
        action = "Deactivated"

    if ok:
        console.print(f"[bold green]{action} memory item:[/bold green] [cyan]{memory_id}[/cyan]")
    else:
        console.print(f"[red]Failed to find memory item:[/red] {memory_id}")


@memory_app.command("consolidate")
def memory_consolidate():
    """Consolidate duplicate active memories within active profile."""
    _, _, p_repo, _, _, _, _, _, _, mem_mgr, _, _, _ = _get_extended_services()
    active = p_repo.get_active()
    profile_id = active.profile_id if active else "default"
    count = mem_mgr.consolidate_duplicates(profile_id)
    console.print(f"[bold green]Consolidation complete![/bold green] Merged [cyan]{count}[/cyan] duplicate memory items.")


# ==========================================
# Self-Improving Skills Commands
# ==========================================

@skills_app.command("list")
def skills_list():
    """List registered self-improving skills and their current versions."""
    _, _, p_repo, _, _, _, skill_repo, _, _, _, _, _, _ = _get_extended_services()
    active = p_repo.get_active()
    profile_id = active.profile_id if active else "default"

    skills = skill_repo.list_by_profile(profile_id)
    table = Table(title=f"EvoDev Skills ({len(skills)} registered)")
    table.add_column("ID", style="dim", no_wrap=True)
    table.add_column("Name", style="cyan bold", no_wrap=True)
    table.add_column("Version", style="green")
    table.add_column("Status", style="yellow")
    table.add_column("Success Rate")
    table.add_column("Evaluations", justify="right")

    for s in skills:
        rate_str = f"{s.success_rate * 100:.1f}%" if s.total_evaluations > 0 else "N/A"
        table.add_row(
            s.id[:8] + "...",
            s.name,
            f"v{s.current_version}",
            s.status.value,
            rate_str,
            str(s.total_evaluations),
        )

    console.print(table)


@skills_app.command("create")
def skills_create(
    name: str = typer.Argument(..., help="Skill name"),
    description: str = typer.Option(..., help="Skill purpose and description"),
    instructions: str = typer.Option(..., help="Initial procedure instructions"),
    category: str = typer.Option("general", help="Category (e.g. debugging, testing, refactoring)"),
):
    """Create a new draft self-improving skill."""
    _, _, _, _, _, _, _, _, _, _, skill_engine, _, _ = _get_extended_services()
    skill = skill_engine.create_skill(
        name=name,
        description=description,
        initial_instructions=instructions,
        category=category,
    )
    console.print(f"[bold green]Created new skill:[/bold green] [cyan]{skill.name}[/cyan] (v{skill.current_version}, ID: {skill.id})")


@skills_app.command("view")
def skills_view(
    skill_id: str = typer.Argument(..., help="Skill ID to view"),
    format: str = typer.Option("markdown", help="Rendering format: markdown, mcp, or hermes"),
):
    """Render a skill for humans or AI coding agents."""
    from evodev.skills.renderer import SkillRenderer

    _, _, _, _, _, _, skill_repo, _, _, _, _, _, _ = _get_extended_services()
    skill = skill_repo.get_by_id(skill_id)
    if not skill:
        console.print(f"[red]Skill not found:[/red] {skill_id}")
        raise typer.Exit(1)

    version_obj = skill_repo.get_version(skill_id, skill.current_version)
    renderer = SkillRenderer()

    if format.lower() == "mcp":
        out = json.dumps(renderer.render_mcp_tool_description(skill, version_obj), indent=2)
    elif format.lower() == "hermes":
        out = renderer.render_hermes_prompt(skill, version_obj)
    else:
        out = renderer.render_markdown(skill, version_obj)

    console.print(out)


@skills_app.command("evaluate")
def skills_evaluate(
    skill_id: str = typer.Argument(..., help="Skill ID to evaluate"),
    success: bool = typer.Option(True, "--success/--failure", help="Record success or failure trial"),
    score: float = typer.Option(1.0, help="Benchmark score between 0.0 and 1.0"),
):
    """Record an empirical benchmark evaluation on the active skill version."""
    _, _, _, _, _, _, skill_repo, _, _, _, skill_engine, _, _ = _get_extended_services()
    skill = skill_repo.get_by_id(skill_id)
    if not skill:
        console.print(f"[red]Skill not found:[/red] {skill_id}")
        raise typer.Exit(1)

    eval_result = skill_engine.evaluator.evaluate_version(
        skill_id=skill.id,
        version=skill.current_version,
        trials=[(success, score, f"CLI manual benchmark (success={success})")],
    )
    console.print(f"[bold green]Recorded evaluation for skill v{skill.current_version}:[/bold green]")
    console.print(f"  Passed: {eval_result.passed} | Score: {eval_result.score:.2f} | Benchmark: {eval_result.benchmark_name}")


# ==========================================
# Safe Checkpoints Commands
# ==========================================

@checkpoints_app.command("list")
def checkpoints_list(
    checkpoint_type: Optional[str] = typer.Option(None, help="Filter by type: git, database, profile"),
):
    """List historical Git, SQLite database, and Profile checkpoints."""
    _, _, _, _, _, _, _, _, _, _, _, cp_mgr, _ = _get_extended_services()
    c_type = CheckpointType(checkpoint_type) if checkpoint_type else None
    cps = cp_mgr.list_checkpoints(checkpoint_type=c_type)

    table = Table(title=f"Historical Checkpoints ({len(cps)} available)")
    table.add_column("ID", style="dim", no_wrap=True)
    table.add_column("Type", style="cyan bold", no_wrap=True)
    table.add_column("Summary", no_wrap=True)
    table.add_column("Reference", style="dim")
    table.add_column("Created At", style="green", no_wrap=True)

    for cp in cps:
        table.add_row(
            cp.id[:8] + "...",
            cp.checkpoint_type.value.upper(),
            cp.summary,
            cp.reference[:30] + ("..." if len(cp.reference) > 30 else ""),
            cp.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        )

    console.print(table)


@checkpoints_app.command("create")
def checkpoints_create(
    summary: str = typer.Argument(..., help="Summary description of checkpoint"),
    type: str = typer.Option("database", help="Checkpoint type: git, database, or profile"),
    repo_path: str = typer.Option(".", help="Repository path if creating a git checkpoint"),
):
    """Create a new safe checkpoint before risky operations."""
    _, _, p_repo, _, _, _, _, _, _, _, _, cp_mgr, _ = _get_extended_services()
    t_lower = type.lower()
    if t_lower == "git":
        rec = cp_mgr.create_git_checkpoint(summary=summary, repo_path=Path(repo_path))
    elif t_lower == "database":
        rec = cp_mgr.create_database_checkpoint(summary=summary)
    elif t_lower == "profile":
        active = p_repo.get_active()
        pid = active.profile_id if active else "default"
        rec = cp_mgr.create_profile_checkpoint(profile_id=pid, summary=summary)
    else:
        console.print(f"[red]Unknown checkpoint type:[/red] {type}. Choose git, database, or profile.")
        raise typer.Exit(1)

    console.print(f"[bold green]Created {rec.checkpoint_type.value.upper()} checkpoint:[/bold green] [cyan]{rec.id}[/cyan]")
    console.print(f"Reference: [dim]{rec.reference}[/dim]")


@checkpoints_app.command("restore")
def checkpoints_restore(
    checkpoint_id: str = typer.Argument(..., help="Checkpoint ID to restore"),
    yes: bool = typer.Option(False, "-y", "--yes", help="Confirm rollback without prompt"),
):
    """Restore EvoDev database state from a safe database checkpoint."""
    _, _, _, _, _, _, _, _, _, _, _, cp_mgr, _ = _get_extended_services()
    if not yes:
        confirmed = typer.confirm(
            f"Are you sure you want to restore database checkpoint {checkpoint_id}? This replaces the active database.",
            default=False,
        )
        if not confirmed:
            console.print("[yellow]Restore cancelled.[/yellow]")
            raise typer.Exit(0)

    try:
        cp_mgr.rollback_database_checkpoint(checkpoint_id)
        console.print(f"[bold green]Successfully rolled back to database checkpoint:[/bold green] [cyan]{checkpoint_id}[/cyan]")
    except Exception as e:
        console.print(f"[bold red]Rollback failed:[/bold red] {e}")
        raise typer.Exit(1)


# ==========================================
# Background Scheduler Commands
# ==========================================

@schedule_app.command("list")
def schedule_list():
    """List registered persistent background maintenance schedules."""
    _, _, _, _, _, _, _, _, _, _, _, _, sched_engine = _get_extended_services()
    jobs = sched_engine.list_jobs()

    table = Table(title=f"Scheduled Maintenance Tasks ({len(jobs)} registered)")
    table.add_column("ID", style="dim", no_wrap=True)
    table.add_column("Job Name", style="bold", no_wrap=True)
    table.add_column("Type", style="cyan")
    table.add_column("Schedule", style="yellow")
    table.add_column("Enabled", style="green")
    table.add_column("Last Run", style="dim")
    table.add_column("Next Run", style="green")
    table.add_column("Status")

    for j in jobs:
        table.add_row(
            j.id[:8] + "...",
            j.name,
            j.job_type.value,
            j.schedule_expr,
            "YES" if j.enabled else "NO",
            j.last_run_at.strftime("%H:%M:%S") if j.last_run_at else "-",
            j.next_run_at.strftime("%Y-%m-%d %H:%M:%S") if j.next_run_at else "-",
            j.last_status,
        )

    console.print(table)


@schedule_app.command("add")
def schedule_add(
    name: str = typer.Argument(..., help="Job descriptive name"),
    job_type: str = typer.Option("health_check", help="Type: benchmark_run, stale_cleanup, health_check, dependency_audit, scheduled_report"),
    schedule: str = typer.Option("daily", help="Schedule interval: daily, hourly, every:2h, interval:3600"),
):
    """Add a new persistent background automation job."""
    _, _, _, _, _, _, _, _, _, _, _, _, sched_engine = _get_extended_services()
    try:
        jt = JobType(job_type)
    except ValueError:
        console.print(f"[red]Invalid job type:[/red] {job_type}")
        raise typer.Exit(1)

    job = sched_engine.register_job(name=name, job_type=jt, schedule_expr=schedule)
    console.print(f"[bold green]Registered scheduled task:[/bold green] [cyan]{job.name}[/cyan] ({job.schedule_expr}, Next: {job.next_run_at})")


@schedule_app.command("run-pending")
def schedule_run_pending():
    """Execute all due scheduled tasks immediately."""
    _, _, _, _, _, _, _, _, _, _, _, _, sched_engine = _get_extended_services()
    results = sched_engine.run_pending()
    if not results:
        console.print("[dim]No scheduled tasks were due for execution.[/dim]")
        return

    for r in results:
        console.print(f"Executed [bold]{r['name']}[/bold]: status=[green]{r['status']}[/green] (Next: {r['next_run_at']})")


@schedule_app.command("delete")
def schedule_delete(
    job_id: str = typer.Argument(..., help="ID of job to delete"),
):
    """Permanently delete a scheduled task."""
    _, _, _, _, _, _, _, _, _, _, _, _, sched_engine = _get_extended_services()
    if sched_engine.delete_job(job_id):
        console.print(f"[bold green]Deleted scheduled job:[/bold green] [cyan]{job_id}[/cyan]")
    else:
        console.print(f"[red]Job not found:[/red] {job_id}")


# ==========================================
# Desktop GUI Command
# ==========================================

@app.command()
def gui():
    """Launch native Tkinter desktop dashboard for EvoDev."""
    from evodev.gui.app import run_gui
    config = load_config()
    console.print(f"[bold cyan]Launching {config.product_name} 2.0 Native Desktop GUI...[/bold cyan]")
    run_gui(config)


# ==========================================
# Uninstallation Command (Part E)
# ==========================================

@app.command()
def uninstall(
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview resources scheduled for removal without making any changes"),
    yes: bool = typer.Option(False, "-y", "--yes", help="Confirm uninstallation without interactive prompt"),
    backup: bool = typer.Option(True, "--backup/--no-backup", help="Create a backup zip of database and profiles before deletion"),
    keep_exports: bool = typer.Option(True, "--keep-exports/--no-keep-exports", help="Preserve exported .vxp files in data directory"),
):
    """Safely uninstall EvoDev application state while preserving user .vxp archives."""
    config, db, _, _, _, _, _, _, _, _, _ = _get_services()
    uninstaller = EvoDevUninstaller(config=config, db_manager=db, search_workspace_integrations=True)
    plan = uninstaller.build_plan(keep_exports=keep_exports)

    console.print("\n[bold red]=== EvoDev Uninstallation Assessment ===[/bold red]")
    console.print(f"Detected Installation Type: [cyan]{plan.installation_type.value.upper()}[/cyan]")
    console.print(f"Managed Data Directory: [cyan]{plan.data_dir}[/cyan]\n")

    # Table of files to remove
    t_remove = Table(title="1. Application Resources Scheduled for Deletion")
    t_remove.add_column("Category", style="cyan")
    t_remove.add_column("Path", style="dim")
    t_remove.add_column("Description")

    if plan.items_to_remove:
        for item in plan.items_to_remove:
            t_remove.add_row(item.category.upper(), str(item.path), item.description)
    else:
        t_remove.add_row("NONE", "-", "No existing EvoDev database or config files found")
    console.print(t_remove)

    # Table of integration entries to clean
    if plan.integrations_to_clean:
        t_clean = Table(title="2. Integration Config Entries to Clean (EvoDev keys only)")
        t_clean.add_column("Agent", style="cyan")
        t_clean.add_column("Config File", style="dim")
        t_clean.add_column("Target Key", style="bold yellow")
        for c in plan.integrations_to_clean:
            t_clean.add_row(c.agent_name, str(c.config_path), c.entry_key)
        console.print(t_clean)

    # Table of preserved items
    t_pres = Table(title="3. User Resources Preserved (NEVER TOUCHED)")
    t_pres.add_column("Resource", style="green")
    t_pres.add_column("Reason")
    if plan.preserved_items:
        for p in plan.preserved_items:
            t_pres.add_row(str(p.path), p.reason)
    else:
        t_pres.add_row("External .vxp Files", "All user-owned .vxp archives and external backups remain untouched")
    console.print(t_pres)

    console.print(f"\n[bold]Package Removal Manual Command:[/bold] [yellow]{plan.package_removal_command}[/yellow]\n")

    if dry_run:
        result = uninstaller.execute_uninstall(plan, dry_run=True)
        console.print("[bold cyan]DRY-RUN COMPLETE:[/bold cyan] Zero files were deleted or modified.")
        return

    if not yes:
        confirmed = typer.confirm(
            "Are you sure you want to proceed with uninstallation? This removes local EvoDev database and config.",
            default=False,
        )
        if not confirmed:
            console.print("[yellow]Uninstallation cancelled. No changes were made.[/yellow]")
            raise typer.Exit(0)

    # Execute uninstallation
    result = uninstaller.execute_uninstall(plan, perform_backup=backup, dry_run=False)

    if result.backup_path:
        console.print(f"[bold green]Created pre-uninstall backup:[/bold green] [cyan]{result.backup_path}[/cyan]")

    console.print(f"[bold green]Uninstallation completed successfully![/bold green]")
    console.print(f"Removed application files: [cyan]{len(result.removed_files)}[/cyan]")
    console.print(f"Cleaned connector entries: [cyan]{len(result.cleaned_integrations)}[/cyan]")

    if result.errors:
        console.print("[yellow]Warnings during uninstallation:[/yellow]")
        for err in result.errors:
            console.print(f"  • {err.get('path', 'General')}: {err.get('error')}")

    console.print(f"\nTo remove the Python package itself, run: [bold cyan]{result.package_instructions}[/bold cyan]\n")


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
