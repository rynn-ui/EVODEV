"""Experience Inspector view providing deep inspection of profiles, .vxp archives, and competence."""

from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Dict, List, Optional

from evodev.gui.components.dialogs import (
    ConfirmActionDialog,
    InspectFileDialog,
    LessonDetailDialog,
    PasswordDialog,
)
from evodev.gui.components.metric_card import MetricCard
from evodev.gui.components.scrollable_frame import ScrollableFrame
from evodev.gui.theme import Colors, Fonts
from evodev.models.profile import ProfilePackage


class InspectorView(tk.Frame):
    """Deep Experience Inspector tab."""

    def __init__(self, parent: tk.Widget, app: Any):
        super().__init__(parent, bg=Colors.BG_DARK)
        self.app = app
        self.current_profile_id: Optional[str] = None
        self.custom_archive_path: Optional[Path] = None
        self.archive_password: Optional[str] = None
        self.active_subpane = "archive"
        self.active_dimension = "domains"
        self.active_explorer_view = "lessons"

        # Scrollable container
        self.scroll = ScrollableFrame(self, bg=Colors.BG_DARK)
        self.scroll.pack(fill="both", expand=True)
        content = self.scroll.scrollable_content

        # 1. Top Toolbar
        tb_f = tk.Frame(content, bg=Colors.SURFACE, highlightbackground=Colors.BORDER, highlightthickness=1, padx=14, pady=10)
        tb_f.pack(fill="x", padx=16, pady=(12, 12))

        tb_left = tk.Frame(tb_f, bg=Colors.SURFACE)
        tb_left.pack(side="left")

        tk.Label(tb_left, text="SELECT PROFILE:", font=Fonts.SMALL_BOLD, bg=Colors.SURFACE, fg=Colors.TEXT_MUTED).pack(side="left", padx=(0, 8))
        self.profile_combo = ttk.Combobox(tb_left, state="readonly", width=22)
        self.profile_combo.pack(side="left")
        self.profile_combo.bind("<<ComboboxSelected>>", self._on_profile_selected)

        tb_right = tk.Frame(tb_f, bg=Colors.SURFACE)
        tb_right.pack(side="right")

        self.btn_refresh = ttk.Button(tb_right, text="🔄 Refresh", command=self.refresh)
        self.btn_refresh.pack(side="left", padx=(0, 8))

        self.btn_custom_file = ttk.Button(tb_right, text="📂 Inspect .vxp File", command=self._open_file_dialog)
        self.btn_custom_file.pack(side="left", padx=(0, 8))

        self.btn_unlock = ttk.Button(tb_right, text="🔒 Unlock", command=self._open_password_dialog)
        # Hidden by default unless encrypted archive detected

        # State Banner
        self.banner_frame = tk.Frame(content, bg=Colors.SURFACE_LIGHT, padx=12, pady=8)
        self.banner_label = tk.Label(self.banner_frame, text="", font=Fonts.BODY_BOLD, bg=Colors.SURFACE_LIGHT, fg=Colors.TEXT_MAIN)
        self.banner_label.pack(side="left")

        # 2. Profile Metadata Header Card
        self.header_card = tk.Frame(content, bg=Colors.SURFACE, highlightbackground=Colors.BORDER, highlightthickness=1, padx=16, pady=14)
        self.header_card.pack(fill="x", padx=16, pady=(0, 12))

        head_top = tk.Frame(self.header_card, bg=Colors.SURFACE)
        head_top.pack(fill="x")

        self.title_lbl = tk.Label(head_top, text="Profile Name", font=Fonts.HEADER_MEDIUM, bg=Colors.SURFACE, fg=Colors.TEXT_MAIN)
        self.title_lbl.pack(side="left")

        self.badges_frame = tk.Frame(head_top, bg=Colors.SURFACE)
        self.badges_frame.pack(side="left", padx=(12, 0))

        self.badge_ver = tk.Label(self.badges_frame, text="v1.0.0", font=Fonts.SMALL_BOLD, bg=Colors.SURFACE_LIGHT, fg=Colors.TEXT_MAIN, padx=6, pady=1)
        self.badge_ver.pack(side="left", padx=(0, 6))

        self.badge_state = tk.Label(self.badges_frame, text="ACTIVE", font=Fonts.SMALL_BOLD, bg=Colors.SURFACE_LIGHT, fg=Colors.STATUS_GREEN, padx=6, pady=1)
        self.badge_state.pack(side="left", padx=(0, 6))

        self.badge_schema = tk.Label(self.badges_frame, text="Schema v1.0.0", font=Fonts.SMALL_BOLD, bg=Colors.SURFACE_LIGHT, fg=Colors.TEXT_MUTED, padx=6, pady=1)
        self.badge_schema.pack(side="left", padx=(0, 6))

        self.badge_integrity = tk.Label(self.badges_frame, text="SHA-256 Valid", font=Fonts.SMALL_BOLD, bg=Colors.SURFACE_LIGHT, fg=Colors.ACCENT_TEAL, padx=6, pady=1)
        self.badge_integrity.pack(side="left")

        self.btn_delete_profile = ttk.Button(head_top, text="Delete Profile", style="Danger.TButton", command=self._delete_profile)
        self.btn_delete_profile.pack(side="right")

        self.desc_lbl = tk.Label(self.header_card, text="", font=Fonts.BODY, bg=Colors.SURFACE, fg=Colors.TEXT_MUTED, wraplength=700, justify="left")
        self.desc_lbl.pack(anchor="w", pady=(6, 4))

        self.meta_lbl = tk.Label(self.header_card, text="", font=Fonts.SMALL, bg=Colors.SURFACE, fg=Colors.TEXT_DIM)
        self.meta_lbl.pack(anchor="w")

        # 3. High-Level Metric Tiles Grid (7 cards)
        metrics_f = tk.Frame(content, bg=Colors.BG_DARK)
        metrics_f.pack(fill="x", padx=16, pady=(0, 12))

        self.tile_archive_size = MetricCard(metrics_f, label="Archive Size", initial_value="0 B", hint="Compressed .vxp footprint", width=130)
        self.tile_archive_size.pack(side="left", padx=(0, 8), fill="x", expand=True)

        self.tile_uncomp_size = MetricCard(metrics_f, label="Uncompressed", initial_value="0 B", hint="In-memory JSON payload", width=130)
        self.tile_uncomp_size.pack(side="left", padx=(0, 8), fill="x", expand=True)

        self.tile_exps = MetricCard(metrics_f, label="Experiences", initial_value="0", hint="Completed tasks", width=110)
        self.tile_exps.pack(side="left", padx=(0, 8), fill="x", expand=True)

        self.tile_verified = MetricCard(metrics_f, label="Verified Lessons", initial_value="0", hint="Passing test evidence", value_color=Colors.STATUS_GREEN, width=120)
        self.tile_verified.pack(side="left", padx=(0, 8), fill="x", expand=True)

        self.tile_candidates = MetricCard(metrics_f, label="Candidate Lessons", initial_value="0", hint="Pending confirmation", value_color=Colors.STATUS_YELLOW, width=120)
        self.tile_candidates.pack(side="left", padx=(0, 8), fill="x", expand=True)

        self.tile_strategies = MetricCard(metrics_f, label="Strategies", initial_value="0", hint="Bayesian scored records", width=110)
        self.tile_strategies.pack(side="left", padx=(0, 8), fill="x", expand=True)

        self.tile_coverage = MetricCard(metrics_f, label="Domain Coverage", initial_value="0%", hint="Coverage of core domains", width=120)
        self.tile_coverage.pack(side="left", fill="x", expand=True)

        # 4. Sub-Tabs Navigation Bar
        subtabs_nav = tk.Frame(content, bg=Colors.BG_DARK)
        subtabs_nav.pack(fill="x", padx=16, pady=(0, 8))

        self.subtab_buttons = {}
        tabs = [
            ("archive", "📦 Archive Analysis (.vxp)"),
            ("expertise", "📊 Expertise & Competence"),
            ("explorer", "🔎 Knowledge Explorer"),
            ("storage", "💾 Storage Analytics"),
            ("timeline", "⏱️ Version Diff & Timeline"),
        ]
        for key, label in tabs:
            btn = ttk.Button(
                subtabs_nav,
                text=label,
                style="SubTab.TButton",
                command=lambda k=key: self._switch_subpane(k),
            )
            btn.pack(side="left", padx=(0, 8))
            self.subtab_buttons[key] = btn

        # 5. Sub-Pane Container
        self.subpanes_container = tk.Frame(content, bg=Colors.BG_DARK)
        self.subpanes_container.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        # Build each subpane
        self.pane_archive = self._build_archive_pane()
        self.pane_expertise = self._build_expertise_pane()
        self.pane_explorer = self._build_explorer_pane()
        self.pane_storage = self._build_storage_pane()
        self.pane_timeline = self._build_timeline_pane()

        self._switch_subpane("archive")

    # =========================================================================
    # Subpane 1: Archive Analysis
    # =========================================================================
    def _build_archive_pane(self) -> tk.Frame:
        pane = tk.Frame(self.subpanes_container, bg=Colors.BG_DARK)

        card = tk.Frame(pane, bg=Colors.SURFACE, highlightbackground=Colors.BORDER, highlightthickness=1, padx=16, pady=14)
        card.pack(fill="x", pady=(0, 12))

        tk.Label(card, text="Archive Member Enumeration & Compression Metrics", font=Fonts.HEADER_SMALL, bg=Colors.SURFACE, fg=Colors.TEXT_MAIN).pack(anchor="w", pady=(0, 8))

        cols = ("entry", "desc", "uncomp", "comp", "ratio", "records")
        self.arch_tree = ttk.Treeview(card, columns=cols, show="headings", height=6)
        self.arch_tree.heading("entry", text="Archive Entry")
        self.arch_tree.heading("desc", text="Description")
        self.arch_tree.heading("uncomp", text="Uncompressed")
        self.arch_tree.heading("comp", text="Compressed")
        self.arch_tree.heading("ratio", text="Ratio")
        self.arch_tree.heading("records", text="Records")

        self.arch_tree.column("entry", width=140)
        self.arch_tree.column("desc", width=220)
        self.arch_tree.column("uncomp", width=110, anchor="e")
        self.arch_tree.column("comp", width=110, anchor="e")
        self.arch_tree.column("ratio", width=80, anchor="e")
        self.arch_tree.column("records", width=80, anchor="center")
        self.arch_tree.pack(fill="x")

        # Cryptographic Integrity Verification Box
        integrity_card = tk.Frame(pane, bg=Colors.SURFACE, highlightbackground=Colors.BORDER, highlightthickness=1, padx=16, pady=14)
        integrity_card.pack(fill="x")

        tk.Label(integrity_card, text="Cryptographic Integrity Verification (SHA-256)", font=Fonts.HEADER_SMALL, bg=Colors.SURFACE, fg=Colors.TEXT_MAIN).pack(anchor="w", pady=(0, 6))
        self.integrity_lbl = tk.Label(integrity_card, text="Integrity status pending...", font=Fonts.CODE_SMALL, bg=Colors.SURFACE, fg=Colors.TEXT_MUTED, justify="left")
        self.integrity_lbl.pack(anchor="w")

        return pane

    # =========================================================================
    # Subpane 2: Expertise & Competence
    # =========================================================================
    def _build_expertise_pane(self) -> tk.Frame:
        pane = tk.Frame(self.subpanes_container, bg=Colors.BG_DARK)

        card = tk.Frame(pane, bg=Colors.SURFACE, highlightbackground=Colors.BORDER, highlightthickness=1, padx=16, pady=14)
        card.pack(fill="x")

        head = tk.Frame(card, bg=Colors.SURFACE)
        head.pack(fill="x", pady=(0, 10))

        tk.Label(head, text="Observed Activity vs Empirically Verified Competence", font=Fonts.HEADER_SMALL, bg=Colors.SURFACE, fg=Colors.TEXT_MAIN).pack(side="left")

        filter_row = tk.Frame(head, bg=Colors.SURFACE)
        filter_row.pack(side="right")

        self.exp_dim_buttons = {}
        for dim, name in [("domains", "Domains"), ("technologies", "Technologies"), ("frameworks", "Frameworks"), ("task_categories", "Categories")]:
            btn = ttk.Button(filter_row, text=name, style="SubTab.TButton", command=lambda d=dim: self._switch_expertise_dimension(d))
            btn.pack(side="left", padx=2)
            self.exp_dim_buttons[dim] = btn

        self.expertise_grid = tk.Frame(card, bg=Colors.SURFACE)
        self.expertise_grid.pack(fill="x", pady=(8, 0))

        return pane

    # =========================================================================
    # Subpane 3: Knowledge Explorer
    # =========================================================================
    def _build_explorer_pane(self) -> tk.Frame:
        pane = tk.Frame(self.subpanes_container, bg=Colors.BG_DARK)

        card = tk.Frame(pane, bg=Colors.SURFACE, highlightbackground=Colors.BORDER, highlightthickness=1, padx=16, pady=14)
        card.pack(fill="x")

        # Top Explorer Views Nav
        v_nav = tk.Frame(card, bg=Colors.SURFACE)
        v_nav.pack(fill="x", pady=(0, 10))

        self.explorer_view_buttons = {}
        for v_key, v_title in [
            ("lessons", "Lessons"),
            ("strategies", "Strategies"),
            ("projects", "Projects"),
            ("technologies", "Technologies"),
            ("preferences", "Preferences"),
            ("benchmarks", "Benchmarks"),
        ]:
            btn = ttk.Button(v_nav, text=v_title, style="SubTab.TButton", command=lambda k=v_key: self._switch_explorer_view(k))
            btn.pack(side="left", padx=2)
            self.explorer_view_buttons[v_key] = btn

        # Search & Filter bar
        filter_bar = tk.Frame(card, bg=Colors.SURFACE)
        filter_bar.pack(fill="x", pady=(0, 10))

        tk.Label(filter_bar, text="Search:", font=Fonts.SMALL_BOLD, bg=Colors.SURFACE, fg=Colors.TEXT_MUTED).pack(side="left", padx=(0, 6))
        self.search_entry = ttk.Entry(filter_bar, width=30)
        self.search_entry.pack(side="left", padx=(0, 12))
        self.search_entry.bind("<KeyRelease>", lambda e: self._filter_explorer())

        tk.Label(filter_bar, text="Scope:", font=Fonts.SMALL_BOLD, bg=Colors.SURFACE, fg=Colors.TEXT_MUTED).pack(side="left", padx=(0, 6))
        self.scope_filter = ttk.Combobox(filter_bar, values=["all", "global", "domain", "technology", "preferences", "project"], state="readonly", width=14)
        self.scope_filter.set("all")
        self.scope_filter.pack(side="left", padx=(0, 12))
        self.scope_filter.bind("<<ComboboxSelected>>", lambda e: self._filter_explorer())

        tk.Label(filter_bar, text="Status:", font=Fonts.SMALL_BOLD, bg=Colors.SURFACE, fg=Colors.TEXT_MUTED).pack(side="left", padx=(0, 6))
        self.status_filter = ttk.Combobox(filter_bar, values=["all", "verified", "candidate"], state="readonly", width=12)
        self.status_filter.set("all")
        self.status_filter.pack(side="left")
        self.status_filter.bind("<<ComboboxSelected>>", lambda e: self._filter_explorer())

        # Results Treeview
        cols = ("col1", "col2", "col3", "col4", "col5")
        self.explorer_tree = ttk.Treeview(card, columns=cols, show="headings", height=8)
        self.explorer_tree.heading("col1", text="Identifier / Title")
        self.explorer_tree.heading("col2", text="Scope / Domain")
        self.explorer_tree.heading("col3", text="Confidence / Score")
        self.explorer_tree.heading("col4", text="Evidence / Provenance")
        self.explorer_tree.heading("col5", text="Status")

        self.explorer_tree.column("col1", width=260)
        self.explorer_tree.column("col2", width=120)
        self.explorer_tree.column("col3", width=100, anchor="center")
        self.explorer_tree.column("col4", width=180)
        self.explorer_tree.column("col5", width=90, anchor="center")
        self.explorer_tree.pack(fill="x")
        self.explorer_tree.bind("<Double-1>", self._on_explorer_double_click)

        # Inspect button below explorer
        row_btn = tk.Frame(card, bg=Colors.SURFACE)
        row_btn.pack(fill="x", pady=(8, 0))
        ttk.Button(row_btn, text="View Record Details", command=self._inspect_selected_record).pack(side="right")

        return pane

    # =========================================================================
    # Subpane 4: Storage Analytics
    # =========================================================================
    def _build_storage_pane(self) -> tk.Frame:
        pane = tk.Frame(self.subpanes_container, bg=Colors.BG_DARK)

        card = tk.Frame(pane, bg=Colors.SURFACE, highlightbackground=Colors.BORDER, highlightthickness=1, padx=16, pady=14)
        card.pack(fill="x")

        tk.Label(card, text="Storage Footprint & Process Allocation", font=Fonts.HEADER_SMALL, bg=Colors.SURFACE, fg=Colors.TEXT_MAIN).pack(anchor="w", pady=(0, 10))

        # Metrics cards row
        s_metrics = tk.Frame(card, bg=Colors.SURFACE)
        s_metrics.pack(fill="x", pady=(0, 14))

        self.st_card_archive = MetricCard(s_metrics, label="Compressed .vxp", initial_value="0 B", width=130)
        self.st_card_archive.pack(side="left", padx=(0, 8), fill="x", expand=True)

        self.st_card_uncomp = MetricCard(s_metrics, label="Uncompressed", initial_value="0 B", width=130)
        self.st_card_uncomp.pack(side="left", padx=(0, 8), fill="x", expand=True)

        self.st_card_db = MetricCard(s_metrics, label="SQLite Database", initial_value="0 B", width=130)
        self.st_card_db.pack(side="left", padx=(0, 8), fill="x", expand=True)

        self.st_card_wal = MetricCard(s_metrics, label="SQLite WAL/SHM", initial_value="0 B", width=130)
        self.st_card_wal.pack(side="left", padx=(0, 8), fill="x", expand=True)

        self.st_card_ram = MetricCard(s_metrics, label="Process RAM (RSS)", initial_value="0 MB", width=130)
        self.st_card_ram.pack(side="left", fill="x", expand=True)

        # Storage breakdown table
        cols = ("comp", "size", "path", "note")
        self.storage_tree = ttk.Treeview(card, columns=cols, show="headings", height=5)
        self.storage_tree.heading("comp", text="Storage Component")
        self.storage_tree.heading("size", text="Measured Size")
        self.storage_tree.heading("path", text="Physical Path / Mechanism")
        self.storage_tree.heading("note", text="Optimization Note")

        self.storage_tree.column("comp", width=160)
        self.storage_tree.column("size", width=120, anchor="e")
        self.storage_tree.column("path", width=300)
        self.storage_tree.column("note", width=180)
        self.storage_tree.pack(fill="x")

        return pane

    # =========================================================================
    # Subpane 5: Version Diff & Timeline
    # =========================================================================
    def _build_timeline_pane(self) -> tk.Frame:
        pane = tk.Frame(self.subpanes_container, bg=Colors.BG_DARK)

        card = tk.Frame(pane, bg=Colors.SURFACE, highlightbackground=Colors.BORDER, highlightthickness=1, padx=16, pady=14)
        card.pack(fill="x", pady=(0, 12))

        tk.Label(card, text="Version Checkpoint Comparison", font=Fonts.HEADER_SMALL, bg=Colors.SURFACE, fg=Colors.TEXT_MAIN).pack(anchor="w", pady=(0, 8))

        diff_toolbar = tk.Frame(card, bg=Colors.SURFACE)
        diff_toolbar.pack(fill="x", pady=(0, 10))

        tk.Label(diff_toolbar, text="Compare Version A:", font=Fonts.SMALL_BOLD, bg=Colors.SURFACE, fg=Colors.TEXT_MUTED).pack(side="left", padx=(0, 6))
        self.ver_a_combo = ttk.Combobox(diff_toolbar, state="readonly", width=12)
        self.ver_a_combo.pack(side="left", padx=(0, 10))

        tk.Label(diff_toolbar, text="With Version B:", font=Fonts.SMALL_BOLD, bg=Colors.SURFACE, fg=Colors.TEXT_MUTED).pack(side="left", padx=(0, 6))
        self.ver_b_combo = ttk.Combobox(diff_toolbar, state="readonly", width=12)
        self.ver_b_combo.pack(side="left", padx=(0, 12))

        ttk.Button(diff_toolbar, text="Compare Checkpoints", command=self._run_version_diff).pack(side="left")

        self.diff_results_box = tk.Text(card, bg=Colors.BG_DARK, fg=Colors.TEXT_MAIN, font=Fonts.CODE_SMALL, relief="flat", padx=10, pady=10, height=6)
        self.diff_results_box.pack(fill="x")

        # Growth timeline list
        timeline_card = tk.Frame(pane, bg=Colors.SURFACE, highlightbackground=Colors.BORDER, highlightthickness=1, padx=16, pady=14)
        timeline_card.pack(fill="x")

        tk.Label(timeline_card, text="Expertise Growth & Checkpoint Timeline", font=Fonts.HEADER_SMALL, bg=Colors.SURFACE, fg=Colors.TEXT_MAIN).pack(anchor="w", pady=(0, 8))

        cols = ("version", "date", "lessons", "strategies", "bench", "msg")
        self.timeline_tree = ttk.Treeview(timeline_card, columns=cols, show="headings", height=5)
        self.timeline_tree.heading("version", text="Version")
        self.timeline_tree.heading("date", text="Created Date")
        self.timeline_tree.heading("lessons", text="Lessons")
        self.timeline_tree.heading("strategies", text="Strategies")
        self.timeline_tree.heading("bench", text="Benchmark Delta")
        self.timeline_tree.heading("msg", text="Message / Reason")

        self.timeline_tree.column("version", width=90, anchor="center")
        self.timeline_tree.column("date", width=130)
        self.timeline_tree.column("lessons", width=80, anchor="center")
        self.timeline_tree.column("strategies", width=80, anchor="center")
        self.timeline_tree.column("bench", width=120)
        self.timeline_tree.column("msg", width=260)
        self.timeline_tree.pack(fill="x")

        return pane

    # =========================================================================
    # Navigation & Actions
    # =========================================================================
    def _switch_subpane(self, target: str) -> None:
        self.active_subpane = target
        for k, btn in self.subtab_buttons.items():
            btn.configure(style="ActiveSubTab.TButton" if k == target else "SubTab.TButton")

        for p in [self.pane_archive, self.pane_expertise, self.pane_explorer, self.pane_storage, self.pane_timeline]:
            p.pack_forget()

        if target == "archive":
            self.pane_archive.pack(fill="x")
        elif target == "expertise":
            self.pane_expertise.pack(fill="x")
            self._render_expertise()
        elif target == "explorer":
            self.pane_explorer.pack(fill="x")
            self._filter_explorer()
        elif target == "storage":
            self.pane_storage.pack(fill="x")
            self._render_storage()
        elif target == "timeline":
            self.pane_timeline.pack(fill="x")
            self._render_timeline()

    def _switch_expertise_dimension(self, dim: str) -> None:
        self.active_dimension = dim
        for k, btn in self.exp_dim_buttons.items():
            btn.configure(style="ActiveSubTab.TButton" if k == dim else "SubTab.TButton")
        self._render_expertise()

    def _switch_explorer_view(self, view: str) -> None:
        self.active_explorer_view = view
        for k, btn in self.explorer_view_buttons.items():
            btn.configure(style="ActiveSubTab.TButton" if k == view else "SubTab.TButton")
        self._filter_explorer()

    def _on_profile_selected(self, event=None):
        name = self.profile_combo.get()
        if not name:
            return
        p = self.app.p_repo.get_by_name(name) or self.app.p_repo.get_by_id(name)
        if p:
            self.current_profile_id = p.profile_id
            self.custom_archive_path = None
            self.refresh()

    def _open_file_dialog(self):
        InspectFileDialog(self, on_inspect=self._inspect_custom_file)

    def _inspect_custom_file(self, path_str: str):
        self.custom_archive_path = Path(path_str)
        self.refresh()

    def _open_password_dialog(self):
        PasswordDialog(self, on_unlock=self._on_password_entered)

    def _on_password_entered(self, pwd: str):
        self.archive_password = pwd
        self.refresh()

    def _delete_profile(self):
        if not self.current_profile_id:
            return
        p = self.app.p_repo.get_by_id(self.current_profile_id)
        if not p:
            return

        ConfirmActionDialog(
            self,
            title="Delete Experience Profile",
            message=f"Are you sure you want to delete profile '{p.name}'? All internal experiences and lessons will be removed. External .vxp archives remain untouched.",
            on_confirm=lambda r: self._do_delete_profile(p.profile_id),
            destructive=True,
        )

    def _do_delete_profile(self, profile_id: str):
        self.app.inspector.delete_profile_safely(profile_id, confirm=True)
        self.current_profile_id = None
        self.app.refresh_all_views()

    # =========================================================================
    # Data Refresh & Rendering
    # =========================================================================
    def refresh(self) -> None:
        """Fetch inspection data using ProfileInspector."""
        inspector = self.app.inspector
        p_repo = self.app.p_repo

        # Populate combo with all stored profiles
        profiles = p_repo.list_all()
        profile_names = [p.name for p in profiles]
        self.profile_combo["values"] = profile_names

        # If custom archive file
        if self.custom_archive_path and self.custom_archive_path.is_file():
            self._render_custom_archive(self.custom_archive_path)
            return

        # Resolve active profile
        if not self.current_profile_id:
            active = p_repo.get_active()
            if active:
                self.current_profile_id = active.profile_id
            elif profiles:
                self.current_profile_id = profiles[0].profile_id

        if not self.current_profile_id:
            return

        summary = inspector.get_profile_summary(self.current_profile_id)
        if not summary:
            return

        self.profile_combo.set(summary.name)

        # Header metadata
        self.title_lbl.configure(text=summary.name)
        self.badge_ver.configure(text=f"v{summary.version}")
        self.badge_state.configure(text=summary.load_state.upper())
        self.badge_schema.configure(
            text=f"Schema v{summary.schema_version}",
            fg=Colors.TEXT_MUTED if summary.is_schema_supported else Colors.STATUS_RED,
        )
        is_integrity_valid = summary.is_schema_supported and summary.load_state != "CORRUPT"
        self.badge_integrity.configure(
            text="SHA-256 Valid" if is_integrity_valid else "Integrity Warning",
            fg=Colors.ACCENT_TEAL if is_integrity_valid else Colors.STATUS_RED,
        )
        self.desc_lbl.configure(text=summary.description or "No description provided.")
        self.meta_lbl.configure(text=f"📁 Archive: {summary.archive_path or 'Database-backed'} · 🕒 Last Modified: {summary.updated_at.strftime('%Y-%m-%d %H:%M')}")

        # High-level metric tiles
        self.tile_archive_size.set_value(f"{summary.file_size_bytes} B")
        self.tile_uncomp_size.set_value(f"{summary.uncompressed_size_bytes} B")
        self.tile_exps.set_value(str(summary.experience_count))
        self.tile_verified.set_value(str(summary.verified_lesson_count))
        self.tile_candidates.set_value(str(summary.candidate_lesson_count))
        self.tile_strategies.set_value(str(summary.strategy_count))
        self.tile_coverage.set_value(f"{summary.domain_coverage_pct}%")
        self.tile_coverage.set_hint(f"Domains: {', '.join(summary.domain_coverage) if summary.domain_coverage else 'None'}")

        # Render active subpane
        if self.active_subpane == "archive":
            self._render_archive(summary.profile_id)
        elif self.active_subpane == "expertise":
            self._render_expertise()
        elif self.active_subpane == "explorer":
            self._filter_explorer()
        elif self.active_subpane == "storage":
            self._render_storage()
        elif self.active_subpane == "timeline":
            self._render_timeline()

    def _render_archive(self, profile_id: str):
        for row in self.arch_tree.get_children():
            self.arch_tree.delete(row)

        profile = self.app.p_repo.get_by_id(profile_id)
        if not profile:
            return

        archive_path = self.app.config.exports_dir / f"{profile.name}.vxp"
        if not archive_path.is_file():
            archive_path = self.app.config.profiles_dir / f"{profile.name}.vxp"

        if archive_path.is_file():
            result = self.app.inspector.inspect_archive(archive_path, password=self.archive_password)
        else:
            # Package in memory to measure real entries
            lessons = self.app.l_repo.list_by_profile(profile.profile_id, active_only=False)
            strategies = self.app.s_repo.list_by_profile(profile.profile_id)
            benchmarks = self.app.b_repo.get_metrics(profile.profile_id) if self.app.b_repo else []
            package = ProfilePackage(
                manifest=profile,
                lessons=lessons,
                strategies=strategies,
                preferences={},
                benchmarks=benchmarks,
            )
            temp_export = self.app.config.exports_dir / f"{profile.name}.vxp"
            self.app.profile_mgr.archive_format.pack_to_vxp(package, temp_export)
            result = self.app.inspector.inspect_archive(temp_export, password=self.archive_password)

        if result.is_encrypted and not result.entries:
            self.btn_unlock.pack(side="left", padx=(0, 8))
            self.integrity_lbl.configure(text="🔒 Archive is encrypted using AES-256-GCM. Click Unlock above to inspect members.", fg=Colors.STATUS_YELLOW)
            return
        else:
            self.btn_unlock.pack_forget()

        for e in result.entries:
            rec_str = str(e.record_count) if e.record_count is not None else "-"
            self.arch_tree.insert(
                "",
                "end",
                values=(e.name, e.description, f"{e.uncompressed_bytes} B", f"{e.compressed_bytes} B", f"{e.compression_ratio_pct:.1f}%", rec_str),
            )

        status_text = "VALID SHA-256 INTEGRITY DIGEST" if result.integrity_verified else "INTEGRITY MISMATCH WARNING"
        color = Colors.STATUS_GREEN if result.integrity_verified else Colors.STATUS_RED
        self.integrity_lbl.configure(
            text=f"Status: {status_text}\nDigest: {result.integrity_checksum_expected or 'N/A'}",
            fg=color,
        )

    def _render_custom_archive(self, file_path: Path):
        self.title_lbl.configure(text=f"Archive: {file_path.name}")
        self.desc_lbl.configure(text=f"Custom file on disk: {file_path}")
        result = self.app.inspector.inspect_archive(file_path, password=self.archive_password)

        for row in self.arch_tree.get_children():
            self.arch_tree.delete(row)

        for e in result.entries:
            rec_str = str(e.record_count) if e.record_count is not None else "-"
            self.arch_tree.insert(
                "",
                "end",
                values=(e.name, e.description, f"{e.uncompressed_bytes} B", f"{e.compressed_bytes} B", f"{e.compression_ratio_pct:.1f}%", rec_str),
            )

        self.integrity_lbl.configure(
            text=f"Integrity Status: {'VALID SHA-256' if result.integrity_verified else 'INVALID'}\nExpected: {result.integrity_checksum_expected}",
            fg=Colors.STATUS_GREEN if result.integrity_verified else Colors.STATUS_RED,
        )

    def _render_expertise(self):
        for w in self.expertise_grid.winfo_children():
            w.destroy()

        if not self.current_profile_id:
            return

        analytics = self.app.inspector.calculate_expertise(self.current_profile_id)
        dim_data = getattr(analytics, self.active_dimension, [])

        if not dim_data:
            tk.Label(self.expertise_grid, text=f"No data available for dimension '{self.active_dimension}' yet.", font=Fonts.BODY, bg=Colors.SURFACE, fg=Colors.TEXT_MUTED).pack(anchor="w", pady=10)
            return

        # Render cards for each entry
        for idx, item in enumerate(dim_data):
            row_f = tk.Frame(self.expertise_grid, bg=Colors.BG_DARK, highlightbackground=Colors.BORDER, highlightthickness=1, padx=12, pady=10)
            row_f.pack(fill="x", pady=(0, 8))

            head = tk.Frame(row_f, bg=Colors.BG_DARK)
            head.pack(fill="x")
            tk.Label(head, text=item.name.upper(), font=Fonts.BODY_BOLD, bg=Colors.BG_DARK, fg=Colors.TEXT_MAIN).pack(side="left")

            tk.Label(
                head,
                text=f"Competence: {item.verified_competence_pct}%",
                font=Fonts.BODY_BOLD,
                bg=Colors.BG_DARK,
                fg=Colors.STATUS_GREEN if item.verified_competence_pct >= 70 else Colors.ACCENT_CYAN,
            ).pack(side="right")

            # Progress Bar for Verified Competence
            pb = ttk.Progressbar(row_f, orient="horizontal", mode="determinate", value=item.verified_competence_pct, style="Horizontal.TProgressbar")
            pb.pack(fill="x", pady=(4, 6))

            stats_txt = f"Observed Tasks: {item.observed_tasks_count} · Attempts: {item.attempt_count} · Successes: {item.success_count} · Verified Lessons: {item.verified_lesson_count}"
            tk.Label(row_f, text=stats_txt, font=Fonts.SMALL, bg=Colors.BG_DARK, fg=Colors.TEXT_MUTED).pack(anchor="w")

    def _filter_explorer(self):
        for row in self.explorer_tree.get_children():
            self.explorer_tree.delete(row)

        if not self.current_profile_id:
            return

        q = self.search_entry.get().strip()
        scope = self.scope_filter.get()
        status = self.status_filter.get()

        views_data = self.app.inspector.get_searchable_views(
            identifier=self.current_profile_id,
            query=q,
            scope=scope if scope != "all" else "",
            status=status if status != "all" else "",
        )

        records = views_data.get(self.active_explorer_view, [])

        if not records:
            self.explorer_tree.insert("", "end", values=("No matching records found.", "-", "-", "-", "-"))
            return

        for r in records:
            # Map fields based on record type
            if self.active_explorer_view == "lessons":
                scope_str = r.get("scope", "global").upper()
                score_str = f"{r.get('confidence', 0.0):.2f}"
                status_str = "VERIFIED" if r.get("is_active") else "INACTIVE"
                ev_str = f"{len(r.get('evidence_history', []))} verification events"
                self.explorer_tree.insert("", "end", iid=r.get("id"), values=(r.get("title", ""), scope_str, score_str, ev_str, status_str))

            elif self.active_explorer_view == "strategies":
                score_str = f"{r.get('bayesian_score', 0.0):.2f}"
                stats_str = f"Attempts: {r.get('attempts_count', 0)}, Succ: {r.get('success_count', 0)}"
                self.explorer_tree.insert("", "end", iid=r.get("id"), values=(r.get("name", ""), r.get("category", "general"), score_str, stats_str, "ACTIVE"))

            elif self.active_explorer_view == "benchmarks":
                self.explorer_tree.insert("", "end", iid=r.get("id"), values=(r.get("suite_name", ""), r.get("agent_mode", ""), f"{r.get('success_rate', 0):.1%}", f"{r.get('total_tasks', 0)} tasks", "RECORDED"))

            else:
                self.explorer_tree.insert("", "end", iid=str(r.get("name") or r.get("id")), values=(str(r.get("name") or r.get("id")), "-", "-", "-", "OK"))

    def _on_explorer_double_click(self, event):
        self._inspect_selected_record()

    def _inspect_selected_record(self):
        sel = self.explorer_tree.selection()
        if not sel:
            return
        rec_id = sel[0]

        if self.active_explorer_view == "lessons":
            lesson = self.app.l_repo.get_by_id(rec_id)
            if lesson:
                LessonDetailDialog(
                    self,
                    lesson=lesson,
                    on_modify=self._on_modify_lesson,
                    on_delete=self._on_delete_lesson,
                )

    def _on_modify_lesson(self, lesson_id: str, updates: Dict[str, Any], reason: str):
        self.app.inspector.modify_lesson_safely(lesson_id, updates=updates, confirm=True, reason=reason)
        self.refresh()

    def _on_delete_lesson(self, lesson_id: str, reason: str):
        self.app.inspector.delete_lesson_safely(lesson_id, confirm=True)
        self.refresh()

    def _render_storage(self):
        for row in self.storage_tree.get_children():
            self.storage_tree.delete(row)

        analytics = self.app.inspector.get_storage_analytics(self.current_profile_id)

        self.st_card_archive.set_value(f"{round(analytics.archive_size_bytes / 1024, 1)} KB")
        self.st_card_uncomp.set_value(f"{round(analytics.uncompressed_size_bytes / 1024, 1)} KB")
        self.st_card_db.set_value(f"{round(analytics.database_file_bytes / 1024, 1)} KB")
        self.st_card_wal.set_value(f"{round(analytics.wal_shm_bytes / 1024, 1)} KB")
        self.st_card_ram.set_value(f"{analytics.process_ram_rss_mb:.1f} MB")

        for row in analytics.breakdown_rows:
            self.storage_tree.insert(
                "",
                "end",
                values=(row.component, f"{round(row.size_bytes / 1024, 1)} KB", row.physical_path, row.optimization_note),
            )

    def _render_timeline(self):
        for row in self.timeline_tree.get_children():
            self.timeline_tree.delete(row)

        if not self.current_profile_id:
            return

        timeline = self.app.inspector.get_expertise_timeline(self.current_profile_id)
        versions = [t.version for t in timeline]

        self.ver_a_combo["values"] = versions
        self.ver_b_combo["values"] = versions
        if len(versions) >= 2:
            self.ver_a_combo.set(versions[-2])
            self.ver_b_combo.set(versions[-1])
        elif versions:
            self.ver_a_combo.set(versions[0])
            self.ver_b_combo.set(versions[0])

        for t in timeline:
            dt_str = t.created_at.strftime("%Y-%m-%d %H:%M")
            self.timeline_tree.insert(
                "",
                "end",
                values=(t.version, dt_str, str(t.lesson_count), str(t.strategy_count), t.benchmark_delta_summary, t.message),
            )

    def _run_version_diff(self):
        va = self.ver_a_combo.get()
        vb = self.ver_b_combo.get()
        if not va or not vb or not self.current_profile_id:
            return

        diff = self.app.inspector.compare_versions(self.current_profile_id, va, vb)
        self.diff_results_box.delete("1.0", tk.END)

        lines = [
            f"=== Checkpoint Difference: {va} -> {vb} ===",
            f"Additions: {len(diff.additions)} · Updates: {len(diff.updates)} · Removals: {len(diff.removals)}",
        ]
        if diff.benchmark_deltas:
            lines.append("Benchmark Deltas: " + json.dumps(diff.benchmark_deltas))
        self.diff_results_box.insert("1.0", "\n".join(lines))
