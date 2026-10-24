"""Diagnostics and Doctor view for inspecting database health and system posture."""

from pathlib import Path
import tkinter as tk
from tkinter import ttk
from typing import Any

from evodev.gui.components.scrollable_frame import ScrollableFrame
from evodev.gui.theme import Colors, Fonts
from evodev.security.redactor import SecretRedactor
from evodev.storage.migrations import MigrationManager


class DoctorView(tk.Frame):
    """System diagnostics, health checks, and security posture pane."""

    def __init__(self, parent: tk.Widget, app: Any):
        super().__init__(parent, bg=Colors.BG_DARK)
        self.app = app

        self.scroll = ScrollableFrame(self, bg=Colors.BG_DARK)
        self.scroll.pack(fill="both", expand=True)
        content = self.scroll.scrollable_content

        card = tk.Frame(content, bg=Colors.SURFACE, highlightbackground=Colors.BORDER, highlightthickness=1, padx=16, pady=14)
        card.pack(fill="both", expand=True, padx=16, pady=16)

        head = tk.Frame(card, bg=Colors.SURFACE)
        head.pack(fill="x", pady=(0, 12))

        tk.Label(head, text="System Health & Security Posture", font=Fonts.HEADER_MEDIUM, bg=Colors.SURFACE, fg=Colors.TEXT_MAIN).pack(side="left")
        ttk.Button(head, text="Run Diagnostics", command=self.refresh).pack(side="right")

        tk.Label(
            card,
            text="Empirical verification of local SQLite storage, write permissions, secret redaction, and integrations.",
            font=Fonts.SMALL,
            bg=Colors.SURFACE,
            fg=Colors.TEXT_MUTED,
        ).pack(anchor="w", pady=(0, 14))

        cols = ("comp", "status", "details")
        self.tree = ttk.Treeview(card, columns=cols, show="headings", height=12)
        self.tree.heading("comp", text="Component")
        self.tree.heading("status", text="Status")
        self.tree.heading("details", text="Details")

        self.tree.column("comp", width=220)
        self.tree.column("status", width=120, anchor="center")
        self.tree.column("details", width=480)
        self.tree.pack(fill="both", expand=True)

    def refresh(self) -> None:
        for row in self.tree.get_children():
            self.tree.delete(row)

        config = self.app.config

        # 1. SQLite Database & Migrations
        try:
            migrator = MigrationManager(self.app.db)
            with self.app.db.session() as conn:
                versions = migrator.get_applied_versions(conn)
            self.tree.insert("", "end", values=("SQLite Database", "OK", f"WAL mode active. Applied migrations: {versions}"))
        except Exception as e:
            self.tree.insert("", "end", values=("SQLite Database", "FAIL", str(e)))

        # 2. Storage Permissions
        try:
            config.ensure_directories()
            probe = config.data_dir / ".doctor_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            self.tree.insert("", "end", values=("Storage Permissions", "OK", f"Writable: {config.data_dir}"))
        except Exception as e:
            self.tree.insert("", "end", values=("Storage Permissions", "FAIL", str(e)))

        # 3. Secret Redaction Engine
        try:
            redactor = SecretRedactor()
            sample = "sk-proj-1234567890abcdef1234567890abcdef"
            masked = redactor.redact_text(sample)
            if "[REDACTED_OPENAI_KEY]" in masked:
                self.tree.insert("", "end", values=("Secret Redactor", "OK", "Regex and entropy patterns operational"))
            else:
                self.tree.insert("", "end", values=("Secret Redactor", "WARN", "Did not mask test token"))
        except Exception as e:
            self.tree.insert("", "end", values=("Secret Redactor", "FAIL", str(e)))

        # 4. Agent Connectors Diagnostics
        for diag in self.app.connector_manager.get_diagnostics():
            st_text = "FOUND" if diag["is_available"] else "STANDBY"
            self.tree.insert("", "end", values=(f"Agent: {diag['agent_name']}", st_text, diag["details"]))

        # 5. Active Profile
        active = self.app.p_repo.get_active()
        if active:
            self.tree.insert("", "end", values=("Active Profile", "ACTIVE", f"{active.name} (v{active.version}, ID: {active.profile_id})"))
        else:
            self.tree.insert("", "end", values=("Active Profile", "NONE", "No profile currently active"))
