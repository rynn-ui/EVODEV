"""Complete uninstallation and safe data lifecycle management view (Part E)."""

from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

from evodev.gui.components.dialogs import UninstallDialog
from evodev.gui.components.scrollable_frame import ScrollableFrame
from evodev.gui.theme import Colors, Fonts
from evodev.lifecycle.uninstaller import EvoDevUninstaller, UninstallPlan


class UninstallView(tk.Frame):
    """Safe uninstallation and resource lifecycle management pane."""

    def __init__(self, parent: tk.Widget, app: Any):
        super().__init__(parent, bg=Colors.BG_DARK)
        self.app = app
        self.uninstaller = EvoDevUninstaller(
            config=self.app.config,
            db_manager=self.app.db,
            search_workspace_integrations=True,
        )

        self.scroll = ScrollableFrame(self, bg=Colors.BG_DARK)
        self.scroll.pack(fill="both", expand=True)
        content = self.scroll.scrollable_content

        card = tk.Frame(content, bg=Colors.SURFACE, highlightbackground=Colors.BORDER, highlightthickness=1, padx=16, pady=16)
        card.pack(fill="both", expand=True, padx=16, pady=16)

        # Header
        tk.Label(card, text="Complete Uninstallation & Safe Data Lifecycle", font=Fonts.HEADER_MEDIUM, bg=Colors.SURFACE, fg=Colors.STATUS_RED).pack(anchor="w")
        tk.Label(
            card,
            text="Safely remove EvoDev application state and registered connector entries while strictly preserving user-owned .vxp archives.",
            font=Fonts.SMALL,
            bg=Colors.SURFACE,
            fg=Colors.TEXT_MUTED,
            wraplength=700,
            justify="left",
        ).pack(anchor="w", pady=(2, 14))

        # Safety guarantee banner
        banner = tk.Frame(card, bg=Colors.BG_DARK, highlightbackground=Colors.STATUS_GREEN, highlightthickness=1, padx=14, pady=10)
        banner.pack(fill="x", pady=(0, 14))
        tk.Label(banner, text="🛡️ SAFEGUARD GUARANTEE", font=Fonts.SMALL_BOLD, bg=Colors.BG_DARK, fg=Colors.STATUS_GREEN).pack(anchor="w")
        tk.Label(
            banner,
            text="External .vxp files outside EvoDev's managed directory will NEVER be deleted or modified. Only EvoDev-owned files and integration keys are scheduled for removal.",
            font=Fonts.SMALL,
            bg=Colors.BG_DARK,
            fg=Colors.TEXT_MAIN,
            wraplength=660,
            justify="left",
        ).pack(anchor="w", pady=(2, 0))

        # Action bar
        act_f = tk.Frame(card, bg=Colors.SURFACE)
        act_f.pack(fill="x", pady=(0, 12))
        ttk.Button(act_f, text="Preview Removal Plan", command=self.refresh).pack(side="left", padx=(0, 10))
        ttk.Button(act_f, text="⚠️ Uninstall EvoDev...", style="Danger.TButton", command=self._open_uninstall_dialog).pack(side="left")

        # Plan Summary Box
        tk.Label(card, text="Current Installation & Planned Resources to Clean", font=Fonts.HEADER_SMALL, bg=Colors.SURFACE, fg=Colors.TEXT_MAIN).pack(anchor="w", pady=(6, 6))

        self.plan_text = tk.Text(card, bg=Colors.BG_DARK, fg=Colors.TEXT_MAIN, font=Fonts.CODE_SMALL, relief="flat", padx=10, pady=10, wrap="word", height=14)
        self.plan_text.pack(fill="both", expand=True)

    def refresh(self) -> None:
        """Regenerate and display the uninstallation plan."""
        plan = self.uninstaller.build_plan(keep_exports=True)
        self.plan_text.delete("1.0", tk.END)

        lines = [
            f"Installation Type: {plan.installation_type.value.upper()}",
            f"Managed Data Directory: {plan.data_dir}",
            "\n[1. OWNED FILES SCHEDULED FOR DELETION]",
        ]
        if plan.items_to_remove:
            for item in plan.items_to_remove:
                lines.append(f"  • [{item.category.upper()}] {item.path} ({item.description})")
        else:
            lines.append("  (No existing application files detected)")

        lines.append("\n[2. INTEGRATION ENTRIES SCHEDULED FOR REMOVAL (EVODEV KEYS ONLY)]")
        if plan.integrations_to_clean:
            for c in plan.integrations_to_clean:
                lines.append(f"  • [{c.agent_name}] Key '{c.entry_key}' inside {c.config_path}")
        else:
            lines.append("  (No active integration entries detected in current project or home)")

        lines.append("\n[3. USER RESOURCES PRESERVED (NEVER TOUCHED)]")
        if plan.preserved_items:
            for p in plan.preserved_items:
                lines.append(f"  • {p.path} ({p.reason})")
        else:
            lines.append("  • All external .vxp archives, exports, and unrelated configurations")

        lines.append(f"\n[4. PACKAGE REMOVAL COMMAND]\n  {plan.package_removal_command}")

        self.plan_text.insert("1.0", "\n".join(lines))

    def _open_uninstall_dialog(self) -> None:
        plan = self.uninstaller.build_plan(keep_exports=True)
        UninstallDialog(self, plan=plan, on_execute=self._execute_uninstall)

    def _execute_uninstall(self, perform_backup: bool, dry_run: bool) -> None:
        plan = self.uninstaller.build_plan(keep_exports=True)
        result = self.uninstaller.execute_uninstall(
            plan=plan,
            perform_backup=perform_backup,
            dry_run=dry_run,
        )

        msg_lines = []
        if result.dry_run:
            msg_lines.append("DRY-RUN SIMULATION COMPLETE:")
            msg_lines.append(f"Files that would be removed: {len(result.removed_files)}")
            msg_lines.append(f"Integrations that would be cleaned: {len(result.cleaned_integrations)}")
            msg_lines.append("Zero changes were made to disk.")
        else:
            msg_lines.append("UNINSTALLATION COMPLETE:")
            if result.backup_path:
                msg_lines.append(f"Backup saved to: {result.backup_path}")
            msg_lines.append(f"Removed application files: {len(result.removed_files)}")
            msg_lines.append(f"Cleaned integrations: {len(result.cleaned_integrations)}")
            msg_lines.append(f"Package removal command: {result.package_instructions}")

        if result.errors:
            msg_lines.append("\nEncountered Warnings / Errors:")
            for err in result.errors:
                msg_lines.append(f"• {err.get('path', 'General')}: {err.get('error')}")

        messagebox.showinfo("Uninstall Result", "\n".join(msg_lines), parent=self)
        self.refresh()
