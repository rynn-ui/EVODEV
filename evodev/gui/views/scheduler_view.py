"""Persistent Background Scheduler view for managing local automation tasks."""

import json
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Optional

from evodev.gui.components.scrollable_frame import ScrollableFrame
from evodev.gui.theme import Colors, Fonts
from evodev.models.scheduler import JobType, ScheduledJob


class SchedulerView(tk.Frame):
    """Persistent local background scheduler inspection and job management pane."""

    def __init__(self, parent: tk.Widget, app: Any):
        super().__init__(parent, bg=Colors.BG_DARK)
        self.app = app
        self.selected_job: Optional[ScheduledJob] = None

        self.scroll = ScrollableFrame(self, bg=Colors.BG_DARK)
        self.scroll.pack(fill="both", expand=True)
        content = self.scroll.scrollable_content

        card = tk.Frame(content, bg=Colors.SURFACE, highlightbackground=Colors.BORDER, highlightthickness=1, padx=16, pady=14)
        card.pack(fill="both", expand=True, padx=16, pady=16)

        # Header & Actions
        head = tk.Frame(card, bg=Colors.SURFACE)
        head.pack(fill="x", pady=(0, 10))

        tk.Label(head, text="Persistent Local Background Scheduler", font=Fonts.HEADER_MEDIUM, bg=Colors.SURFACE, fg=Colors.TEXT_MAIN).pack(side="left")

        btn_row = tk.Frame(head, bg=Colors.SURFACE)
        btn_row.pack(side="right")
        ttk.Button(btn_row, text="+ Add Scheduled Job", style="Primary.TButton", command=self._open_new_job_dialog).pack(side="left", padx=(0, 6))
        ttk.Button(btn_row, text="▶️ Run Due Jobs", command=self._run_due_jobs).pack(side="left", padx=(0, 6))
        ttk.Button(btn_row, text="⚡ Run Now", command=self._run_selected_now).pack(side="left", padx=(0, 6))
        ttk.Button(btn_row, text="🗑️ Delete Job", style="Danger.TButton", command=self._delete_selected_job).pack(side="left")

        # Jobs Table
        cols = ("name", "type", "schedule", "enabled", "last_run", "next_run", "status")
        self.tree = ttk.Treeview(card, columns=cols, show="headings", height=10)
        self.tree.heading("name", text="Job Name")
        self.tree.heading("type", text="Job Type")
        self.tree.heading("schedule", text="Schedule")
        self.tree.heading("enabled", text="Enabled")
        self.tree.heading("last_run", text="Last Run")
        self.tree.heading("next_run", text="Next Run")
        self.tree.heading("status", text="Status")

        self.tree.column("name", width=220)
        self.tree.column("type", width=130, anchor="center")
        self.tree.column("schedule", width=100, anchor="center")
        self.tree.column("enabled", width=70, anchor="center")
        self.tree.column("last_run", width=130, anchor="center")
        self.tree.column("next_run", width=140, anchor="center")
        self.tree.column("status", width=90, anchor="center")
        self.tree.pack(fill="x")

        self.tree.bind("<<TreeviewSelect>>", self._on_select_job)

        # Job Details & Execution Logs
        detail_card = tk.Frame(card, bg=Colors.SURFACE_LIGHT, padx=12, pady=10, highlightbackground=Colors.BORDER, highlightthickness=1)
        detail_card.pack(fill="both", expand=True, pady=(12, 0))

        tk.Label(detail_card, text="Job Parameters & Diagnostics:", font=Fonts.SMALL_BOLD, bg=Colors.SURFACE_LIGHT, fg=Colors.TEXT_MUTED).pack(anchor="w", pady=(0, 6))

        self.detail_text = tk.Text(
            detail_card,
            bg=Colors.BG_DARK,
            fg=Colors.TEXT_MAIN,
            font=Fonts.CODE,
            height=7,
            relief="flat",
            padx=8,
            pady=8,
            wrap="word",
        )
        self.detail_text.pack(fill="both", expand=True)

    def refresh(self) -> None:
        for row in self.tree.get_children():
            self.tree.delete(row)

        jobs = self.app.sched_engine.list_jobs()
        for j in jobs:
            self.tree.insert(
                "",
                "end",
                iid=j.id,
                values=(
                    j.name,
                    j.job_type.value,
                    j.schedule_expr,
                    "YES" if j.enabled else "NO",
                    j.last_run_at.strftime("%Y-%m-%d %H:%M") if j.last_run_at else "-",
                    j.next_run_at.strftime("%Y-%m-%d %H:%M") if j.next_run_at else "-",
                    j.last_status,
                ),
            )

        if self.selected_job:
            updated = self.app.sched_repo.get_by_id(self.selected_job.id)
            if updated:
                self.selected_job = updated
                self._render_job_details()

    def _on_select_job(self, event=None) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        job_id = sel[0]
        self.selected_job = self.app.sched_repo.get_by_id(job_id)
        self._render_job_details()

    def _render_job_details(self) -> None:
        if not self.selected_job:
            self.detail_text.delete("1.0", "end")
            self.detail_text.insert("end", "// Select a scheduled job to inspect configuration and status.")
            return

        out = {
            "id": self.selected_job.id,
            "name": self.selected_job.name,
            "job_type": self.selected_job.job_type.value,
            "schedule": self.selected_job.schedule_expr,
            "enabled": self.selected_job.enabled,
            "last_status": self.selected_job.last_status,
            "last_run_at": self.selected_job.last_run_at.isoformat() if self.selected_job.last_run_at else None,
            "next_run_at": self.selected_job.next_run_at.isoformat() if self.selected_job.next_run_at else None,
            "parameters": self.selected_job.params,
        }
        self.detail_text.delete("1.0", "end")
        self.detail_text.insert("end", json.dumps(out, indent=2))

    def _open_new_job_dialog(self) -> None:
        dlg = tk.Toplevel(self.app.root)
        dlg.title("Add Scheduled Automation Job")
        dlg.geometry("460x320")
        dlg.configure(bg=Colors.BG_DARK)
        dlg.transient(self.app.root)
        dlg.grab_set()

        f = tk.Frame(dlg, bg=Colors.SURFACE, padx=16, pady=16)
        f.pack(fill="both", expand=True, padx=12, pady=12)

        tk.Label(f, text="Register Background Scheduled Job", font=Fonts.BODY_BOLD, bg=Colors.SURFACE, fg=Colors.TEXT_MAIN).pack(anchor="w", pady=(0, 10))

        tk.Label(f, text="Job Descriptive Name:", font=Fonts.SMALL_BOLD, bg=Colors.SURFACE, fg=Colors.TEXT_MUTED).pack(anchor="w")
        name_e = ttk.Entry(f)
        name_e.insert(0, "Daily Experience Hygiene")
        name_e.pack(fill="x", pady=(2, 8))

        tk.Label(f, text="Job Type:", font=Fonts.SMALL_BOLD, bg=Colors.SURFACE, fg=Colors.TEXT_MUTED).pack(anchor="w")
        type_cb = ttk.Combobox(f, values=[t.value for t in JobType], state="readonly")
        type_cb.set("stale_cleanup")
        type_cb.pack(fill="x", pady=(2, 8))

        tk.Label(f, text="Schedule (e.g. daily, hourly, every:2h, interval:3600):", font=Fonts.SMALL_BOLD, bg=Colors.SURFACE, fg=Colors.TEXT_MUTED).pack(anchor="w")
        sched_e = ttk.Entry(f)
        sched_e.insert(0, "daily")
        sched_e.pack(fill="x", pady=(2, 12))

        def _save():
            name = name_e.get().strip()
            jt = JobType(type_cb.get())
            sched_expr = sched_e.get().strip() or "daily"

            if not name:
                messagebox.showerror("Error", "Job name is required.", parent=dlg)
                return

            try:
                self.app.sched_engine.register_job(
                    name=name,
                    job_type=jt,
                    schedule_expr=sched_expr,
                )
                dlg.destroy()
                self.refresh()
                messagebox.showinfo("Registered", f"Scheduled '{name}'.", parent=self.app.root)
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=dlg)

        btn_row = tk.Frame(f, bg=Colors.SURFACE)
        btn_row.pack(fill="x")
        ttk.Button(btn_row, text="Cancel", command=dlg.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(btn_row, text="Register Job", style="Primary.TButton", command=_save).pack(side="right")

    def _run_due_jobs(self) -> None:
        results = self.app.sched_engine.run_pending()
        self.refresh()
        messagebox.showinfo("Scheduler", f"Executed {len(results)} due background tasks.", parent=self.app.root)

    def _run_selected_now(self) -> None:
        if not self.selected_job:
            return
        res = self.app.sched_engine.execute_job_now(self.selected_job.id)
        self.refresh()
        messagebox.showinfo("Executed", f"Execution finished with status '{res['status']}'.", parent=self.app.root)

    def _delete_selected_job(self) -> None:
        if not self.selected_job:
            return
        if messagebox.askyesno("Confirm Delete", f"Delete scheduled job '{self.selected_job.name}'?", parent=self.app.root):
            self.app.sched_engine.delete_job(self.selected_job.id)
            self.refresh()
