"""Overview & telemetry view displaying runtime health, knowledge counts, and connectors."""

from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Dict, List, Optional

from evodev.gui.components.metric_card import MetricCard
from evodev.gui.components.scrollable_frame import ScrollableFrame
from evodev.gui.theme import Colors, Fonts


class OverviewView(tk.Frame):
    """System Overview & Telemetry pane."""

    def __init__(self, parent: tk.Widget, app: Any):
        super().__init__(parent, bg=Colors.BG_DARK)
        self.app = app

        # Scrollable container
        self.scroll = ScrollableFrame(self, bg=Colors.BG_DARK)
        self.scroll.pack(fill="both", expand=True)
        content = self.scroll.scrollable_content

        # 1. Quick Actions Bar
        actions_bar = tk.Frame(content, bg=Colors.SURFACE, highlightbackground=Colors.BORDER, highlightthickness=1, padx=16, pady=12)
        actions_bar.pack(fill="x", padx=16, pady=(12, 6))

        tk.Label(actions_bar, text="⚡ Quick Actions:", font=Fonts.BODY_BOLD, bg=Colors.SURFACE, fg=Colors.ACCENT_CYAN).pack(side="left", padx=(0, 12))

        ttk.Button(
            actions_bar,
            text="🚀 Open OpenCode",
            style="Launch.TButton",
            command=self._quick_launch_opencode,
        ).pack(side="left", padx=(0, 8))

        ttk.Button(
            actions_bar,
            text="🔌 Agent Connectors Hub",
            style="Success.TButton",
            command=lambda: self.app.switch_view("connectors"),
        ).pack(side="left", padx=(0, 8))

        ttk.Button(
            actions_bar,
            text="🛡️ Safe Checkpoint",
            command=lambda: self.app.switch_view("checkpoints"),
        ).pack(side="left", padx=(0, 8))

        ttk.Button(
            actions_bar,
            text="💡 View Verified Lessons",
            command=lambda: self.app.switch_view("lessons"),
        ).pack(side="left")

        # 2. Metric Cards Grid
        metrics_container = tk.Frame(content, bg=Colors.BG_DARK, pady=6)
        metrics_container.pack(fill="x", padx=16)

        self.card_lessons = MetricCard(
            metrics_container,
            label="Active Lessons",
            initial_value="0",
            hint="Promoted across scopes",
            value_color=Colors.STATUS_GREEN,
        )
        self.card_lessons.pack(side="left", padx=(0, 12), fill="x", expand=True)

        self.card_strategies = MetricCard(
            metrics_container,
            label="Tracked Strategies",
            initial_value="0",
            hint="Empirical Bayesian scored",
            value_color=Colors.ACCENT_CYAN,
        )
        self.card_strategies.pack(side="left", padx=(0, 12), fill="x", expand=True)

        self.card_experiences = MetricCard(
            metrics_container,
            label="Recorded Experiences",
            initial_value="0",
            hint="Completed developer tasks",
            value_color=Colors.ACCENT_TEAL,
        )
        self.card_experiences.pack(side="left", padx=(0, 12), fill="x", expand=True)

        self.card_db = MetricCard(
            metrics_container,
            label="Database Footprint",
            initial_value="0 KB",
            hint="Local SQLite WAL storage",
            value_color=Colors.TEXT_MAIN,
        )
        self.card_db.pack(side="left", fill="x", expand=True)

        # 3. Agent Integration Status Grid
        conn_sec = tk.Frame(content, bg=Colors.SURFACE, highlightbackground=Colors.BORDER, highlightthickness=1, padx=16, pady=14)
        conn_sec.pack(fill="x", padx=16, pady=(10, 12))

        conn_head = tk.Frame(conn_sec, bg=Colors.SURFACE)
        conn_head.pack(fill="x", pady=(0, 10))
        tk.Label(conn_head, text="Connected AI Coding Agents", font=Fonts.HEADER_SMALL, bg=Colors.SURFACE, fg=Colors.TEXT_MAIN).pack(side="left")
        ttk.Button(conn_head, text="Manage Connectors →", command=lambda: self.app.switch_view("connectors")).pack(side="right")

        self.conn_cards_frame = tk.Frame(conn_sec, bg=Colors.SURFACE)
        self.conn_cards_frame.pack(fill="x")

        # 4. Recent Verified Lessons Section
        lessons_sec = tk.Frame(content, bg=Colors.SURFACE, highlightbackground=Colors.BORDER, highlightthickness=1, padx=16, pady=14)
        lessons_sec.pack(fill="x", padx=16, pady=(0, 16))

        sec_head = tk.Frame(lessons_sec, bg=Colors.SURFACE)
        sec_head.pack(fill="x", pady=(0, 10))
        tk.Label(sec_head, text="Recent Verified Lessons", font=Fonts.HEADER_SMALL, bg=Colors.SURFACE, fg=Colors.TEXT_MAIN).pack(side="left")
        tk.Label(sec_head, text="LIVE MEMORY", font=Fonts.SMALL_BOLD, bg=Colors.SURFACE_LIGHT, fg=Colors.ACCENT_TEAL, padx=6, pady=2).pack(side="right")

        cols = ("title", "strategy", "scope", "confidence")
        self.lessons_tree = ttk.Treeview(lessons_sec, columns=cols, show="headings", height=5)
        self.lessons_tree.heading("title", text="Title & Trigger")
        self.lessons_tree.heading("strategy", text="Recommended Strategy")
        self.lessons_tree.heading("scope", text="Scope")
        self.lessons_tree.heading("confidence", text="Confidence")

        self.lessons_tree.column("title", width=260)
        self.lessons_tree.column("strategy", width=280)
        self.lessons_tree.column("scope", width=100, anchor="center")
        self.lessons_tree.column("confidence", width=90, anchor="center")
        self.lessons_tree.pack(fill="x")

    def _quick_launch_opencode(self) -> None:
        """Quick launch OpenCode terminal in current directory."""
        target_dir = Path.cwd().resolve()
        res = self.app.connector_manager.launch_agent("opencode", target_dir)
        if not res.get("success"):
            messagebox.showwarning("OpenCode Launch", res.get("message", "Unable to launch OpenCode."), parent=self)

    def refresh(self) -> None:
        """Fetch real status data from EvoDev core services and update UI."""
        config = self.app.config
        p_repo = self.app.p_repo
        l_repo = self.app.l_repo
        s_repo = self.app.s_repo
        e_repo = self.app.e_repo

        active = p_repo.get_active()
        p_id = active.profile_id if active else "default"

        # 1. Update stats
        lessons_cnt = l_repo.count_by_profile(p_id)
        strat_cnt = getattr(s_repo, "count_by_profile", lambda p: len(s_repo.list_by_profile(p)))(p_id)
        exp_cnt = e_repo.count_by_profile(p_id)

        db_size_kb = 0.0
        if config.db_path.is_file():
            db_size_kb = round(config.db_path.stat().st_size / 1024, 1)

        self.card_lessons.set_value(str(lessons_cnt))
        self.card_strategies.set_value(str(strat_cnt))
        self.card_experiences.set_value(str(exp_cnt))
        self.card_db.set_value(f"{db_size_kb} KB")

        # 2. Update Recent Lessons
        for row in self.lessons_tree.get_children():
            self.lessons_tree.delete(row)

        all_lessons = l_repo.list_by_profile(p_id, active_only=True)
        recent_lessons = sorted(all_lessons, key=lambda x: x.updated_at, reverse=True)[:5]

        if not recent_lessons:
            self.lessons_tree.insert("", "end", values=("No verified lessons recorded yet in active profile.", "-", "-", "-"))
        else:
            for l in recent_lessons:
                scope_str = l.scope.value.upper() if hasattr(l.scope, "value") else str(l.scope).upper()
                strat_short = (l.recommended_strategy[:50] + "...") if len(l.recommended_strategy) > 50 else l.recommended_strategy
                self.lessons_tree.insert(
                    "",
                    "end",
                    values=(l.title, strat_short, scope_str, f"{l.confidence:.2f}"),
                )

        # 3. Update Connector Cards asynchronously to ensure zero UI freeze
        if hasattr(self.app, "worker_pool") and self.app.worker_pool and not self.app.worker_pool._is_shutdown:
            self.app.worker_pool.run_async(
                task_fn=self.app.connector_manager.get_diagnostics,
                on_success=self._render_connector_cards,
            )
        else:
            self._render_connector_cards(self.app.connector_manager.get_diagnostics())

    def _render_connector_cards(self, connectors_info: List[Dict[str, Any]]) -> None:
        """Safely render connector cards on Tkinter main thread."""
        try:
            if not self.winfo_exists() or not self.conn_cards_frame.winfo_exists():
                return
        except Exception:
            return

        for widget in self.conn_cards_frame.winfo_children():
            widget.destroy()

        for idx, conn in enumerate(connectors_info):
            card = tk.Frame(
                self.conn_cards_frame,
                bg=Colors.BG_DARK,
                highlightbackground=Colors.BORDER,
                highlightthickness=1,
                padx=12,
                pady=10,
            )
            card.pack(side="left", fill="x", expand=True, padx=(0 if idx == 0 else 8, 0))

            header = tk.Frame(card, bg=Colors.BG_DARK)
            header.pack(fill="x")
            tk.Label(header, text=conn["agent_name"].split()[0], font=Fonts.BODY_BOLD, bg=Colors.BG_DARK, fg=Colors.TEXT_MAIN).pack(side="left")

            status_color = Colors.STATUS_GREEN if conn["is_available"] else Colors.TEXT_DIM
            status_text = "READY" if conn["is_available"] else "STANDBY"
            tk.Label(
                header,
                text=status_text,
                font=Fonts.SMALL_BOLD,
                bg=Colors.SURFACE_LIGHT,
                fg=status_color,
                padx=5,
                pady=1,
            ).pack(side="right")

            tk.Label(
                card,
                text=conn["description"],
                font=Fonts.SMALL,
                bg=Colors.BG_DARK,
                fg=Colors.TEXT_MUTED,
                wraplength=170,
                justify="left",
            ).pack(anchor="w", pady=(4, 6))

            # Small Launch or Setup Button
            act_row = tk.Frame(card, bg=Colors.BG_DARK)
            act_row.pack(fill="x")

            aid = conn["adapter_id"]
            if conn["is_available"]:
                ttk.Button(
                    act_row,
                    text="🚀 Launch",
                    style="Launch.TButton",
                    command=lambda a=aid: self._launch_agent_from_overview(a),
                ).pack(side="left", fill="x", expand=True)
            else:
                ttk.Button(
                    act_row,
                    text="Configure",
                    command=lambda: self.app.switch_view("connectors"),
                ).pack(side="left", fill="x", expand=True)

    def _launch_agent_from_overview(self, adapter_id: str) -> None:
        target_dir = Path.cwd().resolve()
        res = self.app.connector_manager.launch_agent(adapter_id, target_dir)
        if not res.get("success"):
            messagebox.showwarning("Agent Launch", res.get("message", "Unable to launch."), parent=self)
