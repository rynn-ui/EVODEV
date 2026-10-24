"""Experiences view displaying development task history and outcomes."""

import tkinter as tk
from tkinter import ttk
from typing import Any

from evodev.gui.components.scrollable_frame import ScrollableFrame
from evodev.gui.theme import Colors, Fonts


class ExperiencesView(tk.Frame):
    """Historical development tasks and experience log pane."""

    def __init__(self, parent: tk.Widget, app: Any):
        super().__init__(parent, bg=Colors.BG_DARK)
        self.app = app

        self.scroll = ScrollableFrame(self, bg=Colors.BG_DARK)
        self.scroll.pack(fill="both", expand=True)
        content = self.scroll.scrollable_content

        card = tk.Frame(content, bg=Colors.SURFACE, highlightbackground=Colors.BORDER, highlightthickness=1, padx=16, pady=14)
        card.pack(fill="both", expand=True, padx=16, pady=16)

        tk.Label(card, text="Historical Development Experiences", font=Fonts.HEADER_MEDIUM, bg=Colors.SURFACE, fg=Colors.TEXT_MAIN).pack(anchor="w")
        tk.Label(
            card,
            text="Completed coding tasks, attempted strategies, verification evidence, and outcome signals.",
            font=Fonts.SMALL,
            bg=Colors.SURFACE,
            fg=Colors.TEXT_MUTED,
        ).pack(anchor="w", pady=(2, 12))

        cols = ("id", "project", "problem", "outcome", "verified", "strategies", "date")
        self.tree = ttk.Treeview(card, columns=cols, show="headings", height=10)
        self.tree.heading("id", text="Task ID")
        self.tree.heading("project", text="Project")
        self.tree.heading("problem", text="Initial Problem")
        self.tree.heading("outcome", text="Outcome")
        self.tree.heading("verified", text="Verified")
        self.tree.heading("strategies", text="Strategies Attempted")
        self.tree.heading("date", text="Recorded At")

        self.tree.column("id", width=80, anchor="center")
        self.tree.column("project", width=120)
        self.tree.column("problem", width=260)
        self.tree.column("outcome", width=80, anchor="center")
        self.tree.column("verified", width=70, anchor="center")
        self.tree.column("strategies", width=180)
        self.tree.column("date", width=130)
        self.tree.pack(fill="x", pady=(0, 12))

        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        # Selected Record Detail Box
        self.detail_card = tk.Frame(card, bg=Colors.BG_DARK, highlightbackground=Colors.BORDER, highlightthickness=1, padx=12, pady=10)
        self.detail_card.pack(fill="both", expand=True)

        tk.Label(self.detail_card, text="Experience Record Detail", font=Fonts.BODY_BOLD, bg=Colors.BG_DARK, fg=Colors.ACCENT_CYAN).pack(anchor="w")
        self.detail_text = tk.Text(self.detail_card, bg=Colors.BG_DARK, fg=Colors.TEXT_MAIN, font=Fonts.CODE_SMALL, relief="flat", padx=6, pady=6, height=8, wrap="word")
        self.detail_text.pack(fill="both", expand=True, pady=(4, 0))

    def refresh(self) -> None:
        for row in self.tree.get_children():
            self.tree.delete(row)
        self.detail_text.delete("1.0", tk.END)

        active = self.app.p_repo.get_active()
        p_id = active.profile_id if active else "default"

        exps = self.app.e_repo.list_by_profile(p_id, limit=50)

        if not exps:
            self.tree.insert("", "end", values=("-", "-", "No experiences recorded in this profile yet.", "-", "-", "-", "-"))
            return

        for r in exps:
            is_ver = "✓" if r.verification and r.verification.passed else "✗"
            strats_str = ", ".join(r.strategies_attempted) if r.strategies_attempted else "None"
            dt_str = r.created_at.strftime("%Y-%m-%d %H:%M")
            self.tree.insert(
                "",
                "end",
                iid=r.id,
                values=(r.task_id[:10] if r.task_id else r.id[:8], r.project_id, r.initial_problem[:60], r.outcome.upper(), is_ver, strats_str, dt_str),
            )

    def _on_select(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        exp_id = sel[0]
        rec = self.app.e_repo.get_by_id(exp_id)
        if not rec:
            return

        self.detail_text.delete("1.0", tk.END)
        lines = [
            f"ID: {rec.id} (Task: {rec.task_id}, Session: {rec.session_id})",
            f"Project: {rec.project_id} · Domain: {rec.domain} · Languages: {', '.join(rec.languages)}",
            f"Problem: {rec.initial_problem}",
            f"Outcome: {rec.outcome.upper()}",
            f"Strategies Attempted: {', '.join(rec.strategies_attempted)}",
        ]
        if rec.verification:
            lines.append(f"Verification: Passed={rec.verification.passed} (Score={rec.verification.confidence_score:.2f}) [{rec.verification.verification_type}] {rec.verification.evidence_snippet}")
        if rec.errors_observed:
            lines.append("Errors Observed:")
            for err in rec.errors_observed:
                lines.append(f"  • {err}")
        if rec.file_changes:
            lines.append(f"Changed Files: {', '.join(rec.file_changes)}")

        self.detail_text.insert("1.0", "\n".join(lines))
