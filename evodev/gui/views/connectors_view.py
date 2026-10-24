"""Connectors view managing multi-agent adapters and diagnostics."""

from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

from evodev.gui.components.scrollable_frame import ScrollableFrame
from evodev.gui.theme import Colors, Fonts


class ConnectorsView(tk.Frame):
    """Unified AI Coding Agent Connectors management pane."""

    def __init__(self, parent: tk.Widget, app: Any):
        super().__init__(parent, bg=Colors.BG_DARK)
        self.app = app

        self.scroll = ScrollableFrame(self, bg=Colors.BG_DARK)
        self.scroll.pack(fill="both", expand=True)
        content = self.scroll.scrollable_content

        card = tk.Frame(content, bg=Colors.SURFACE, highlightbackground=Colors.BORDER, highlightthickness=1, padx=16, pady=14)
        card.pack(fill="both", expand=True, padx=16, pady=16)

        head = tk.Frame(card, bg=Colors.SURFACE)
        head.pack(fill="x", pady=(0, 14))

        tk.Label(head, text="Unified AI Coding Agent Connectors", font=Fonts.HEADER_MEDIUM, bg=Colors.SURFACE, fg=Colors.TEXT_MAIN).pack(side="left")
        ttk.Button(head, text="Run Health Checks", command=self.refresh).pack(side="right")

        tk.Label(
            card,
            text="All agents share the same EvoDev Core learning engine, database, retrieval system, and experience profiles.",
            font=Fonts.SMALL,
            bg=Colors.SURFACE,
            fg=Colors.TEXT_MUTED,
        ).pack(anchor="w", pady=(0, 14))

        # Container for connector cards
        self.cards_container = tk.Frame(card, bg=Colors.SURFACE)
        self.cards_container.pack(fill="x", pady=(0, 16))

        # Diagnostics Table
        tk.Label(card, text="Connector Diagnostics & Capabilities Matrix", font=Fonts.HEADER_SMALL, bg=Colors.SURFACE, fg=Colors.TEXT_MAIN).pack(anchor="w", pady=(8, 8))

        cols = ("id", "agent", "status", "version", "mcp", "context", "ingest", "outcome")
        self.diag_tree = ttk.Treeview(card, columns=cols, show="headings", height=5)
        self.diag_tree.heading("id", text="Adapter ID")
        self.diag_tree.heading("agent", text="Agent Name")
        self.diag_tree.heading("status", text="Health Status")
        self.diag_tree.heading("version", text="Detected Version")
        self.diag_tree.heading("mcp", text="MCP Compliant")
        self.diag_tree.heading("context", text="Context Retrieval")
        self.diag_tree.heading("ingest", text="Event Ingestion")
        self.diag_tree.heading("outcome", text="Outcome Reporting")

        self.diag_tree.column("id", width=90, anchor="center")
        self.diag_tree.column("agent", width=180)
        self.diag_tree.column("status", width=100, anchor="center")
        self.diag_tree.column("version", width=120)
        self.diag_tree.column("mcp", width=100, anchor="center")
        self.diag_tree.column("context", width=110, anchor="center")
        self.diag_tree.column("ingest", width=110, anchor="center")
        self.diag_tree.column("outcome", width=120, anchor="center")
        self.diag_tree.pack(fill="x")

    def refresh(self) -> None:
        for w in self.cards_container.winfo_children():
            w.destroy()
        for row in self.diag_tree.get_children():
            self.diag_tree.delete(row)

        diagnostics = self.app.connector_manager.get_diagnostics()

        for diag in diagnostics:
            # Add to Diagnostics Treeview
            caps = diag.get("capabilities", {})
            mcp_str = "✓" if caps.get("mcp_compliant") else "-"
            ctx_str = "✓" if caps.get("can_retrieve_context") else "-"
            ingest_str = "✓" if caps.get("can_ingest_events") else "-"
            out_str = "✓" if caps.get("can_report_outcomes") else "-"

            self.diag_tree.insert(
                "",
                "end",
                values=(
                    diag["adapter_id"],
                    diag["agent_name"],
                    diag["status"].upper(),
                    diag["agent_version"],
                    mcp_str,
                    ctx_str,
                    ingest_str,
                    out_str,
                ),
            )

            # Build Adapter Card
            card = tk.Frame(
                self.cards_container,
                bg=Colors.BG_DARK,
                highlightbackground=Colors.BORDER,
                highlightthickness=1,
                padx=14,
                pady=12,
            )
            card.pack(fill="x", pady=(0, 10))

            top_row = tk.Frame(card, bg=Colors.BG_DARK)
            top_row.pack(fill="x")

            tk.Label(top_row, text=diag["agent_name"], font=Fonts.BODY_BOLD, bg=Colors.BG_DARK, fg=Colors.TEXT_MAIN).pack(side="left")

            status_color = Colors.STATUS_GREEN if diag["is_available"] else Colors.TEXT_DIM
            status_txt = "AVAILABLE" if diag["is_available"] else "STANDBY"
            tk.Label(top_row, text=status_txt, font=Fonts.SMALL_BOLD, bg=Colors.SURFACE_LIGHT, fg=status_color, padx=6, pady=1).pack(side="right")

            tk.Label(card, text=diag["description"], font=Fonts.SMALL, bg=Colors.BG_DARK, fg=Colors.TEXT_MUTED, wraplength=700, justify="left").pack(anchor="w", pady=(4, 6))

            cmd_str = ""
            if diag["adapter_id"] == "opencode":
                cmd_str = "evodev connectors install-opencode"
            elif diag["adapter_id"] == "gemini":
                cmd_str = "evodev connectors install-gemini"
            elif diag["adapter_id"] == "kilocode":
                cmd_str = "evodev connectors install-kilo"
            else:
                cmd_str = "POST http://127.0.0.1:8765/api/query"

            cmd_f = tk.Frame(card, bg=Colors.SURFACE, padx=8, pady=4)
            cmd_f.pack(fill="x")
            tk.Label(cmd_f, text=f"Config Command:  {cmd_str}", font=Fonts.CODE_SMALL, bg=Colors.SURFACE, fg=Colors.ACCENT_CYAN).pack(side="left")
            ttk.Button(cmd_f, text="Copy", command=lambda c=cmd_str: self._copy_cmd(c)).pack(side="right")

    def _copy_cmd(self, cmd: str):
        self.clipboard_clear()
        self.clipboard_append(cmd)
        messagebox.showinfo("Copied", f"Copied to clipboard:\n{cmd}", parent=self)
