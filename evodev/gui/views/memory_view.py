"""Categorized Persistent Memory management view with scope isolation and search."""

import json
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Optional

from evodev.gui.components.scrollable_frame import ScrollableFrame
from evodev.gui.theme import Colors, Fonts
from evodev.models.experience import KnowledgeScope
from evodev.models.memory import MemoryCategory, MemoryItem


class MemoryView(tk.Frame):
    """Categorized persistent memory inspection, search, and editing pane."""

    CATEGORIES = [
        "ALL",
        "PREFERENCES",
        "ARCHITECTURE",
        "LESSONS",
        "ANTI_PATTERNS",
        "TASK_SUMMARIES",
        "SKILLS",
        "GENERAL",
        "PROJECT_PRIVATE",
    ]

    def __init__(self, parent: tk.Widget, app: Any):
        super().__init__(parent, bg=Colors.BG_DARK)
        self.app = app
        self.active_category = "ALL"
        self._current_memories: list[MemoryItem] = []

        self.scroll = ScrollableFrame(self, bg=Colors.BG_DARK)
        self.scroll.pack(fill="both", expand=True)
        content = self.scroll.scrollable_content

        card = tk.Frame(content, bg=Colors.SURFACE, highlightbackground=Colors.BORDER, highlightthickness=1, padx=16, pady=14)
        card.pack(fill="both", expand=True, padx=16, pady=16)

        # Header with Category Tabs
        head = tk.Frame(card, bg=Colors.SURFACE)
        head.pack(fill="x", pady=(0, 10))
        tk.Label(head, text="Categorized Persistent Memory", font=Fonts.HEADER_MEDIUM, bg=Colors.SURFACE, fg=Colors.TEXT_MAIN).pack(side="left")

        # Category Filter Tabs
        filter_f = tk.Frame(card, bg=Colors.SURFACE)
        filter_f.pack(fill="x", pady=(0, 10))

        self.cat_btns: dict[str, ttk.Button] = {}
        for cat in self.CATEGORIES:
            btn = ttk.Button(
                filter_f,
                text=cat.replace("_", " "),
                style="SubTab.TButton",
                command=lambda c=cat: self._set_category(c),
            )
            btn.pack(side="left", padx=2, pady=2)
            self.cat_btns[cat] = btn

        # Search Bar & Actions
        search_f = tk.Frame(card, bg=Colors.SURFACE)
        search_f.pack(fill="x", pady=(0, 10))

        tk.Label(search_f, text="Search Memory:", font=Fonts.SMALL_BOLD, bg=Colors.SURFACE, fg=Colors.TEXT_MUTED).pack(side="left", padx=(0, 8))
        self.search_entry = ttk.Entry(search_f)
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.search_entry.bind("<KeyRelease>", lambda e: self.refresh())

        ttk.Button(search_f, text="+ Add Memory", style="Primary.TButton", command=self._open_add_dialog).pack(side="right", padx=(4, 0))
        ttk.Button(search_f, text="⚡ Consolidate", command=self._consolidate_duplicates).pack(side="right")

        # Memory Treeview
        cols = ("cat", "title", "scope", "conf", "project", "evidence", "status")
        self.tree = ttk.Treeview(card, columns=cols, show="headings", height=10)
        self.tree.heading("cat", text="Category")
        self.tree.heading("title", text="Title")
        self.tree.heading("scope", text="Scope")
        self.tree.heading("conf", text="Confidence")
        self.tree.heading("project", text="Project")
        self.tree.heading("evidence", text="Evidence")
        self.tree.heading("status", text="Active")

        self.tree.column("cat", width=110)
        self.tree.column("title", width=260)
        self.tree.column("scope", width=90, anchor="center")
        self.tree.column("conf", width=70, anchor="center")
        self.tree.column("project", width=90, anchor="center")
        self.tree.column("evidence", width=70, anchor="center")
        self.tree.column("status", width=60, anchor="center")
        self.tree.pack(fill="x")

        self.tree.bind("<<TreeviewSelect>>", self._on_select_item)

        # Detail Pane
        self.detail_card = tk.Frame(card, bg=Colors.SURFACE_LIGHT, padx=12, pady=10, highlightbackground=Colors.BORDER, highlightthickness=1)
        self.detail_card.pack(fill="both", expand=True, pady=(12, 0))

        detail_head = tk.Frame(self.detail_card, bg=Colors.SURFACE_LIGHT)
        detail_head.pack(fill="x", pady=(0, 6))

        self.detail_title = tk.Label(detail_head, text="Select a memory item above to inspect details", font=Fonts.BODY_BOLD, bg=Colors.SURFACE_LIGHT, fg=Colors.TEXT_MAIN)
        self.detail_title.pack(side="left")

        self.btn_deactivate = ttk.Button(detail_head, text="Deactivate", command=self._deactivate_selected)
        self.btn_deactivate.pack(side="right", padx=(4, 0))
        self.btn_delete = ttk.Button(detail_head, text="Delete", style="Danger.TButton", command=self._delete_selected)
        self.btn_delete.pack(side="right")

        # Content text
        self.detail_text = tk.Text(
            self.detail_card,
            bg=Colors.BG_DARK,
            fg=Colors.TEXT_MAIN,
            font=Fonts.CODE,
            height=8,
            relief="flat",
            padx=8,
            pady=8,
            wrap="word",
        )
        self.detail_text.pack(fill="both", expand=True)

        self._set_category("ALL")

    def _set_category(self, cat: str) -> None:
        self.active_category = cat
        for c, btn in self.cat_btns.items():
            btn.configure(style="ActiveSubTab.TButton" if c == cat else "SubTab.TButton")
        self.refresh()

    def refresh(self) -> None:
        for row in self.tree.get_children():
            self.tree.delete(row)

        active = self.app.p_repo.get_active()
        p_id = active.profile_id if active else "default"

        cat_filter = None
        if self.active_category != "ALL":
            cat_filter = MemoryCategory(self.active_category.lower())

        memories = self.app.mem_repo.list_by_profile(p_id, category=cat_filter, active_only=False)
        query = self.search_entry.get().strip().lower()

        filtered: list[MemoryItem] = []
        for m in memories:
            if query:
                m_str = (m.title + " " + json.dumps(m.content)).lower()
                if query not in m_str:
                    continue
            filtered.append(m)

        self._current_memories = filtered

        for m in filtered:
            self.tree.insert(
                "",
                "end",
                iid=m.id,
                values=(
                    m.category.value,
                    m.title,
                    m.scope.value,
                    f"{m.confidence:.2f}",
                    m.project_id or "global",
                    str(len(m.evidence)),
                    "YES" if m.is_active else "NO",
                ),
            )

        self.detail_text.delete("1.0", "end")
        self.detail_text.insert("end", "// Select a memory item above to inspect full content, provenance, and verification evidence.")
        self.detail_title.configure(text="Memory Details")

    def _on_select_item(self, event=None) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        mem_id = selected[0]
        mem = self.app.mem_repo.get_by_id(mem_id)
        if not mem:
            return

        self.detail_title.configure(text=f"[{mem.category.value.upper()}] {mem.title} (ID: {mem.id[:8]}...)")
        self.detail_text.delete("1.0", "end")

        out = {
            "id": mem.id,
            "category": mem.category.value,
            "title": mem.title,
            "scope": mem.scope.value,
            "project_id": mem.project_id,
            "confidence": mem.confidence,
            "content": mem.content,
            "provenance": {
                "verification_count": mem.provenance.verification_count,
                "failure_count": mem.provenance.failure_count,
                "origin_project_ids": mem.provenance.origin_project_ids,
            },
            "evidence": [e.model_dump(mode="json") for e in mem.evidence],
            "created_at": mem.created_at.isoformat(),
            "updated_at": mem.updated_at.isoformat(),
        }
        self.detail_text.insert("end", json.dumps(out, indent=2))

    def _open_add_dialog(self) -> None:
        dlg = tk.Toplevel(self.app.root)
        dlg.title("Add Persistent Memory")
        dlg.geometry("480x420")
        dlg.configure(bg=Colors.BG_DARK)
        dlg.transient(self.app.root)
        dlg.grab_set()

        f = tk.Frame(dlg, bg=Colors.SURFACE, padx=16, pady=16)
        f.pack(fill="both", expand=True, padx=12, pady=12)

        tk.Label(f, text="Add Persistent Memory Item", font=Fonts.BODY_BOLD, bg=Colors.SURFACE, fg=Colors.TEXT_MAIN).pack(anchor="w", pady=(0, 10))

        tk.Label(f, text="Category:", font=Fonts.SMALL_BOLD, bg=Colors.SURFACE, fg=Colors.TEXT_MUTED).pack(anchor="w")
        cat_cb = ttk.Combobox(f, values=[c.value for c in MemoryCategory], state="readonly")
        cat_cb.set("preferences")
        cat_cb.pack(fill="x", pady=(2, 8))

        tk.Label(f, text="Title / Summary:", font=Fonts.SMALL_BOLD, bg=Colors.SURFACE, fg=Colors.TEXT_MUTED).pack(anchor="w")
        title_e = ttk.Entry(f)
        title_e.pack(fill="x", pady=(2, 8))

        tk.Label(f, text="Project ID (required if project-private):", font=Fonts.SMALL_BOLD, bg=Colors.SURFACE, fg=Colors.TEXT_MUTED).pack(anchor="w")
        proj_e = ttk.Entry(f)
        proj_e.pack(fill="x", pady=(2, 8))

        tk.Label(f, text="Content (JSON or Text):", font=Fonts.SMALL_BOLD, bg=Colors.SURFACE, fg=Colors.TEXT_MUTED).pack(anchor="w")
        content_txt = tk.Text(f, height=5, bg=Colors.BG_DARK, fg=Colors.TEXT_MAIN, font=Fonts.CODE)
        content_txt.insert("1.0", '{\n  "note": "Description of preference or architecture rule"\n}')
        content_txt.pack(fill="both", expand=True, pady=(2, 10))

        def _save():
            cat = MemoryCategory(cat_cb.get())
            title = title_e.get().strip()
            proj = proj_e.get().strip() or None
            raw_c = content_txt.get("1.0", "end").strip()

            if not title:
                messagebox.showerror("Validation Error", "Title is required.", parent=dlg)
                return

            try:
                c_dict = json.loads(raw_c)
                if not isinstance(c_dict, dict):
                    c_dict = {"text": raw_c}
            except Exception:
                c_dict = {"text": raw_c}

            try:
                self.app.mem_mgr.record_memory(
                    category=cat,
                    title=title,
                    content=c_dict,
                    project_id=proj,
                )
                dlg.destroy()
                self.refresh()
                messagebox.showinfo("Saved", f"Recorded memory '{title}'.", parent=self.app.root)
            except Exception as ex:
                messagebox.showerror("Error", str(ex), parent=dlg)

        btn_row = tk.Frame(f, bg=Colors.SURFACE)
        btn_row.pack(fill="x")
        ttk.Button(btn_row, text="Cancel", command=dlg.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(btn_row, text="Save Memory", style="Primary.TButton", command=_save).pack(side="right")

    def _deactivate_selected(self) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        mem_id = sel[0]
        self.app.mem_mgr.deactivate_memory(mem_id)
        self.refresh()

    def _delete_selected(self) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        mem_id = sel[0]
        if messagebox.askyesno("Confirm Delete", "Permanently remove this memory item?", parent=self.app.root):
            self.app.mem_mgr.delete_memory(mem_id)
            self.refresh()

    def _consolidate_duplicates(self) -> None:
        active = self.app.p_repo.get_active()
        p_id = active.profile_id if active else "default"
        count = self.app.mem_mgr.consolidate_duplicates(p_id)
        self.refresh()
        messagebox.showinfo("Consolidation", f"Consolidated {count} duplicate memory items.", parent=self.app.root)
