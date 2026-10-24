"""Main desktop application window and service orchestrator for EvoDev 2.0."""

import logging
from pathlib import Path
import sys
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Dict, Optional

from evodev.collector.collector_service import CollectorService
from evodev.config import EvoDevConfig, load_config
from evodev.connectors.gemini import GeminiCLIConnector
from evodev.connectors.generic import GenericAdapter
from evodev.connectors.hermes import HermesConnector
from evodev.connectors.kilocode import KiloCodeConnector
from evodev.connectors.manager import ConnectorManager, ConnectorRegistry
from evodev.connectors.opencode import OpenCodeConnector
from evodev.checkpoints.manager import CheckpointManager
from evodev.gui.components.dialogs import NewProfileDialog
from evodev.gui.theme import Colors, Fonts, apply_theme
from evodev.gui.views import (
    BenchmarksView,
    CheckpointsView,
    ConnectorsView,
    DoctorView,
    ExperiencesView,
    InspectorView,
    LessonsView,
    MemoryView,
    OrchestrationView,
    OverviewView,
    SchedulerView,
    SkillsView,
    StrategiesView,
    UninstallView,
)
from evodev.gui.workers import WorkerPool
from evodev.memory.manager import MemoryManager
from evodev.orchestration.orchestrator import SpecialistOrchestrator
from evodev.profiles.inspector import ProfileInspector
from evodev.profiles.manager import ProfileManager
from evodev.retrieval.engine import RetrievalEngine
from evodev.scheduler.engine import SchedulerEngine
from evodev.skills.engine import SkillEngine
from evodev.storage.db import DatabaseManager, close_db, get_db
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

logger = logging.getLogger(__name__)


