"""Modal dialogs for profile creation, safe mutations, password unlocking, and uninstallation."""

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable, Dict, List, Optional

from evodev.gui.theme import Colors, Fonts
from evodev.lifecycle.uninstaller import EvoDevUninstaller, UninstallPlan


class BaseDialog(tk.Toplevel):
    """Base modal dialog with dark theme and window centering."""

    def __init__(self, parent: tk.Widget, title: str, width: int = 500, height: int = 350):
        super().__init__(parent)
        self.transient(parent)
        self.title(title)
        self.configure(bg=Colors.BG_DARK)
        self.resizable(False, False)

        # Center relative to parent
        self.update_idletasks()
        p_x = parent.winfo_rootx()
        p_y = parent.winfo_rooty()
        p_w = parent.winfo_width()
        p_h = parent.winfo_height()

        x = max(50, p_x + (p_w - width) // 2)
        y = max(50, p_y + (p_h - height) // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")

        self.grab_set()

    def close(self):
        self.grab_release()
        self.destroy()


class NewProfileDialog(BaseDialog):
    """Dialog for creating a new experience profile."""

    def __init__(self, parent: tk.Widget, on_create: Callable[[Dict[str, Any]], None]):
        super().__init__(parent, "Create New Experience Profile", width=480, height=360)
        self.on_create = on_create

        pad_f = tk.Frame(self, bg=Colors.BG_DARK, padx=20, pady=20)
        pad_f.pack(fill="both", expand=True)

        tk.Label(pad_f, text="CREATE NEW PROFILE", font=Fonts.HEADER_SMALL, bg=Colors.BG_DARK, fg=Colors.ACCENT_CYAN).pack(anchor="w")
        tk.Label(pad_f, text="Define an isolated experience footprint for your coding tasks.", font=Fonts.SMALL, bg=Colors.BG_DARK, fg=Colors.TEXT_MUTED).pack(anchor="w", pady=(0, 15))

        # Profile Name
        tk.Label(pad_f, text="Profile Name *", font=Fonts.SMALL_BOLD, bg=Colors.BG_DARK, fg=Colors.TEXT_MAIN).pack(anchor="w")
        self.name_entry = ttk.Entry(pad_f)
        self.name_entry.pack(fill="x", pady=(2, 10))
        self.name_entry.focus_set()

        # Description
        tk.Label(pad_f, text="Description", font=Fonts.SMALL_BOLD, bg=Colors.BG_DARK, fg=Colors.TEXT_MAIN).pack(anchor="w")
        self.desc_entry = ttk.Entry(pad_f)
        self.desc_entry.pack(fill="x", pady=(2, 10))

        # Domain
        tk.Label(pad_f, text="Technical Domain", font=Fonts.SMALL_BOLD, bg=Colors.BG_DARK, fg=Colors.TEXT_MAIN).pack(anchor="w")
        self.domain_cb = ttk.Combobox(pad_f, values=["general", "web", "mobile", "backend", "ml", "devops"], state="readonly")
        self.domain_cb.set("general")
        self.domain_cb.pack(fill="x", pady=(2, 10))

        # Activate Immediately Checkbox
        self.activate_var = tk.BooleanVar(value=True)
        chk = tk.Checkbutton(
            pad_f,
            text="Activate profile immediately upon creation",
            variable=self.activate_var,
            bg=Colors.BG_DARK,
            fg=Colors.TEXT_MAIN,
            selectcolor=Colors.SURFACE,
            activebackground=Colors.BG_DARK,
            activeforeground=Colors.ACCENT_CYAN,
            font=Fonts.BODY,
        )
        chk.pack(anchor="w", pady=(5, 15))

        # Button row
        btn_row = tk.Frame(pad_f, bg=Colors.BG_DARK)
        btn_row.pack(fill="x", side="bottom")

        cancel_btn = ttk.Button(btn_row, text="Cancel", command=self.close)
        cancel_btn.pack(side="right", padx=(8, 0))

        create_btn = ttk.Button(btn_row, text="Create Profile", style="Primary.TButton", command=self._submit)
        create_btn.pack(side="right")

    def _submit(self):
        name = self.name_entry.get().strip()
        if not name:
            messagebox.showerror("Error", "Profile name cannot be empty.", parent=self)
            return
        data = {
            "name": name,
            "description": self.desc_entry.get().strip(),
            "domains": [self.domain_cb.get()],
            "activate": self.activate_var.get(),
        }
        self.close()
        self.on_create(data)


class ConfirmActionDialog(BaseDialog):
    """Dialog requiring explicit confirmation and checkpoint notes before mutations."""

    def __init__(
        self,
        parent: tk.Widget,
        title: str,
        message: str,
        on_confirm: Callable[[str], None],
        destructive: bool = False,
    ):
        super().__init__(parent, title, width=480, height=290)
        self.on_confirm = on_confirm

        pad_f = tk.Frame(self, bg=Colors.BG_DARK, padx=20, pady=20)
        pad_f.pack(fill="both", expand=True)

        header_color = Colors.STATUS_RED if destructive else Colors.ACCENT_CYAN
        tk.Label(pad_f, text=title.upper(), font=Fonts.HEADER_SMALL, bg=Colors.BG_DARK, fg=header_color).pack(anchor="w")

        msg_lbl = tk.Label(pad_f, text=message, font=Fonts.BODY, bg=Colors.BG_DARK, fg=Colors.TEXT_MAIN, wraplength=440, justify="left")
        msg_lbl.pack(anchor="w", pady=(8, 12))

        # Safety guarantee banner
        banner_f = tk.Frame(pad_f, bg=Colors.SURFACE, padx=10, pady=8, highlightbackground=Colors.ACCENT_TEAL, highlightthickness=1)
        banner_f.pack(fill="x", pady=(0, 12))
        tk.Label(
            banner_f,
            text="🛡️ Safety Guarantee: An immutable version checkpoint will be recorded before applying changes.",
            font=Fonts.SMALL,
            bg=Colors.SURFACE,
            fg=Colors.TEXT_MUTED,
            wraplength=420,
            justify="left",
        ).pack(anchor="w")

        tk.Label(pad_f, text="Checkpoint Note / Reason:", font=Fonts.SMALL_BOLD, bg=Colors.BG_DARK, fg=Colors.TEXT_MUTED).pack(anchor="w")
        self.reason_entry = ttk.Entry(pad_f)
        self.reason_entry.insert(0, "User manual action via desktop GUI")
        self.reason_entry.pack(fill="x", pady=(2, 15))

        btn_row = tk.Frame(pad_f, bg=Colors.BG_DARK)
        btn_row.pack(fill="x", side="bottom")

        ttk.Button(btn_row, text="Cancel", command=self.close).pack(side="right", padx=(8, 0))

        btn_style = "Danger.TButton" if destructive else "Primary.TButton"
        ttk.Button(btn_row, text="Confirm & Proceed", style=btn_style, command=self._submit).pack(side="right")

    def _submit(self):
        reason = self.reason_entry.get().strip() or "User confirmed action"
        self.close()
        self.on_confirm(reason)


class PasswordDialog(BaseDialog):
    """Modal for entering AES-256-GCM password to inspect encrypted profile."""

    def __init__(self, parent: tk.Widget, on_unlock: Callable[[str], None]):
        super().__init__(parent, "Unlock Encrypted Profile", width=440, height=220)
        self.on_unlock = on_unlock

        pad_f = tk.Frame(self, bg=Colors.BG_DARK, padx=20, pady=20)
        pad_f.pack(fill="both", expand=True)

        tk.Label(pad_f, text="🔒 ENCRYPTED PROFILE ARCHIVE", font=Fonts.HEADER_SMALL, bg=Colors.BG_DARK, fg=Colors.STATUS_YELLOW).pack(anchor="w")
        tk.Label(pad_f, text="Enter the decryption password to inspect internal records and lessons.", font=Fonts.SMALL, bg=Colors.BG_DARK, fg=Colors.TEXT_MUTED, wraplength=400, justify="left").pack(anchor="w", pady=(4, 12))

        self.pass_entry = ttk.Entry(pad_f, show="*")
        self.pass_entry.pack(fill="x", pady=(0, 15))
        self.pass_entry.focus_set()

        btn_row = tk.Frame(pad_f, bg=Colors.BG_DARK)
        btn_row.pack(fill="x", side="bottom")

        ttk.Button(btn_row, text="Cancel", command=self.close).pack(side="right", padx=(8, 0))
        ttk.Button(btn_row, text="Decrypt & Inspect", style="Primary.TButton", command=self._submit).pack(side="right")

    def _submit(self):
        pwd = self.pass_entry.get()
        if not pwd:
            messagebox.showerror("Error", "Password cannot be empty.", parent=self)
            return
        self.close()
        self.on_unlock(pwd)


class InspectFileDialog(BaseDialog):
    """Modal for selecting an external .vxp file to inspect."""

    def __init__(self, parent: tk.Widget, on_inspect: Callable[[str], None]):
        super().__init__(parent, "Inspect External .vxp File", width=520, height=230)
        self.on_inspect = on_inspect

        pad_f = tk.Frame(self, bg=Colors.BG_DARK, padx=20, pady=20)
        pad_f.pack(fill="both", expand=True)

        tk.Label(pad_f, text="INSPECT PORTABLE EXPERIENCE ARCHIVE", font=Fonts.HEADER_SMALL, bg=Colors.BG_DARK, fg=Colors.ACCENT_CYAN).pack(anchor="w")
        tk.Label(pad_f, text="Select any .vxp archive file on disk to inspect members, sizes, and digests.", font=Fonts.SMALL, bg=Colors.BG_DARK, fg=Colors.TEXT_MUTED).pack(anchor="w", pady=(4, 10))

        row = tk.Frame(pad_f, bg=Colors.BG_DARK)
        row.pack(fill="x", pady=(0, 15))

        self.path_entry = ttk.Entry(row)
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        browse_btn = ttk.Button(row, text="Browse...", command=self._browse)
        browse_btn.pack(side="right")

        btn_row = tk.Frame(pad_f, bg=Colors.BG_DARK)
        btn_row.pack(fill="x", side="bottom")

        ttk.Button(btn_row, text="Cancel", command=self.close).pack(side="right", padx=(8, 0))
        ttk.Button(btn_row, text="Inspect Archive", style="Primary.TButton", command=self._submit).pack(side="right")

    def _browse(self):
        f = filedialog.askopenfilename(
            parent=self,
            title="Select Experience Profile (.vxp)",
            filetypes=[("EvoDev Experience Archive", "*.vxp"), ("All Files", "*.*")],
        )
        if f:
            self.path_entry.delete(0, tk.END)
            self.path_entry.insert(0, f)

    def _submit(self):
        p = self.path_entry.get().strip()
        if not p or not Path(p).is_file():
            messagebox.showerror("Error", "Please select a valid .vxp file.", parent=self)
            return
        self.close()
        self.on_inspect(p)


class LessonDetailDialog(BaseDialog):
    """Detailed inspector for a single Lesson record with safe edit and delete."""

    def __init__(
        self,
        parent: tk.Widget,
        lesson: Any,
        on_modify: Optional[Callable[[str, Dict[str, Any], str], None]] = None,
        on_delete: Optional[Callable[[str, str], None]] = None,
    ):
        super().__init__(parent, f"Lesson Details: {lesson.title}", width=640, height=540)
        self.lesson = lesson
        self.on_modify = on_modify
        self.on_delete = on_delete

        pad_f = tk.Frame(self, bg=Colors.BG_DARK, padx=20, pady=16)
        pad_f.pack(fill="both", expand=True)

        # Header
        scope_str = lesson.scope.value.upper() if hasattr(lesson.scope, "value") else str(lesson.scope).upper()
        tk.Label(pad_f, text=f"[{scope_str}] {lesson.title}", font=Fonts.HEADER_SMALL, bg=Colors.BG_DARK, fg=Colors.ACCENT_CYAN, wraplength=580, justify="left").pack(anchor="w")

        meta_txt = f"Confidence: {lesson.confidence:.2f} · Active: {lesson.is_active} · Version: v{lesson.version} · Updated: {lesson.updated_at.strftime('%Y-%m-%d %H:%M')}"
        tk.Label(pad_f, text=meta_txt, font=Fonts.SMALL, bg=Colors.BG_DARK, fg=Colors.TEXT_MUTED).pack(anchor="w", pady=(2, 10))

        # Content area
        content_box = tk.Text(pad_f, bg=Colors.SURFACE, fg=Colors.TEXT_MAIN, font=Fonts.BODY, relief="flat", padx=10, pady=10, wrap="word", height=15)
        content_box.pack(fill="both", expand=True, pady=(0, 12))

        # Populate details
        txt = []
        txt.append("=== TRIGGER PATTERN ===")
        txt.append(lesson.trigger_pattern or "N/A")
        txt.append("\n=== RECOMMENDED STRATEGY ===")
        txt.append(lesson.recommended_strategy or "N/A")

        if lesson.anti_patterns:
            txt.append("\n=== ANTI-PATTERNS & PITFALLS ===")
            for ap in lesson.anti_patterns:
                txt.append(f"• {ap}")

        if lesson.context_conditions:
            txt.append("\n=== CONTEXT CONDITIONS ===")
            for k, v in lesson.context_conditions.items():
                txt.append(f"• {k}: {v}")

        if lesson.evidence_history:
            txt.append("\n=== VERIFICATION EVIDENCE ===")
            for ev in lesson.evidence_history:
                txt.append(f"• Passed: {ev.passed} (Score: {ev.confidence_score:.2f}) [{ev.verification_type}] {ev.evidence_snippet}")

        if lesson.provenance:
            txt.append("\n=== PROVENANCE & ORIGIN ===")
            txt.append(f"Source: {lesson.provenance.source_agent or 'Unknown'} · Session: {lesson.provenance.session_id or 'N/A'}")
            if lesson.provenance.origin_project_ids:
                txt.append(f"Origin Projects: {', '.join(lesson.provenance.origin_project_ids)}")

        content_box.insert("1.0", "\n".join(txt))
        content_box.configure(state="disabled")

        # Action buttons
        btn_row = tk.Frame(pad_f, bg=Colors.BG_DARK)
        btn_row.pack(fill="x", side="bottom")

        ttk.Button(btn_row, text="Close", command=self.close).pack(side="right")

        if self.on_delete:
            ttk.Button(btn_row, text="Delete Lesson", style="Danger.TButton", command=self._delete).pack(side="left")

        if self.on_modify:
            status_txt = "Deactivate" if lesson.is_active else "Activate"
            ttk.Button(btn_row, text=status_txt, command=self._toggle_active).pack(side="left", padx=(8, 0))

    def _toggle_active(self):
        new_state = not self.lesson.is_active
        reason = f"User {'activated' if new_state else 'deactivated'} lesson"
        if self.on_modify:
            self.on_modify(self.lesson.id, {"is_active": new_state}, reason)
        self.close()

    def _delete(self):
        ConfirmActionDialog(
            self,
            title="Delete Verified Lesson",
            message=f"Are you sure you want to delete lesson '{self.lesson.title}'? An immutable rollback checkpoint will be recorded.",
            on_confirm=lambda r: self._do_delete(r),
            destructive=True,
        )

    def _do_delete(self, reason: str):
        if self.on_delete:
            self.on_delete(self.lesson.id, reason)
        self.close()


class UninstallDialog(BaseDialog):
    """Complete uninstallation preview and confirmation dialog (Part E)."""

    def __init__(self, parent: tk.Widget, plan: UninstallPlan, on_execute: Callable[[bool, bool], None]):
        super().__init__(parent, "Uninstall EvoDev Application & State", width=620, height=520)
        self.plan = plan
        self.on_execute = on_execute

        pad_f = tk.Frame(self, bg=Colors.BG_DARK, padx=20, pady=16)
        pad_f.pack(fill="both", expand=True)

        tk.Label(pad_f, text="⚠️ UNINSTALL EVODEV", font=Fonts.HEADER_SMALL, bg=Colors.BG_DARK, fg=Colors.STATUS_RED).pack(anchor="w")
        tk.Label(
            pad_f,
            text="Review all resources scheduled for removal. User-owned external .vxp files are strictly preserved.",
            font=Fonts.SMALL,
            bg=Colors.BG_DARK,
            fg=Colors.TEXT_MUTED,
            wraplength=580,
            justify="left",
        ).pack(anchor="w", pady=(2, 10))

        # Preview listbox/text
        text_f = tk.Text(pad_f, bg=Colors.SURFACE, fg=Colors.TEXT_MAIN, font=Fonts.CODE_SMALL, relief="flat", padx=10, pady=10, wrap="word", height=13)
        text_f.pack(fill="both", expand=True, pady=(0, 10))

        lines = []
        lines.append("=== 1. EVODEV APPLICATION & DATABASE FILES TO REMOVE ===")
        for item in self.plan.items_to_remove:
            lines.append(f"• [{item.category.upper()}] {item.path}")
            lines.append(f"  Description: {item.description}")

        if self.plan.integrations_to_clean:
            lines.append("\n=== 2. INTEGRATION ENTRIES TO CLEAN (EVODEV KEYS ONLY) ===")
            for c in self.plan.integrations_to_clean:
                lines.append(f"• [{c.agent_name}] Key '{c.entry_key}' in {c.config_path}")

        lines.append("\n=== 3. USER FILES PRESERVED (NEVER TOUCHED) ===")
        if self.plan.preserved_items:
            for p in self.plan.preserved_items:
                lines.append(f"• {p.path} ({p.reason})")
        else:
            lines.append("• All external .vxp archives and unrelated tools configurations remain untouched.")

        lines.append(f"\n=== 4. PACKAGE REMOVAL INSTRUCTIONS ===")
        lines.append(f"Command: {self.plan.package_removal_command}")

        text_f.insert("1.0", "\n".join(lines))
        text_f.configure(state="disabled")

        # Options checkboxes
        self.backup_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            pad_f,
            text="Create backup ZIP of database & profiles before deletion (Recommended)",
            variable=self.backup_var,
            bg=Colors.BG_DARK,
            fg=Colors.STATUS_GREEN,
            selectcolor=Colors.SURFACE,
            activebackground=Colors.BG_DARK,
            activeforeground=Colors.STATUS_GREEN,
            font=Fonts.BODY_BOLD,
        ).pack(anchor="w", pady=(2, 2))

        self.dry_run_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            pad_f,
            text="Dry run only (Simulate and verify without modifying any files)",
            variable=self.dry_run_var,
            bg=Colors.BG_DARK,
            fg=Colors.TEXT_MAIN,
            selectcolor=Colors.SURFACE,
            activebackground=Colors.BG_DARK,
            activeforeground=Colors.ACCENT_CYAN,
            font=Fonts.BODY,
        ).pack(anchor="w", pady=(0, 10))

        # Bottom buttons
        btn_row = tk.Frame(pad_f, bg=Colors.BG_DARK)
        btn_row.pack(fill="x", side="bottom")

        ttk.Button(btn_row, text="Cancel", command=self.close).pack(side="right", padx=(8, 0))
        ttk.Button(btn_row, text="Confirm Uninstallation", style="Danger.TButton", command=self._submit).pack(side="right")

    def _submit(self):
        dry_run = self.dry_run_var.get()
        backup = self.backup_var.get()
        self.close()
        self.on_execute(backup, dry_run)
