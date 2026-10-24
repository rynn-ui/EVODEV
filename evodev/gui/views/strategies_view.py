"""Strategies view displaying empirical Bayesian scoring ledger."""

import tkinter as tk
from tkinter import ttk
from typing import Any

from evodev.gui.components.scrollable_frame import ScrollableFrame
from evodev.gui.theme import Colors, Fonts


class StrategiesView(tk.Frame):
    """Strategy statistics and Bayesian performance ledger pane."""

    def __init__(self, parent: tk.Widget, app: Any):
        super().__init__(parent, bg=Colors.BG_DARK)
        self.app = app

        self.scroll = ScrollableFrame(self, bg=Colors.BG_DARK)
        self.scroll.pack(fill="both", expand=True)
        content = self.scroll.scrollable_content

        card = tk.Frame(content, bg=Colors.SURFACE, highlightbackground=Colors.BORDER, highlightthickness=1, padx=16, pady=14)
        card.pack(fill="both", expand=True, padx=16, pady=16)

        tk.Label(card, text="Strategy Performance Ledger", font=Fonts.HEADER_MEDIUM, bg=Colors.SURFACE, fg=Colors.TEXT_MAIN).pack(anchor="w")
        tk.Label(
            card,
            text="Bayesian expected success rates accounting for attempts, verified outcomes, and regressions.",
            font=Fonts.SMALL,
            bg=Colors.SURFACE,
            fg=Colors.TEXT_MUTED,
        ).pack(anchor="w", pady=(2, 12))

        cols = ("name", "category", "attempts", "successes", "regressions", "score")
        self.tree = ttk.Treeview(card, columns=cols, show="headings", height=15)
        self.tree.heading("name", text="Strategy Name")
        self.tree.heading("category", text="Category / Domain")
        self.tree.heading("attempts", text="Attempts")
        self.tree.heading("successes", text="Successes")
        self.tree.heading("regressions", text="Regressions")
        self.tree.heading("score", text="Bayesian Score")

        self.tree.column("name", width=280)
        self.tree.column("category", width=140)
        self.tree.column("attempts", width=90, anchor="center")
        self.tree.column("successes", width=90, anchor="center")
        self.tree.column("regressions", width=90, anchor="center")
        self.tree.column("score", width=110, anchor="center")
        self.tree.pack(fill="both", expand=True)

    def refresh(self) -> None:
        for row in self.tree.get_children():
            self.tree.delete(row)

        active = self.app.p_repo.get_active()
        p_id = active.profile_id if active else "default"

        strats = self.app.s_repo.list_by_profile(p_id)
        # Sort descending by Bayesian score
        sorted_strats = sorted(strats, key=lambda x: x.bayesian_score, reverse=True)

        if not sorted_strats:
            self.tree.insert("", "end", values=("No strategies recorded yet in this profile.", "-", "-", "-", "-", "-"))
            return

        for s in sorted_strats:
            score_str = f"{s.bayesian_score:.2f}"
            self.tree.insert(
                "",
                "end",
                values=(s.name, s.category, str(s.attempts_count), str(s.success_count), str(s.regression_count), score_str),
            )
