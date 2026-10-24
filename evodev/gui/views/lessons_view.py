"""Verified Lessons view for inspecting accumulated lessons across knowledge scopes."""

import tkinter as tk
from tkinter import ttk
from typing import Any, Optional

from evodev.gui.components.dialogs import LessonDetailDialog
from evodev.gui.components.scrollable_frame import ScrollableFrame
from evodev.gui.theme import Colors, Fonts
from evodev.models.experience import KnowledgeScope


class LessonsView(tk.Frame):
    """Verified Lessons and Knowledge Scopes management pane."""

    def __init__(self, parent: tk.Widget, app: Any):
        super().__init__(parent, bg=Colors.BG_DARK)
        self.app = app
        self.active_scope = "ALL"

        self.scroll = ScrollableFrame(self, bg=Colors.BG_DARK)
        self.scroll.pack(fill="both", expand=True)
        content = self.scroll.scrollable_content

        card = tk.Frame(content, bg=Colors.SURFACE, highlightbackground=Colors.BORDER, highlightthickness=1, padx=16, pady=14)
        card.pack(fill="both", expand=True, padx=16, pady=16)

        # Header with Scope Filter Tags
        head = tk.Frame(card, bg=Colors.SURFACE)
        head.pack(fill="x", pady=(0, 12))

        tk.Label(head, text="Accumulated Lessons & Knowledge Scopes", font=Fonts.HEADER_MEDIUM, bg=Colors.SURFACE, fg=Colors.TEXT_MAIN).pack(side="left")

        filter_row = tk.Frame(head, bg=Colors.SURFACE)
        filter_row.pack(side="right")

        self.scope_btns = {}
        for sc in ["ALL", "GLOBAL", "TECHNOLOGY", "DOMAIN", "PROJECT", "PREFERENCES"]:
            btn = ttk.Button(filter_row, text=sc, style="SubTab.TButton", command=lambda s=sc: self._set_scope(s))
            btn.pack(side="left", padx=2)
            self.scope_btns[sc] = btn

        # Search Bar
        search_f = tk.Frame(card, bg=Colors.SURFACE)
        search_f.pack(fill="x", pady=(0, 10))
        tk.Label(search_f, text="Search:", font=Fonts.SMALL_BOLD, bg=Colors.SURFACE, fg=Colors.TEXT_MUTED).pack(side="left", padx=(0, 8))
        self.search_entry = ttk.Entry(search_f)
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.search_entry.bind("<KeyRelease>", lambda e: self.refresh())

        # Lessons Treeview
        cols = ("title", "scope", "trigger", "strategy", "conf", "status")
        self.tree = ttk.Treeview(card, columns=cols, show="headings", height=14)
        self.tree.heading("title", text="Title")
        self.tree.heading("scope", text="Scope")
        self.tree.heading("trigger", text="Trigger Pattern")
        self.tree.heading("strategy", text="Recommended Strategy")
        self.tree.heading("conf", text="Confidence")
        self.tree.heading("status", text="Status")

        self.tree.column("title", width=220)
        self.tree.column("scope", width=90, anchor="center")
        self.tree.column("trigger", width=200)
        self.tree.column("strategy", width=220)
        self.tree.column("conf", width=70, anchor="center")
        self.tree.column("status", width=70, anchor="center")
        self.tree.pack(fill="both", expand=True)

        self.tree.bind("<Double-1>", self._on_double_click)

        # Footer actions
        actions_f = tk.Frame(card, bg=Colors.SURFACE)
        actions_f.pack(fill="x", pady=(10, 0))
        tk.Label(actions_f, text="Double-click a lesson or click button to inspect details & evidence.", font=Fonts.SMALL, bg=Colors.SURFACE, fg=Colors.TEXT_MUTED).pack(side="left")
        ttk.Button(actions_f, text="Inspect Lesson Record", command=self._inspect_selected).pack(side="right")

        self._set_scope("ALL")

    def _set_scope(self, scope: str) -> None:
        self.active_scope = scope
        for sc, btn in self.scope_btns.items():
            btn.configure(style="ActiveSubTab.TButton" if sc == scope else "SubTab.TButton")
        self.refresh()

    def refresh(self) -> None:
        for row in self.tree.get_children():
            self.tree.delete(row)

        active = self.app.p_repo.get_active()
        p_id = active.profile_id if active else "default"

        lessons = self.app.l_repo.list_by_profile(p_id, active_only=False)
        query = self.search_entry.get().strip().lower()

        filtered = []
        for l in lessons:
            scope_val = l.scope.value.upper() if hasattr(l.scope, "value") else str(l.scope).upper()
            if self.active_scope != "ALL" and scope_val != self.active_scope:
                continue
            if query:
                combined = f"{l.title} {l.trigger_pattern} {l.recommended_strategy}".lower()
                if query not in combined:
                    continue
            filtered.append(l)

        if not filtered:
            self.tree.insert("", "end", values=("No matching lessons found in this profile.", "-", "-", "-", "-", "-"))
            return

        for l in filtered:
            scope_str = l.scope.value.upper() if hasattr(l.scope, "value") else str(l.scope).upper()
            status_str = "ACTIVE" if l.is_active else "DISABLED"
            self.tree.insert(
                "",
                "end",
                iid=l.id,
                values=(l.title, scope_str, l.trigger_pattern, l.recommended_strategy, f"{l.confidence:.2f}", status_str),
            )

    def _on_double_click(self, event):
        self._inspect_selected()

    def _inspect_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        lesson_id = sel[0]
        lesson = self.app.l_repo.get_by_id(lesson_id)
        if lesson:
            LessonDetailDialog(
                self,
                lesson=lesson,
                on_modify=self._on_modify,
                on_delete=self._on_delete,
            )

    def _on_modify(self, lesson_id: str, updates: dict, reason: str):
        self.app.inspector.modify_lesson_safely(lesson_id, updates, confirm=True, reason=reason)
        self.refresh()

    def _on_delete(self, lesson_id: str, reason: str):
        self.app.inspector.delete_lesson_safely(lesson_id, confirm=True)
        self.refresh()
