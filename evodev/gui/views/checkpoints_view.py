"""Safe Checkpoints & Rollback view for managing Git, DB, and Profile snapshots."""

import json
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Optional

from evodev.gui.components.scrollable_frame import ScrollableFrame
from evodev.gui.theme import Colors, Fonts
from evodev.models.checkpoints import CheckpointRecord, CheckpointType


class CheckpointsView(tk.Frame):
    """Safe checkpoints management, reviewable Git diff inspection, and DB rollback pane."""

    def __init__(self, parent: tk.Widget, app: Any):
        super().__init__(parent, bg=Colors.BG_DARK)
        self.app = app
        self.active_type: Optional[CheckpointType] = None
        self.selected_checkpoint: Optional[CheckpointRecord] = None

        self.scroll = ScrollableFrame(self, bg=Colors.BG_DARK)
        self.scroll.pack(fill="both", expand=True)
        content = self.scroll.scrollable_content

        card = tk.Frame(content, bg=Colors.SURFACE, highlightbackground=Colors.BORDER, highlightthickness=1, padx=16, pady=14)
        card.pack(fill="both", expand=True, padx=16, pady=16)

        # Header & Actions
        head = tk.Frame(card, bg=Colors.SURFACE)
        head.pack(fill="x", pady=(0, 10))

        tk.Label(head, text="Safe Checkpoints & Non-Destructive Rollback", font=Fonts.HEADER_MEDIUM, bg=Colors.SURFACE, fg=Colors.TEXT_MAIN).pack(side="left")

        btn_row = tk.Frame(head, bg=Colors.SURFACE)
        btn_row.pack(side="right")
        ttk.Button(btn_row, text="+ Git Snapshot", command=self._create_git_checkpoint).pack(side="left", padx=(0, 6))
        ttk.Button(btn_row, text="+ DB Backup", command=self._create_db_checkpoint).pack(side="left", padx=(0, 6))
        ttk.Button(btn_row, text="+ Profile Version", command=self._create_profile_checkpoint).pack(side="left", padx=(0, 6))
        ttk.Button(btn_row, text="⏪ Restore DB", style="Danger.TButton", command=self._restore_selected_db).pack(side="left")

        # Type Filters
        filter_f = tk.Frame(card, bg=Colors.SURFACE)
        filter_f.pack(fill="x", pady=(0, 8))

        self.type_btns: dict[str, ttk.Button] = {}
        for t_label in ["ALL", "GIT", "DATABASE", "PROFILE"]:
            btn = ttk.Button(
                filter_f,
                text=t_label,
                style="SubTab.TButton",
                command=lambda t=t_label: self._set_type_filter(t),
            )
            btn.pack(side="left", padx=2)
            self.type_btns[t_label] = btn

        # Checkpoints Table
        cols = ("type", "summary", "reference", "created_at")
        self.tree = ttk.Treeview(card, columns=cols, show="headings", height=8)
        self.tree.heading("type", text="Type")
        self.tree.heading("summary", text="Summary Description")
        self.tree.heading("reference", text="Reference / Hash")
        self.tree.heading("created_at", text="Timestamp")

        self.tree.column("type", width=90, anchor="center")
        self.tree.column("summary", width=360)
        self.tree.column("reference", width=180)
        self.tree.column("created_at", width=140, anchor="center")
        self.tree.pack(fill="x")

        self.tree.bind("<<TreeviewSelect>>", self._on_select_checkpoint)

        # Inspection & Diff Preview
        preview_card = tk.Frame(card, bg=Colors.SURFACE_LIGHT, padx=12, pady=10, highlightbackground=Colors.BORDER, highlightthickness=1)
        preview_card.pack(fill="both", expand=True, pady=(12, 0))

        self.preview_head = tk.Label(preview_card, text="Checkpoint Details & Reviewable Diff", font=Fonts.BODY_BOLD, bg=Colors.SURFACE_LIGHT, fg=Colors.TEXT_MAIN)
        self.preview_head.pack(anchor="w", pady=(0, 6))

        self.preview_text = tk.Text(
            preview_card,
            bg=Colors.BG_DARK,
            fg=Colors.TEXT_MAIN,
            font=Fonts.CODE,
            height=10,
            relief="flat",
            padx=8,
            pady=8,
            wrap="word",
        )
        self.preview_text.pack(fill="both", expand=True)

        self._set_type_filter("ALL")

    def _set_type_filter(self, t_label: str) -> None:
        if t_label == "ALL":
            self.active_type = None
        else:
            self.active_type = CheckpointType(t_label.lower())

        for lbl, btn in self.type_btns.items():
            btn.configure(style="ActiveSubTab.TButton" if lbl == t_label else "SubTab.TButton")
        self.refresh()

    def refresh(self) -> None:
        for row in self.tree.get_children():
            self.tree.delete(row)

        cps = self.app.cp_mgr.list_checkpoints(checkpoint_type=self.active_type)
        for cp in cps:
            self.tree.insert(
                "",
                "end",
                iid=cp.id,
                values=(
                    cp.checkpoint_type.value.upper(),
                    cp.summary,
                    cp.reference,
                    cp.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )

        if self.selected_checkpoint:
            updated = self.app.cp_repo.get_by_id(self.selected_checkpoint.id)
            if updated:
                self.selected_checkpoint = updated
                self._render_details()

    def _on_select_checkpoint(self, event=None) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        cp_id = sel[0]
        self.selected_checkpoint = self.app.cp_repo.get_by_id(cp_id)
        self._render_details()

    def _render_details(self) -> None:
        if not self.selected_checkpoint:
            self.preview_text.delete("1.0", "end")
            self.preview_text.insert("end", "// Select a checkpoint to view status, diffs, or backup paths.")
            return

        cp = self.selected_checkpoint
        self.preview_head.configure(text=f"[{cp.checkpoint_type.value.upper()}] {cp.summary} ({cp.reference})")
        self.preview_text.delete("1.0", "end")

        out = {
            "id": cp.id,
            "type": cp.checkpoint_type.value,
            "summary": cp.summary,
            "reference": cp.reference,
            "created_at": cp.created_at.isoformat(),
            "details": cp.details,
        }
        self.preview_text.insert("end", json.dumps(out, indent=2))

    def _create_git_checkpoint(self) -> None:
        rec = self.app.cp_mgr.create_git_checkpoint(summary="Manual Git status snapshot from desktop GUI")
        self.refresh()
        self.tree.selection_set(rec.id)
        self._on_select_checkpoint()
        messagebox.showinfo("Git Checkpoint", f"Captured Git snapshot {rec.reference}.", parent=self.app.root)

    def _create_db_checkpoint(self) -> None:
        rec = self.app.cp_mgr.create_database_checkpoint(summary="Manual SQLite snapshot from desktop GUI")
        self.refresh()
        self.tree.selection_set(rec.id)
        self._on_select_checkpoint()
        messagebox.showinfo("DB Checkpoint", f"Created database backup snapshot.", parent=self.app.root)

    def _create_profile_checkpoint(self) -> None:
        active = self.app.p_repo.get_active()
        pid = active.profile_id if active else "default"
        rec = self.app.cp_mgr.create_profile_checkpoint(profile_id=pid, summary="Manual profile version checkpoint")
        self.refresh()
        self.tree.selection_set(rec.id)
        self._on_select_checkpoint()
        messagebox.showinfo("Profile Checkpoint", f"Created profile version checkpoint {rec.reference}.", parent=self.app.root)

    def _restore_selected_db(self) -> None:
        if not self.selected_checkpoint:
            messagebox.showwarning("Notice", "Select a DATABASE checkpoint to restore.", parent=self.app.root)
            return

        if self.selected_checkpoint.checkpoint_type != CheckpointType.DATABASE:
            messagebox.showwarning("Invalid Checkpoint", "Only DATABASE checkpoints can be directly restored here.", parent=self.app.root)
            return

        if messagebox.askyesno("Confirm Rollback", f"Rollback SQLite database to checkpoint '{self.selected_checkpoint.id}'? Active session will be restored.", parent=self.app.root):
            try:
                self.app.cp_mgr.rollback_database_checkpoint(self.selected_checkpoint.id)
                self.app.refresh_all_views()
                messagebox.showinfo("Rollback Complete", "Successfully restored database checkpoint.", parent=self.app.root)
            except Exception as e:
                messagebox.showerror("Rollback Failed", str(e), parent=self.app.root)