class EvoDevApp:
    """Native Tkinter Desktop GUI for EvoDev 2.0."""

    VIEW_TITLES = {
        "overview": ("System Overview", "Runtime health, storage consumption, and active experience footprint."),
        "inspector": ("Experience Inspector", "Deep inspection of profiles, .vxp archives, and competence analytics."),
        "memory": ("Categorized Memory", "Partitioned persistent recall across 8 distinct memory categories."),
        "skills": ("Self-Improving Skills", "Reusable procedures, versions, and empirical benchmark evaluations."),
        "lessons": ("Verified Lessons", "Accumulated lessons, trigger patterns, and knowledge scopes."),
        "strategies": ("Strategy Statistics", "Bayesian expected success rates accounting for attempts and regressions."),
        "experiences": ("Experience Log", "Historical completed coding tasks and verified outcomes."),
        "orchestration": ("Specialist Delegation", "Multi-agent task decomposition, specialist roles, and human approval gates."),
        "scheduler": ("Persistent Automation", "Local background maintenance tasks, stale cleanup, and health schedules."),
        "checkpoints": ("Safe Checkpoints", "Reviewable Git diffs, SQLite snapshots, and safe non-destructive rollback."),
        "benchmarks": ("Empirical Benchmarks", "Evaluate agent performance across challenging coding tasks."),
        "connectors": ("Agent Connectors", "Manage unified integrations for OpenCode, Gemini CLI, Kilo Code, and Hermes."),
        "doctor": ("Diagnostics & Doctor", "Verify database health, write permissions, and secret redaction."),
        "uninstall": ("Uninstall EvoDev", "Safely remove application state while strictly preserving external .vxp archives."),
    }

    def __init__(self, root: Optional[tk.Tk] = None, config: Optional[EvoDevConfig] = None):
        self.root = root or tk.Tk()
        self.config = config or load_config()

        # Initialize core services
        self.db = get_db(self.config)
        MigrationManager(self.db).run_migrations()

        self.p_repo = ProfileRepository(self.db)
        self.l_repo = LessonRepository(self.db)
        self.s_repo = StrategyRepository(self.db)
        self.e_repo = ExperienceRepository(self.db)
        self.ev_repo = EventRepository(self.db)
        self.b_repo = BenchmarkRepository(self.db)
        self.mem_repo = MemoryRepository(self.db)
        self.skill_repo = SkillRepository(self.db)
        self.cp_repo = CheckpointRepository(self.db)
        self.sched_repo = ScheduleRepository(self.db)

        # Ensure default profile
        if not self.p_repo.get_active():
            existing = self.p_repo.get_by_name("Default")
            if not existing:
                from evodev.models.profile import ProfileManifest
                self.p_repo.create(ProfileManifest(name="Default"), is_active=True)
            else:
                self.p_repo.activate(existing.profile_id)

        self.profile_mgr = ProfileManager(
            self.p_repo, self.l_repo, self.s_repo, self.e_repo, self.b_repo, self.config,
            memory_repo=self.mem_repo, skill_repo=self.skill_repo
        )
        self.inspector = ProfileInspector(self.p_repo, self.l_repo, self.s_repo, self.e_repo, self.b_repo, self.ev_repo, self.config)
        self.collector = CollectorService(self.ev_repo, self.e_repo, self.p_repo)
        self.engine = RetrievalEngine(self.l_repo, self.p_repo)
        self.mem_mgr = MemoryManager(self.mem_repo, self.l_repo, self.p_repo)
        self.skill_engine = SkillEngine(self.skill_repo, self.p_repo)
        self.cp_mgr = CheckpointManager(self.cp_repo, self.config, self.db, self.profile_mgr)
        self.sched_engine = SchedulerEngine(self.sched_repo)

        # Initialize unified connectors
        self.registry = ConnectorRegistry()
        self.opencode_conn = OpenCodeConnector(self.l_repo, self.p_repo, self.s_repo, self.collector)
        self.gemini_conn = GeminiCLIConnector(self.l_repo, self.p_repo, self.s_repo, self.collector)
        self.generic_conn = GenericAdapter(self.collector, self.l_repo, self.p_repo, self.s_repo)
        self.kilocode_conn = KiloCodeConnector(self.l_repo, self.p_repo, self.s_repo, self.collector)
        self.hermes_conn = HermesConnector(self.engine, self.ev_repo, self.s_repo, self.l_repo, self.p_repo)

        self.registry.register(self.opencode_conn)
        self.registry.register(self.gemini_conn)
        self.registry.register(self.generic_conn)
        self.registry.register(self.kilocode_conn)
        self.registry.register(self.hermes_conn)

        self.connector_manager = ConnectorManager(
            registry=self.registry,
            retrieval_engine=self.engine,
            collector_service=self.collector,
            strategy_repo=self.s_repo,
            lesson_repo=self.l_repo,
            profile_repo=self.p_repo,
            config=self.config,
        )

        self.orchestrator = SpecialistOrchestrator(self.connector_manager)

        # Worker pool for off-main-thread tasks
        self.worker_pool = WorkerPool(self.root, max_workers=4)

        # Setup GUI Window
        self.root.title("EvoDev 2.0 — Experience Layer")
        self.root.geometry("1180x760")
        self.root.minsize(950, 620)
        self.style = apply_theme(self.root)

        # Window closing protocol
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.current_view_key = "overview"
        self.views: Dict[str, tk.Frame] = {}
        self.nav_buttons: Dict[str, ttk.Button] = {}

        self._build_layout()
        self.switch_view("overview")
        self.update_active_profile_display()

    def _build_layout(self) -> None:
        """Create sidebar, topbar, and main view container."""
        # Main horizontally split frame
        self.main_container = tk.Frame(self.root, bg=Colors.BG_DARK)
        self.main_container.pack(fill="both", expand=True)

        # 1. Left Sidebar
        self.sidebar = tk.Frame(self.main_container, bg=Colors.SIDEBAR, width=250)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        # Brand header
        brand_f = tk.Frame(self.sidebar, bg=Colors.SIDEBAR, padx=16, pady=16)
        brand_f.pack(fill="x")
        tk.Label(brand_f, text="⚡ EvoDev", font=Fonts.HEADER_MEDIUM, bg=Colors.SIDEBAR, fg=Colors.ACCENT_CYAN).pack(anchor="w")
        tk.Label(brand_f, text="Experience Layer 2.0", font=Fonts.SMALL, bg=Colors.SIDEBAR, fg=Colors.TEXT_MUTED).pack(anchor="w")

        # Active Profile Card in Sidebar
        self.profile_card = tk.Frame(
            self.sidebar,
            bg=Colors.SURFACE,
            highlightbackground=Colors.BORDER,
            highlightthickness=1,
            padx=12,
            pady=10,
        )
        self.profile_card.pack(fill="x", padx=14, pady=(4, 14))

        tk.Label(self.profile_card, text="ACTIVE PROFILE", font=Fonts.SMALL_BOLD, bg=Colors.SURFACE, fg=Colors.TEXT_MUTED).pack(anchor="w")

        p_row = tk.Frame(self.profile_card, bg=Colors.SURFACE)
        p_row.pack(fill="x", pady=(2, 6))

        self.sidebar_profile_name = tk.Label(p_row, text="Loading...", font=Fonts.BODY_BOLD, bg=Colors.SURFACE, fg=Colors.TEXT_MAIN)
        self.sidebar_profile_name.pack(side="left")

        self.sidebar_profile_ver = tk.Label(p_row, text="v1.0.0", font=Fonts.SMALL_BOLD, bg=Colors.SURFACE_LIGHT, fg=Colors.ACCENT_TEAL, padx=5, pady=1)
        self.sidebar_profile_ver.pack(side="right")

        # Profile Switch Dropdown
        self.profile_switch_cb = ttk.Combobox(self.profile_card, state="readonly", width=18)
        self.profile_switch_cb.pack(fill="x")
        self.profile_switch_cb.bind("<<ComboboxSelected>>", self._on_switch_profile)

        # Navigation Menu
        nav_f = tk.Frame(self.sidebar, bg=Colors.SIDEBAR)
        nav_f.pack(fill="x", padx=8)

        nav_items = [
            ("overview", "📊  Overview & Telemetry"),
            ("inspector", "🔍  Experience Inspector"),
            ("memory", "🧠  Categorized Memory"),
            ("skills", "⚡  Self-Improving Skills"),
            ("lessons", "💡  Verified Lessons"),
            ("strategies", "🎯  Strategy Statistics"),
            ("experiences", "📝  Experience Log"),
            ("orchestration", "🤖  Specialist Delegation"),
            ("scheduler", "⏱️  Automation Scheduler"),
            ("checkpoints", "🛡️  Safe Checkpoints"),
            ("benchmarks", "📈  Empirical Benchmarks"),
            ("connectors", "🔌  Agent Connectors"),
            ("doctor", "🩺  Diagnostics & Doctor"),
            ("uninstall", "🗑️  Uninstall EvoDev"),
        ]

        for key, label in nav_items:
            btn = ttk.Button(
                nav_f,
                text=label,
                style="Nav.TButton",
                command=lambda k=key: self.switch_view(k),
            )
            btn.pack(fill="x", pady=2)
            self.nav_buttons[key] = btn

        # Sidebar Footer
        footer = tk.Frame(self.sidebar, bg=Colors.SIDEBAR, padx=14, pady=12)
        footer.pack(side="bottom", fill="x")
        tk.Label(footer, text="Local Engine · SQLite WAL", font=Fonts.SMALL, bg=Colors.SIDEBAR, fg=Colors.TEXT_DIM).pack(anchor="w")

        # 2. Right Content Area (Topbar + View)
        self.content_area = tk.Frame(self.main_container, bg=Colors.BG_DARK)
        self.content_area.pack(side="right", fill="both", expand=True)

        # Topbar
        self.topbar = tk.Frame(
            self.content_area,
            bg=Colors.SURFACE,
            highlightbackground=Colors.BORDER,
            highlightthickness=1,
            padx=20,
            pady=12,
        )
        self.topbar.pack(fill="x")

        title_box = tk.Frame(self.topbar, bg=Colors.SURFACE)
        title_box.pack(side="left")

        self.page_heading = tk.Label(title_box, text="System Overview", font=Fonts.HEADER_MEDIUM, bg=Colors.SURFACE, fg=Colors.TEXT_MAIN)
        self.page_heading.pack(anchor="w")

        self.page_subheading = tk.Label(title_box, text="Runtime health and telemetry", font=Fonts.SMALL, bg=Colors.SURFACE, fg=Colors.TEXT_MUTED)
        self.page_subheading.pack(anchor="w", pady=(2, 0))

        # Topbar Action Buttons
        top_actions = tk.Frame(self.topbar, bg=Colors.SURFACE)
        top_actions.pack(side="right")

        self.btn_top_refresh = ttk.Button(top_actions, text="🔄 Refresh", command=self.refresh_current_view)
        self.btn_top_refresh.pack(side="left", padx=(0, 8))

        self.btn_top_new_profile = ttk.Button(top_actions, text="+ New Profile", style="Primary.TButton", command=self._open_new_profile_dialog)
        self.btn_top_new_profile.pack(side="left")

        # Views Container
        self.views_container = tk.Frame(self.content_area, bg=Colors.BG_DARK)
        self.views_container.pack(fill="both", expand=True)

        # Instantiate View Frames
        self.views["overview"] = OverviewView(self.views_container, self)
        self.views["inspector"] = InspectorView(self.views_container, self)
        self.views["memory"] = MemoryView(self.views_container, self)
        self.views["skills"] = SkillsView(self.views_container, self)
        self.views["lessons"] = LessonsView(self.views_container, self)
        self.views["strategies"] = StrategiesView(self.views_container, self)
        self.views["experiences"] = ExperiencesView(self.views_container, self)
        self.views["orchestration"] = OrchestrationView(self.views_container, self)
        self.views["scheduler"] = SchedulerView(self.views_container, self)
        self.views["checkpoints"] = CheckpointsView(self.views_container, self)
        self.views["benchmarks"] = BenchmarksView(self.views_container, self)
        self.views["connectors"] = ConnectorsView(self.views_container, self)
        self.views["doctor"] = DoctorView(self.views_container, self)
        self.views["uninstall"] = UninstallView(self.views_container, self)

    def switch_view(self, view_key: str) -> None:
        """Switch current content view with active tab highlighting."""
        if view_key not in self.views:
            return

        self.current_view_key = view_key

        # Update sidebar button styles
        for k, btn in self.nav_buttons.items():
            btn.configure(style="ActiveNav.TButton" if k == view_key else "Nav.TButton")

        # Update topbar title & subheading
        title, sub = self.VIEW_TITLES.get(view_key, ("EvoDev", ""))
        self.page_heading.configure(text=title)
        self.page_subheading.configure(text=sub)

        # Hide all views and show selected
        for k, v in self.views.items():
            v.pack_forget()

        selected_view = self.views[view_key]
        selected_view.pack(fill="both", expand=True)

        # Refresh the active view
        if hasattr(selected_view, "refresh"):
            selected_view.refresh()

    def update_active_profile_display(self) -> None:
        """Update active profile label and dropdown values."""
        active = self.p_repo.get_active()
        all_profiles = self.p_repo.list_all()

        p_names = [p.name for p in all_profiles]
        self.profile_switch_cb["values"] = p_names

        if active:
            self.sidebar_profile_name.configure(text=active.name)
            self.sidebar_profile_ver.configure(text=f"v{active.version}")
            self.profile_switch_cb.set(active.name)
        else:
            self.sidebar_profile_name.configure(text="None")
            self.sidebar_profile_ver.configure(text="-")
            self.profile_switch_cb.set("")

    def _on_switch_profile(self, event=None):
        name = self.profile_switch_cb.get()
        if not name:
            return
        p = self.p_repo.get_by_name(name)
        if p:
            self.profile_mgr.activate_profile(p.profile_id)
            self.update_active_profile_display()
            self.refresh_all_views()

    def _open_new_profile_dialog(self):
        NewProfileDialog(self.root, on_create=self._create_profile)

    def _create_profile(self, data: dict):
        manifest = self.profile_mgr.create_profile(
            name=data["name"],
            description=data["description"],
            domains=data["domains"],
            activate=data["activate"],
        )
        self.update_active_profile_display()
        self.refresh_all_views()
        messagebox.showinfo("Success", f"Created profile '{manifest.name}'.", parent=self.root)

    def refresh_current_view(self) -> None:
        """Refresh the currently visible view."""
        self.update_active_profile_display()
        v = self.views.get(self.current_view_key)
        if v and hasattr(v, "refresh"):
            v.refresh()

    def refresh_all_views(self) -> None:
        """Refresh all instantiated view panes."""
        self.update_active_profile_display()
        for v in self.views.values():
            if hasattr(v, "refresh"):
                v.refresh()

    def on_closing(self) -> None:
        """Clean shutdown of background threads, database, and GUI resources."""
        try:
            self.worker_pool.shutdown(wait=False)
        except Exception:
            pass

        try:
            self.connector_manager.shutdown_all()
        except Exception:
            pass

        try:
            self.sched_engine.stop_background_worker()
        except Exception:
            pass

        try:
            close_db()
        except Exception:
            pass

        try:
            self.root.destroy()
        except Exception:
            pass


def run_gui(config: Optional[EvoDevConfig] = None) -> None:
    """Entry point for starting the desktop GUI application."""
    root = tk.Tk()
    app = EvoDevApp(root=root, config=config)
    root.mainloop()
