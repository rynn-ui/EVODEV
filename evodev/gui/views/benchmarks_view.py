"""Benchmarks view providing empirical evaluation runner and metrics."""

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Optional

from evodev.evaluation.benchmark import BenchmarkSuiteRunner
from evodev.gui.components.metric_card import MetricCard
from evodev.gui.components.scrollable_frame import ScrollableFrame
from evodev.gui.theme import Colors, Fonts


class BenchmarksView(tk.Frame):
    """Empirical Benchmark Evaluations runner pane."""

    def __init__(self, parent: tk.Widget, app: Any):
        super().__init__(parent, bg=Colors.BG_DARK)
        self.app = app
        self._is_running = False

        self.scroll = ScrollableFrame(self, bg=Colors.BG_DARK)
        self.scroll.pack(fill="both", expand=True)
        content = self.scroll.scrollable_content

        card = tk.Frame(content, bg=Colors.SURFACE, highlightbackground=Colors.BORDER, highlightthickness=1, padx=16, pady=14)
        card.pack(fill="both", expand=True, padx=16, pady=16)

        # Header & Controls
        head = tk.Frame(card, bg=Colors.SURFACE)
        head.pack(fill="x", pady=(0, 14))

        tk.Label(head, text="Empirical Benchmark Evaluations", font=Fonts.HEADER_MEDIUM, bg=Colors.SURFACE, fg=Colors.TEXT_MAIN).pack(side="left")

        controls = tk.Frame(head, bg=Colors.SURFACE)
        controls.pack(side="right")

        tk.Label(controls, text="Suite:", font=Fonts.SMALL_BOLD, bg=Colors.SURFACE, fg=Colors.TEXT_MUTED).pack(side="left", padx=(0, 4))
        self.suite_cb = ttk.Combobox(controls, values=["standard_dev_challenges"], state="readonly", width=22)
        self.suite_cb.set("standard_dev_challenges")
        self.suite_cb.pack(side="left", padx=(0, 10))

        tk.Label(controls, text="Mode:", font=Fonts.SMALL_BOLD, bg=Colors.SURFACE, fg=Colors.TEXT_MUTED).pack(side="left", padx=(0, 4))
        self.mode_cb = ttk.Combobox(controls, values=["evodev_experienced", "base_agent"], state="readonly", width=18)
        self.mode_cb.set("evodev_experienced")
        self.mode_cb.pack(side="left", padx=(0, 12))

        self.btn_run = ttk.Button(controls, text="▶ Run Benchmark Suite", style="Primary.TButton", command=self._start_benchmark)
        self.btn_run.pack(side="left")

        # Running status banner
        self.status_lbl = tk.Label(card, text="", font=Fonts.BODY_BOLD, bg=Colors.SURFACE, fg=Colors.ACCENT_CYAN)
        self.status_lbl.pack(anchor="w", pady=(0, 10))

        # Result KPI tiles (2 rows of 4)
        self.tiles_frame_1 = tk.Frame(card, bg=Colors.SURFACE)
        self.tiles_frame_1.pack(fill="x", pady=(0, 10))

        self.tile_total = MetricCard(self.tiles_frame_1, label="Total Tasks", initial_value="0", hint="Challenges evaluated")
        self.tile_total.pack(side="left", padx=(0, 10), fill="x", expand=True)

        self.tile_passed = MetricCard(self.tiles_frame_1, label="Passed Tasks", initial_value="0", hint="Successfully solved", value_color=Colors.STATUS_GREEN)
        self.tile_passed.pack(side="left", padx=(0, 10), fill="x", expand=True)

        self.tile_failed = MetricCard(self.tiles_frame_1, label="Failed Tasks", initial_value="0", hint="Unresolved challenges", value_color=Colors.STATUS_RED)
        self.tile_failed.pack(side="left", padx=(0, 10), fill="x", expand=True)

        self.tile_regressed = MetricCard(self.tiles_frame_1, label="Regressions", initial_value="0", hint="Breaking regressions", value_color=Colors.STATUS_YELLOW)
        self.tile_regressed.pack(side="left", fill="x", expand=True)

        self.tiles_frame_2 = tk.Frame(card, bg=Colors.SURFACE)
        self.tiles_frame_2.pack(fill="x", pady=(0, 14))

        self.tile_success_rate = MetricCard(self.tiles_frame_2, label="Success Rate", initial_value="0%", hint="Pass percentage", value_color=Colors.STATUS_GREEN)
        self.tile_success_rate.pack(side="left", padx=(0, 10), fill="x", expand=True)

        self.tile_regression_rate = MetricCard(self.tiles_frame_2, label="Regression Rate", initial_value="0%", hint="Regression percentage", value_color=Colors.STATUS_YELLOW)
        self.tile_regression_rate.pack(side="left", padx=(0, 10), fill="x", expand=True)

        self.tile_error_freq = MetricCard(self.tiles_frame_2, label="Repeated Errors", initial_value="0%", hint="Recurring mistake freq")
        self.tile_error_freq.pack(side="left", padx=(0, 10), fill="x", expand=True)

        self.tile_avg_duration = MetricCard(self.tiles_frame_2, label="Avg Duration", initial_value="0.00s", hint="Execution latency")
        self.tile_avg_duration.pack(side="left", fill="x", expand=True)

        # Historical benchmark table
        tk.Label(card, text="Historical Benchmark Runs", font=Fonts.HEADER_SMALL, bg=Colors.SURFACE, fg=Colors.TEXT_MAIN).pack(anchor="w", pady=(6, 8))

        cols = ("date", "suite", "mode", "tasks", "success", "regression", "duration")
        self.hist_tree = ttk.Treeview(card, columns=cols, show="headings", height=5)
        self.hist_tree.heading("date", text="Executed Date")
        self.hist_tree.heading("suite", text="Suite")
        self.hist_tree.heading("mode", text="Agent Mode")
        self.hist_tree.heading("tasks", text="Tasks")
        self.hist_tree.heading("success", text="Success Rate")
        self.hist_tree.heading("regression", text="Regression Rate")
        self.hist_tree.heading("duration", text="Avg Duration")

        self.hist_tree.column("date", width=140)
        self.hist_tree.column("suite", width=180)
        self.hist_tree.column("mode", width=150)
        self.hist_tree.column("tasks", width=70, anchor="center")
        self.hist_tree.column("success", width=90, anchor="center")
        self.hist_tree.column("regression", width=100, anchor="center")
        self.hist_tree.column("duration", width=100, anchor="center")
        self.hist_tree.pack(fill="x")

    def _start_benchmark(self) -> None:
        if self._is_running:
            return

        self._is_running = True
        self.btn_run.configure(state="disabled")
        suite = self.suite_cb.get()
        mode = self.mode_cb.get()
        self.status_lbl.configure(text=f"⏳ Running benchmark suite '{suite}' in mode '{mode}'... Please wait.")

        active = self.app.p_repo.get_active()
        profile_id = active.profile_id if active else "default"

        def _run_worker():
            runner = BenchmarkSuiteRunner(self.app.engine, self.app.b_repo)
            return runner.run_suite(suite_name=suite, profile_id=profile_id, agent_mode=mode)

        def _on_success(metrics):
            self.tile_total.set_value(str(metrics.total_tasks))
            self.tile_passed.set_value(str(metrics.passed_tasks))
            self.tile_failed.set_value(str(metrics.failed_tasks))
            self.tile_regressed.set_value(str(metrics.regressed_tasks))
            self.tile_success_rate.set_value(f"{metrics.success_rate:.1%}")
            self.tile_regression_rate.set_value(f"{metrics.regression_rate:.1%}")
            self.tile_error_freq.set_value(f"{metrics.repeated_error_frequency:.1%}")
            self.tile_avg_duration.set_value(f"{metrics.avg_duration_seconds:.4f}s")
            self.status_lbl.configure(text=f"✓ Benchmark completed! Success rate: {metrics.success_rate:.1%}")
            self.refresh()

        def _on_error(exc):
            self.status_lbl.configure(text=f"⚠️ Benchmark run failed: {exc}")
            messagebox.showerror("Benchmark Error", str(exc), parent=self)

        def _on_finish():
            self._is_running = False
            self.btn_run.configure(state="normal")

        self.app.worker_pool.run_async(
            task_fn=_run_worker,
            on_success=_on_success,
            on_error=_on_error,
            on_finish=_on_finish,
        )

    def refresh(self) -> None:
        for row in self.hist_tree.get_children():
            self.hist_tree.delete(row)

        active = self.app.p_repo.get_active()
        profile_id = active.profile_id if active else "default"

        metrics_list = self.app.b_repo.get_metrics(profile_id)
        if not metrics_list:
            self.hist_tree.insert("", "end", values=("-", "No benchmark records in profile yet.", "-", "-", "-", "-", "-"))
            return

        for m in sorted(metrics_list, key=lambda x: x.timestamp, reverse=True):
            dt_str = m.timestamp.strftime("%Y-%m-%d %H:%M")
            self.hist_tree.insert(
                "",
                "end",
                values=(dt_str, m.suite_name, m.agent_mode, str(m.total_tasks), f"{m.success_rate:.1%}", f"{m.regression_rate:.1%}", f"{m.avg_duration_seconds:.4f}s"),
            )
