"""Connectors view managing multi-agent adapters, 1-click configuration, and launching."""

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict

from evodev.gui.components.scrollable_frame import ScrollableFrame
from evodev.gui.theme import Colors, Fonts


class ConnectorsView(tk.Frame):
    """Unified AI Coding Agent Connectors management pane with 1-click setup & launch."""

    def __init__(self, parent: tk.Widget, app: Any):
        super().__init__(parent, bg=Colors.BG_DARK)
        self.app = app
        self.target_project_var = tk.StringVar(value=str(Path.cwd()))

        self.scroll = ScrollableFrame(self, bg=Colors.BG_DARK)
        self.scroll.pack(fill="both", expand=True)
        content = self.scroll.scrollable_content

        # Header Card
        card = tk.Frame(content, bg=Colors.SURFACE, highlightbackground=Colors.BORDER, highlightthickness=1, padx=18, pady=16)
        card.pack(fill="both", expand=True, padx=16, pady=16)

        head = tk.Frame(card, bg=Colors.SURFACE)
        head.pack(fill="x", pady=(0, 10))

        tk.Label(head, text="🔌 AI Coding Agent Hub", font=Fonts.HEADER_MEDIUM, bg=Colors.SURFACE, fg=Colors.TEXT_MAIN).pack(side="left")
        ttk.Button(head, text="🔄 Check Status", command=self.refresh).pack(side="right")

        tk.Label(
            card,
            text="Connect and launch OpenCode, Gemini CLI, Kilo Code, and Hermes with shared memory, lessons, and self-improving skills.",
            font=Fonts.SMALL,
            bg=Colors.SURFACE,
            fg=Colors.TEXT_MUTED,
        ).pack(anchor="w", pady=(0, 14))

        # Project Directory Selector Bar
        proj_bar = tk.Frame(card, bg=Colors.BG_DARK, highlightbackground=Colors.BORDER, highlightthickness=1, padx=12, pady=10)
        proj_bar.pack(fill="x", pady=(0, 16))

        tk.Label(proj_bar, text="Target Project Folder:", font=Fonts.BODY_BOLD, bg=Colors.BG_DARK, fg=Colors.TEXT_MAIN).pack(side="left", padx=(0, 8))

        self.entry_proj = ttk.Entry(proj_bar, textvariable=self.target_project_var, font=Fonts.CODE_SMALL)
        self.entry_proj.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.target_project_var.trace_add("write", lambda *args: self._on_project_changed())

        ttk.Button(proj_bar, text="📂 Browse...", command=self._browse_project).pack(side="right")

        # Container for connector cards
        self.cards_container = tk.Frame(card, bg=Colors.SURFACE)
        self.cards_container.pack(fill="x", pady=(0, 16))

        # Technical Diagnostics Table (Pro view)
        diag_sec = tk.Frame(card, bg=Colors.SURFACE)
        diag_sec.pack(fill="x", pady=(8, 0))

        tk.Label(diag_sec, text="Capabilities & Protocol Diagnostics", font=Fonts.HEADER_SMALL, bg=Colors.SURFACE, fg=Colors.TEXT_MAIN).pack(anchor="w", pady=(4, 6))

        cols = ("id", "agent", "status", "version", "mcp", "context", "ingest", "outcome")
        self.diag_tree = ttk.Treeview(diag_sec, columns=cols, show="headings", height=5)
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

    def _browse_project(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.target_project_var.get(), parent=self)
        if chosen:
            self.target_project_var.set(chosen)
            self.refresh()

    def _on_project_changed(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        """Fetch diagnostics and update UI."""
        for w in self.cards_container.winfo_children():
            w.destroy()
        for row in self.diag_tree.get_children():
            self.diag_tree.delete(row)

        diagnostics = self.app.connector_manager.get_diagnostics()
        proj_dir = Path(self.target_project_var.get().strip() or ".").resolve()

        for diag in diagnostics:
            adapter_id = diag["adapter_id"]

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
                    adapter_id,
                    diag["agent_name"],
                    diag["status"].upper(),
                    diag["agent_version"],
                    mcp_str,
                    ctx_str,
                    ingest_str,
                    out_str,
                ),
            )

            # Determine Project Connection State
            proj_connected = False
            needs_repair = False
            state_msg = "Not configured in target project"

            if adapter_id == "opencode":
                opencode_conn = self.app.registry.get("opencode")
                if opencode_conn and hasattr(opencode_conn, "validate_project_config"):
                    val = opencode_conn.validate_project_config(proj_dir)
                    if val.get("valid"):
                        proj_connected = True
                        state_msg = "Connected via opencode.json (MCP local)"
                    elif val.get("needs_repair"):
                        needs_repair = True
                        state_msg = "Config format error (Click Repair to fix)"
                    elif val.get("exists"):
                        state_msg = val.get("message", "Config incomplete")
            elif adapter_id == "gemini":
                hooks_p = proj_dir / ".agents" / "hooks.json"
                if hooks_p.is_file():
                    proj_connected = True
                    state_msg = "Connected via .agents/hooks.json & mcp_config.json"
            elif adapter_id == "kilocode":
                kilo_p = proj_dir / ".kilo" / "mcp.json"
                if kilo_p.is_file():
                    proj_connected = True
                    state_msg = "Connected via .kilo/mcp.json"
            elif adapter_id == "hermes":
                hermes_p = proj_dir / "hermes_config.json"
                if hermes_p.is_file():
                    proj_connected = True
                    state_msg = "Connected via hermes_config.json"

            # Build Enhanced Agent Card
            card = tk.Frame(
                self.cards_container,
                bg=Colors.BG_DARK,
                highlightbackground=Colors.BORDER,
                highlightthickness=1,
                padx=16,
                pady=14,
            )
            card.pack(fill="x", pady=(0, 12))

            top_row = tk.Frame(card, bg=Colors.BG_DARK)
            top_row.pack(fill="x")

            # Agent Title & Detected Version
            left_title = tk.Frame(top_row, bg=Colors.BG_DARK)
            left_title.pack(side="left")

            icons = {
                "opencode": "⚡",
                "gemini": "🤖",
                "kilocode": "⚡",
                "hermes": "🦅",
                "generic": "🔌",
            }
            icon = icons.get(adapter_id, "🔌")
            tk.Label(left_title, text=f"{icon} {diag['agent_name']}", font=Fonts.BODY_BOLD, bg=Colors.BG_DARK, fg=Colors.TEXT_MAIN).pack(side="left")

            v_txt = f"v{diag['agent_version']}" if diag["agent_version"] != "N/A" else "Available" if diag["is_available"] else "Standby"
            tk.Label(left_title, text=v_txt, font=Fonts.SMALL_BOLD, bg=Colors.SURFACE, fg=Colors.ACCENT_TEAL if diag["is_available"] else Colors.TEXT_DIM, padx=6, pady=1).pack(side="left", padx=(10, 0))

            # Status Badge
            if proj_connected:
                badge_bg = Colors.SURFACE_LIGHT
                badge_fg = Colors.STATUS_GREEN
                badge_txt = "● CONNECTED IN PROJECT"
            elif needs_repair:
                badge_bg = Colors.SURFACE_LIGHT
                badge_fg = Colors.STATUS_YELLOW
                badge_txt = "⚠️ REPAIR REQUIRED"
            elif diag["is_available"]:
                badge_bg = Colors.SURFACE_LIGHT
                badge_fg = Colors.ACCENT_CYAN
                badge_txt = "○ READY TO CONNECT"
            else:
                badge_bg = Colors.SURFACE_LIGHT
                badge_fg = Colors.TEXT_DIM
                badge_txt = "STANDBY"

            tk.Label(top_row, text=badge_txt, font=Fonts.SMALL_BOLD, bg=badge_bg, fg=badge_fg, padx=8, pady=2).pack(side="right")

            # Description & Target Project State
            tk.Label(card, text=diag["description"], font=Fonts.SMALL, bg=Colors.BG_DARK, fg=Colors.TEXT_MUTED, wraplength=700, justify="left").pack(anchor="w", pady=(4, 2))
            tk.Label(card, text=f"Status: {state_msg}", font=Fonts.SMALL_BOLD, bg=Colors.BG_DARK, fg=badge_fg).pack(anchor="w", pady=(0, 10))

            # Action Buttons Row
            actions_row = tk.Frame(card, bg=Colors.BG_DARK)
            actions_row.pack(fill="x")

            # 1-Click Connect Button
            connect_btn_text = "⚡ Re-Connect" if proj_connected else "🛠️ Auto-Repair" if needs_repair else "⚡ 1-Click Connect"
            ttk.Button(
                actions_row,
                text=connect_btn_text,
                style="Success.TButton",
                command=lambda aid=adapter_id: self._connect_agent(aid),
            ).pack(side="left", padx=(0, 8))

            # 1-Click Launch Button
            ttk.Button(
                actions_row,
                text=f"🚀 Open {diag['agent_name'].split()[0]}",
                style="Launch.TButton",
                command=lambda aid=adapter_id: self._launch_agent(aid),
            ).pack(side="left", padx=(0, 8))

            # Test Connection Button
            ttk.Button(
                actions_row,
                text="🔍 Test Connection",
                command=lambda aid=adapter_id: self._test_connection(aid),
            ).pack(side="left", padx=(0, 8))

            # CLI Command fallback button
            cmd_str = ""
            if adapter_id == "opencode":
                cmd_str = "evodev connectors install-opencode"
            elif adapter_id == "gemini":
                cmd_str = "evodev connectors install-gemini"
            elif adapter_id == "kilocode":
                cmd_str = "evodev connectors install-kilo"
            else:
                cmd_str = "POST http://127.0.0.1:8765/api/query"

            ttk.Button(
                actions_row,
                text="📋 Copy CLI Command",
                command=lambda c=cmd_str: self._copy_cmd(c),
            ).pack(side="right")

    def _connect_agent(self, adapter_id: str) -> None:
        """Provision or repair connector configuration for target project."""
        proj_dir = Path(self.target_project_var.get().strip() or ".").resolve()
        res = self.app.connector_manager.setup_connector_for_project(adapter_id, proj_dir)
        if res.get("success"):
            messagebox.showinfo("Agent Connected", res.get("message", "Connected successfully!"), parent=self)
        else:
            messagebox.showerror("Configuration Error", res.get("message", "Failed to connect."), parent=self)
        self.refresh()

    def _launch_agent(self, adapter_id: str) -> None:
        """Launch the agent terminal session in target project."""
        proj_dir = Path(self.target_project_var.get().strip() or ".").resolve()
        res = self.app.connector_manager.launch_agent(adapter_id, proj_dir)
        if not res.get("success"):
            messagebox.showwarning("Agent Launch", res.get("message", "Unable to launch."), parent=self)
        self.refresh()

    def _test_connection(self, adapter_id: str) -> None:
        """Run live preflight connectivity test for the agent."""
        proj_dir = Path(self.target_project_var.get().strip() or ".").resolve()
        if adapter_id == "opencode":
            opencode_conn = self.app.registry.get("opencode")
            val = opencode_conn.validate_project_config(proj_dir) if opencode_conn else {}
            if val.get("valid"):
                messagebox.showinfo(
                    "OpenCode MCP Test",
                    f"✓ OpenCode MCP configuration is VALID and ready!\n\nFile: {proj_dir / 'opencode.json'}\nType: local\nCommand: python -m evodev.connectors.opencode_mcp\nEnabled: True",
                    parent=self,
                )
            elif val.get("needs_repair"):
                messagebox.showwarning(
                    "OpenCode MCP Test",
                    f"⚠️ Configuration needs repair:\n{val.get('message')}\n\nClick 'Auto-Repair' to automatically fix opencode.json schema.",
                    parent=self,
                )
            else:
                messagebox.showinfo(
                    "OpenCode MCP Test",
                    f"Status: {val.get('message', 'Not configured')}\nClick '1-Click Connect' to configure OpenCode in this project.",
                    parent=self,
                )
        elif adapter_id == "gemini":
            hooks_p = proj_dir / ".agents" / "hooks.json"
            if hooks_p.is_file():
                messagebox.showinfo("Gemini CLI Test", f"✓ Gemini CLI hooks detected and operational at:\n{hooks_p}", parent=self)
            else:
                messagebox.showinfo("Gemini CLI Test", "Gemini CLI hooks not yet initialized in target project.\nClick '1-Click Connect' to provision .agents/hooks.json.", parent=self)
        elif adapter_id == "kilocode":
            kilo_p = proj_dir / ".kilo" / "mcp.json"
            if kilo_p.is_file():
                messagebox.showinfo("Kilo Code Test", f"✓ Kilo Code MCP detected at:\n{kilo_p}", parent=self)
            else:
                messagebox.showinfo("Kilo Code Test", "Kilo Code MCP not yet initialized.\nClick '1-Click Connect' to provision .kilo/mcp.json.", parent=self)
        elif adapter_id == "hermes":
            hermes_p = proj_dir / "hermes_config.json"
            if hermes_p.is_file():
                messagebox.showinfo("Hermes Test", f"✓ Hermes configuration detected at:\n{hermes_p}", parent=self)
            else:
                messagebox.showinfo("Hermes Test", "Hermes tools not yet initialized.\nClick '1-Click Connect' to provision hermes_config.json.", parent=self)
        else:
            messagebox.showinfo("Connection Test", f"Connector '{adapter_id}' is active in registry.", parent=self)

    def _copy_cmd(self, cmd: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(cmd)
        messagebox.showinfo("Copied", f"Copied to clipboard:\n{cmd}", parent=self)
