"""Specialist Delegation & Orchestration view for multi-agent workflows."""

import json
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Optional

from evodev.gui.components.scrollable_frame import ScrollableFrame
from evodev.gui.theme import Colors, Fonts
from evodev.models.orchestration import OrchestrationTask, SpecialistRole, TaskStatus


class OrchestrationView(tk.Frame):
    """Specialist delegation orchestration, task sequencing, and human approval pane."""

    def __init__(self, parent: tk.Widget, app: Any):
        super().__init__(parent, bg=Colors.BG_DARK)
        self.app = app
        self.selected_task: Optional[OrchestrationTask] = None

        self.scroll = ScrollableFrame(self, bg=Colors.BG_DARK)
        self.scroll.pack(fill="both", expand=True)
        content = self.scroll.scrollable_content

        card = tk.Frame(content, bg=Colors.SURFACE, highlightbackground=Colors.BORDER, highlightthickness=1, padx=16, pady=14)
        card.pack(fill="both", expand=True, padx=16, pady=16)

        # Header & Actions
        head = tk.Frame(card, bg=Colors.SURFACE)
        head.pack(fill="x", pady=(0, 10))

        tk.Label(head, text="Specialist Delegation & Orchestration", font=Fonts.HEADER_MEDIUM, bg=Colors.SURFACE, fg=Colors.TEXT_MAIN).pack(side="left")

        btn_row = tk.Frame(head, bg=Colors.SURFACE)
        btn_row.pack(side="right")
        ttk.Button(btn_row, text="+ Plan Specialist Task", style="Primary.TButton", command=self._open_new_task_dialog).pack(side="left", padx=(0, 6))
        ttk.Button(btn_row, text="✅ Approve Step", command=self._approve_selected_step).pack(side="left", padx=(0, 6))
        ttk.Button(btn_row, text="▶️ Execute Next", command=self._execute_next_step).pack(side="left", padx=(0, 6))
        ttk.Button(btn_row, text="⏹️ Cancel Task", command=self._cancel_task).pack(side="left")

        # Tasks Table
        tk.Label(card, text="Orchestrated Tasks:", font=Fonts.SMALL_BOLD, bg=Colors.SURFACE, fg=Colors.TEXT_MUTED).pack(anchor="w", pady=(0, 4))
        task_cols = ("title", "status", "project", "steps", "created_at")
        self.task_tree = ttk.Treeview(card, columns=task_cols, show="headings", height=5)
        self.task_tree.heading("title", text="Task Plan Goal")
        self.task_tree.heading("status", text="Status")
        self.task_tree.heading("project", text="Project")
        self.task_tree.heading("steps", text="Steps")
        self.task_tree.heading("created_at", text="Created At")

        self.task_tree.column("title", width=320)
        self.task_tree.column("status", width=110, anchor="center")
        self.task_tree.column("project", width=90, anchor="center")
        self.task_tree.column("steps", width=60, anchor="center")
        self.task_tree.column("created_at", width=150, anchor="center")
        self.task_tree.pack(fill="x")

        self.task_tree.bind("<<TreeviewSelect>>", self._on_select_task)

        # Sequenced Specialist Steps
        tk.Label(card, text="Sequenced Specialist Delegation Steps:", font=Fonts.SMALL_BOLD, bg=Colors.SURFACE, fg=Colors.TEXT_MUTED).pack(anchor="w", pady=(12, 4))
        step_cols = ("step", "role", "agent", "approval", "status", "desc")
        self.step_tree = ttk.Treeview(card, columns=step_cols, show="headings", height=6)
        self.step_tree.heading("step", text="#")
        self.step_tree.heading("role", text="Specialist Role")
        self.step_tree.heading("agent", text="Assigned Agent")
        self.step_tree.heading("approval", text="Approval Gate")
        self.step_tree.heading("status", text="Step Status")
        self.step_tree.heading("desc", text="Task Description")

        self.step_tree.column("step", width=30, anchor="center")
        self.step_tree.column("role", width=140)
        self.step_tree.column("agent", width=90, anchor="center")
        self.step_tree.column("approval", width=100, anchor="center")
        self.step_tree.column("status", width=110, anchor="center")
        self.step_tree.column("desc", width=320)
        self.step_tree.pack(fill="x")

        self.step_tree.bind("<<TreeviewSelect>>", self._on_select_step)

        # Output / Evidence Log
        self.output_card = tk.Frame(card, bg=Colors.SURFACE_LIGHT, padx=12, pady=10, highlightbackground=Colors.BORDER, highlightthickness=1)
        self.output_card.pack(fill="both", expand=True, pady=(12, 0))

        tk.Label(self.output_card, text="Specialist Execution Output & Evidence:", font=Fonts.SMALL_BOLD, bg=Colors.SURFACE_LIGHT, fg=Colors.TEXT_MUTED).pack(anchor="w", pady=(0, 6))

        self.output_text = tk.Text(
            self.output_card,
            bg=Colors.BG_DARK,
            fg=Colors.TEXT_MAIN,
            font=Fonts.CODE,
            height=6,
            relief="flat",
            padx=8,
            pady=8,
            wrap="word",
        )
        self.output_text.pack(fill="both", expand=True)

    def refresh(self) -> None:
        for row in self.task_tree.get_children():
            self.task_tree.delete(row)

        tasks = self.app.orchestrator.list_tasks()
        for t in tasks:
            self.task_tree.insert(
                "",
                "end",
                iid=t.id,
                values=(
                    t.title,
                    t.status.value.upper(),
                    t.project_id or "default",
                    f"{len(t.steps)}",
                    t.created_at.strftime("%Y-%m-%d %H:%M"),
                ),
            )

        if self.selected_task:
            updated = self.app.orchestrator.get_task(self.selected_task.id)
            if updated:
                self.selected_task = updated
                self._render_steps()

    def _on_select_task(self, event=None) -> None:
        sel = self.task_tree.selection()
        if not sel:
            return
        t_id = sel[0]
        self.selected_task = self.app.orchestrator.get_task(t_id)
        self._render_steps()

    def _render_steps(self) -> None:
        for row in self.step_tree.get_children():
            self.step_tree.delete(row)

        if not self.selected_task:
            return

        for idx, s in enumerate(self.selected_task.steps, 1):
            appr = "REQUIRED" if s.requires_approval else "AUTO"
            self.step_tree.insert(
                "",
                "end",
                iid=s.step_id,
                values=(
                    str(idx),
                    s.role.value.replace("_", " ").title(),
                    s.assigned_agent_id or "auto",
                    appr,
                    s.status.value.upper(),
                    s.task_description,
                ),
            )

    def _on_select_step(self, event=None) -> None:
        sel = self.step_tree.selection()
        if not sel or not self.selected_task:
            return
        s_id = sel[0]
        step = next((s for s in self.selected_task.steps if s.step_id == s_id), None)
        if not step:
            return

        self.output_text.delete("1.0", "end")
        out = {
            "step_id": step.step_id,
            "role": step.role.value,
            "agent": step.assigned_agent_id,
            "status": step.status.value,
            "inputs": step.inputs,
            "outputs": step.outputs,
            "evidence": step.evidence,
            "error": step.error,
        }
        self.output_text.insert("end", json.dumps(out, indent=2))

    def _open_new_task_dialog(self) -> None:
        dlg = tk.Toplevel(self.app.root)
        dlg.title("Plan Multi-Agent Specialist Task")
        dlg.geometry("500x380")
        dlg.configure(bg=Colors.BG_DARK)
        dlg.transient(self.app.root)
        dlg.grab_set()

        f = tk.Frame(dlg, bg=Colors.SURFACE, padx=16, pady=16)
        f.pack(fill="both", expand=True, padx=12, pady=12)

        tk.Label(f, text="Plan Specialist Delegation Workflow", font=Fonts.BODY_BOLD, bg=Colors.SURFACE, fg=Colors.TEXT_MAIN).pack(anchor="w", pady=(0, 10))

        tk.Label(f, text="Task Goal / Title:", font=Fonts.SMALL_BOLD, bg=Colors.SURFACE, fg=Colors.TEXT_MUTED).pack(anchor="w")
        title_e = ttk.Entry(f)
        title_e.insert(0, "Implement feature with test and security review")
        title_e.pack(fill="x", pady=(2, 8))

        tk.Label(f, text="Project ID:", font=Fonts.SMALL_BOLD, bg=Colors.SURFACE, fg=Colors.TEXT_MUTED).pack(anchor="w")
        proj_e = ttk.Entry(f)
        proj_e.insert(0, "default")
        proj_e.pack(fill="x", pady=(2, 8))

        tk.Label(f, text="Default Sequence:", font=Fonts.SMALL_BOLD, bg=Colors.SURFACE, fg=Colors.TEXT_MUTED).pack(anchor="w")
        seq_lbl = tk.Label(f, text="1. Implementer -> 2. Test Engineer -> 3. Security Reviewer (Approval Gate)", font=Fonts.SMALL, bg=Colors.SURFACE, fg=Colors.ACCENT_TEAL)
        seq_lbl.pack(anchor="w", pady=(2, 12))

        def _create():
            title = title_e.get().strip()
            proj = proj_e.get().strip() or "default"
            if not title:
                return

            steps = [
                {"role": SpecialistRole.IMPLEMENTER, "task_description": f"Write code changes for {title}", "requires_approval": False},
                {"role": SpecialistRole.TEST_ENGINEER, "task_description": "Add comprehensive unit and regression tests", "requires_approval": False},
                {"role": SpecialistRole.SECURITY_REVIEWER, "task_description": "Audit security vulnerabilities and secret leaks", "requires_approval": True},
            ]

            task = self.app.orchestrator.create_task_plan(
                title=title,
                project_id=proj,
                step_definitions=steps,
            )
            dlg.destroy()
            self.refresh()
            self.task_tree.selection_set(task.id)
            self._on_select_task()
            messagebox.showinfo("Created", f"Planned 3-stage specialist workflow for '{task.title}'.", parent=self.app.root)

        btn_row = tk.Frame(f, bg=Colors.SURFACE)
        btn_row.pack(fill="x")
        ttk.Button(btn_row, text="Cancel", command=dlg.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(btn_row, text="Create Task Plan", style="Primary.TButton", command=_create).pack(side="right")

    def _approve_selected_step(self) -> None:
        if not self.selected_task:
            return
        sel = self.step_tree.selection()
        if not sel:
            messagebox.showwarning("Notice", "Select a step waiting for approval.", parent=self.app.root)
            return
        step_id = sel[0]
        self.app.orchestrator.approve_step(self.selected_task.id, step_id)
        self.refresh()
        messagebox.showinfo("Approved", "Human approval granted for specialist step.", parent=self.app.root)

    def _execute_next_step(self) -> None:
        if not self.selected_task:
            return
        next_step = None
        for s in self.selected_task.steps:
            if s.status in (TaskStatus.PENDING, TaskStatus.WAITING_APPROVAL):
                next_step = s
                break

        if not next_step:
            messagebox.showinfo("Complete", "All steps in this task have finished.", parent=self.app.root)
            return

        if next_step.status == TaskStatus.WAITING_APPROVAL and next_step.requires_approval:
            messagebox.showwarning("Approval Gate", "This step requires explicit human approval before execution.", parent=self.app.root)
            return

        res = self.app.orchestrator.execute_step(self.selected_task.id, next_step.step_id)
        self.refresh()
        self.step_tree.selection_set(res.step_id)
        self._on_select_step()

    def _cancel_task(self) -> None:
        if not self.selected_task:
            return
        self.app.orchestrator.cancel_task(self.selected_task.id)
        self.refresh()
