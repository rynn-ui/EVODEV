"""Self-Improving Skill Engine view for managing reusable procedures, versions, and evaluations."""

import json
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Optional

from evodev.gui.components.scrollable_frame import ScrollableFrame
from evodev.gui.theme import Colors, Fonts
from evodev.models.skills import Skill, SkillStatus
from evodev.skills.renderer import SkillRenderer


class SkillsView(tk.Frame):
    """Self-improving skills inspection, versioning, evaluation, and rendering pane."""

    def __init__(self, parent: tk.Widget, app: Any):
        super().__init__(parent, bg=Colors.BG_DARK)
        self.app = app
        self.renderer = SkillRenderer()
        self.selected_skill: Optional[Skill] = None

        self.scroll = ScrollableFrame(self, bg=Colors.BG_DARK)
        self.scroll.pack(fill="both", expand=True)
        content = self.scroll.scrollable_content

        card = tk.Frame(content, bg=Colors.SURFACE, highlightbackground=Colors.BORDER, highlightthickness=1, padx=16, pady=14)
        card.pack(fill="both", expand=True, padx=16, pady=16)

        # Header & Actions
        head = tk.Frame(card, bg=Colors.SURFACE)
        head.pack(fill="x", pady=(0, 10))

        tk.Label(head, text="Self-Improving Skills & Procedures", font=Fonts.HEADER_MEDIUM, bg=Colors.SURFACE, fg=Colors.TEXT_MAIN).pack(side="left")

        btn_row = tk.Frame(head, bg=Colors.SURFACE)
        btn_row.pack(side="right")
        ttk.Button(btn_row, text="+ New Skill", style="Primary.TButton", command=self._open_new_skill_dialog).pack(side="left", padx=(0, 6))
        ttk.Button(btn_row, text="⏱️ Evaluate", command=self._open_evaluate_dialog).pack(side="left", padx=(0, 6))
        ttk.Button(btn_row, text="⤴️ Propose Version", command=self._open_propose_dialog).pack(side="left", padx=(0, 6))
        ttk.Button(btn_row, text="⏪ Rollback", command=self._rollback_skill).pack(side="left")

        # Skills Table
        cols = ("name", "version", "status", "success_rate", "evaluations", "category")
        self.tree = ttk.Treeview(card, columns=cols, show="headings", height=8)
        self.tree.heading("name", text="Skill Name")
        self.tree.heading("version", text="Version")
        self.tree.heading("status", text="Status")
        self.tree.heading("success_rate", text="Success Rate")
        self.tree.heading("evaluations", text="Evaluations")
        self.tree.heading("category", text="Category")

        self.tree.column("name", width=220)
        self.tree.column("version", width=70, anchor="center")
        self.tree.column("status", width=90, anchor="center")
        self.tree.column("success_rate", width=100, anchor="center")
        self.tree.column("evaluations", width=90, anchor="center")
        self.tree.column("category", width=110, anchor="center")
        self.tree.pack(fill="x")

        self.tree.bind("<<TreeviewSelect>>", self._on_select_skill)

        # Multi-Format Rendering & Evaluation Preview Card
        render_card = tk.Frame(card, bg=Colors.SURFACE_LIGHT, padx=12, pady=10, highlightbackground=Colors.BORDER, highlightthickness=1)
        render_card.pack(fill="both", expand=True, pady=(12, 0))

        r_head = tk.Frame(render_card, bg=Colors.SURFACE_LIGHT)
        r_head.pack(fill="x", pady=(0, 8))

        self.preview_title = tk.Label(r_head, text="Skill Details & Cross-Agent Formats", font=Fonts.BODY_BOLD, bg=Colors.SURFACE_LIGHT, fg=Colors.TEXT_MAIN)
        self.preview_title.pack(side="left")

        self.format_var = tk.StringVar(value="markdown")
        fmt_row = tk.Frame(r_head, bg=Colors.SURFACE_LIGHT)
        fmt_row.pack(side="right")
        tk.Label(fmt_row, text="Format:", font=Fonts.SMALL_BOLD, bg=Colors.SURFACE_LIGHT, fg=Colors.TEXT_MUTED).pack(side="left", padx=(0, 6))

        for fmt, label in [("markdown", "Markdown"), ("mcp", "MCP Schema"), ("hermes", "Hermes Prompt")]:
            rb = ttk.Radiobutton(fmt_row, text=label, value=fmt, variable=self.format_var, command=self._render_preview)
            rb.pack(side="left", padx=4)

        self.preview_text = tk.Text(
            render_card,
            bg=Colors.BG_DARK,
            fg=Colors.TEXT_MAIN,
            font=Fonts.CODE,
            height=12,
            relief="flat",
            padx=10,
            pady=10,
            wrap="word",
        )
        self.preview_text.pack(fill="both", expand=True)

    def refresh(self) -> None:
        for row in self.tree.get_children():
            self.tree.delete(row)

        active = self.app.p_repo.get_active()
        p_id = active.profile_id if active else "default"

        skills = self.app.skill_repo.list_by_profile(p_id)
        for s in skills:
            rate = f"{s.success_rate * 100:.1f}%" if s.total_evaluations > 0 else "N/A"
            self.tree.insert(
                "",
                "end",
                iid=s.id,
                values=(
                    s.name,
                    f"v{s.current_version}",
                    s.status.value.upper(),
                    rate,
                    str(s.total_evaluations),
                    s.category,
                ),
            )

        if self.selected_skill:
            updated = self.app.skill_repo.get_by_id(self.selected_skill.id)
            if updated:
                self.selected_skill = updated
                self._render_preview()

    def _on_select_skill(self, event=None) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        skill_id = sel[0]
        skill = self.app.skill_repo.get_by_id(skill_id)
        if not skill:
            return
        self.selected_skill = skill
        self.preview_title.configure(text=f"Skill: {skill.name} (v{skill.current_version})")
        self._render_preview()

    def _render_preview(self) -> None:
        if not self.selected_skill:
            self.preview_text.delete("1.0", "end")
            self.preview_text.insert("end", "// Select a skill above to render its instructions, procedures, and formats.")
            return

        version_obj = self.app.skill_repo.get_version(self.selected_skill.id, self.selected_skill.current_version)
        fmt = self.format_var.get()

        if fmt == "mcp":
            content = json.dumps(self.renderer.render_mcp_tool_description(self.selected_skill, version_obj), indent=2)
        elif fmt == "hermes":
            content = self.renderer.render_hermes_prompt(self.selected_skill, version_obj)
        else:
            content = self.renderer.render_markdown(self.selected_skill, version_obj)

        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("end", content)

    def _open_new_skill_dialog(self) -> None:
        dlg = tk.Toplevel(self.app.root)
        dlg.title("Create Self-Improving Skill")
        dlg.geometry("520x460")
        dlg.configure(bg=Colors.BG_DARK)
        dlg.transient(self.app.root)
        dlg.grab_set()

        f = tk.Frame(dlg, bg=Colors.SURFACE, padx=16, pady=16)
        f.pack(fill="both", expand=True, padx=12, pady=12)

        tk.Label(f, text="Create Reusable Skill", font=Fonts.BODY_BOLD, bg=Colors.SURFACE, fg=Colors.TEXT_MAIN).pack(anchor="w", pady=(0, 10))

        tk.Label(f, text="Skill Name:", font=Fonts.SMALL_BOLD, bg=Colors.SURFACE, fg=Colors.TEXT_MUTED).pack(anchor="w")
        name_e = ttk.Entry(f)
        name_e.pack(fill="x", pady=(2, 8))

        tk.Label(f, text="Description:", font=Fonts.SMALL_BOLD, bg=Colors.SURFACE, fg=Colors.TEXT_MUTED).pack(anchor="w")
        desc_e = ttk.Entry(f)
        desc_e.pack(fill="x", pady=(2, 8))

        tk.Label(f, text="Category (e.g., refactoring, testing, debugging):", font=Fonts.SMALL_BOLD, bg=Colors.SURFACE, fg=Colors.TEXT_MUTED).pack(anchor="w")
        cat_e = ttk.Entry(f)
        cat_e.insert(0, "general")
        cat_e.pack(fill="x", pady=(2, 8))

        tk.Label(f, text="Initial Instructions & Procedures:", font=Fonts.SMALL_BOLD, bg=Colors.SURFACE, fg=Colors.TEXT_MUTED).pack(anchor="w")
        inst_txt = tk.Text(f, height=6, bg=Colors.BG_DARK, fg=Colors.TEXT_MAIN, font=Fonts.CODE)
        inst_txt.insert("1.0", "1. Check prerequisites\n2. Run verified procedure\n3. Validate outputs with tests")
        inst_txt.pack(fill="both", expand=True, pady=(2, 10))

        def _save():
            name = name_e.get().strip()
            desc = desc_e.get().strip()
            cat = cat_e.get().strip() or "general"
            instructions = inst_txt.get("1.0", "end").strip()

            if not name or not desc or not instructions:
                messagebox.showerror("Validation Error", "Name, description, and instructions are required.", parent=dlg)
                return

            try:
                skill = self.app.skill_engine.create_skill(
                    name=name,
                    description=desc,
                    initial_instructions=instructions,
                    category=cat,
                )
                dlg.destroy()
                self.refresh()
                messagebox.showinfo("Success", f"Created skill '{skill.name}'.", parent=self.app.root)
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=dlg)

        btn_row = tk.Frame(f, bg=Colors.SURFACE)
        btn_row.pack(fill="x")
        ttk.Button(btn_row, text="Cancel", command=dlg.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(btn_row, text="Create Skill", style="Primary.TButton", command=_save).pack(side="right")

    def _open_evaluate_dialog(self) -> None:
        if not self.selected_skill:
            messagebox.showwarning("Select Skill", "Please select a skill to evaluate.", parent=self.app.root)
            return

        dlg = tk.Toplevel(self.app.root)
        dlg.title(f"Evaluate Skill: {self.selected_skill.name}")
        dlg.geometry("420x260")
        dlg.configure(bg=Colors.BG_DARK)
        dlg.transient(self.app.root)
        dlg.grab_set()

        f = tk.Frame(dlg, bg=Colors.SURFACE, padx=16, pady=16)
        f.pack(fill="both", expand=True, padx=12, pady=12)

        tk.Label(f, text=f"Record Benchmark Evaluation (v{self.selected_skill.current_version})", font=Fonts.BODY_BOLD, bg=Colors.SURFACE, fg=Colors.TEXT_MAIN).pack(anchor="w", pady=(0, 10))

        success_var = tk.BooleanVar(value=True)
        cb_f = tk.Frame(f, bg=Colors.SURFACE)
        cb_f.pack(fill="x", pady=(0, 8))
        ttk.Radiobutton(cb_f, text="Verified Success", value=True, variable=success_var).pack(side="left", padx=(0, 12))
        ttk.Radiobutton(cb_f, text="Failure / Regression", value=False, variable=success_var).pack(side="left")

        tk.Label(f, text="Score (0.0 to 1.0):", font=Fonts.SMALL_BOLD, bg=Colors.SURFACE, fg=Colors.TEXT_MUTED).pack(anchor="w")
        score_e = ttk.Entry(f)
        score_e.insert(0, "1.0")
        score_e.pack(fill="x", pady=(2, 8))

        tk.Label(f, text="Task / Benchmark Notes:", font=Fonts.SMALL_BOLD, bg=Colors.SURFACE, fg=Colors.TEXT_MUTED).pack(anchor="w")
        notes_e = ttk.Entry(f)
        notes_e.insert(0, "Manual GUI benchmark trial")
        notes_e.pack(fill="x", pady=(2, 12))

        def _record():
            try:
                sc = float(score_e.get().strip())
                is_s = success_var.get()
                notes = notes_e.get().strip()
                res = self.app.skill_engine.evaluator.evaluate_version(
                    skill_id=self.selected_skill.id,
                    version=self.selected_skill.current_version,
                    trials=[(is_s, sc, notes)],
                )
                dlg.destroy()
                self.refresh()
                messagebox.showinfo("Evaluated", f"Evaluation recorded. Score: {res.score:.2f}", parent=self.app.root)
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=dlg)

        btn_row = tk.Frame(f, bg=Colors.SURFACE)
        btn_row.pack(fill="x")
        ttk.Button(btn_row, text="Cancel", command=dlg.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(btn_row, text="Record Evaluation", style="Primary.TButton", command=_record).pack(side="right")

    def _open_propose_dialog(self) -> None:
        if not self.selected_skill:
            messagebox.showwarning("Select Skill", "Please select a skill to propose an update.", parent=self.app.root)
            return

        dlg = tk.Toplevel(self.app.root)
        dlg.title(f"Propose Version for {self.selected_skill.name}")
        dlg.geometry("480x360")
        dlg.configure(bg=Colors.BG_DARK)
        dlg.transient(self.app.root)
        dlg.grab_set()

        f = tk.Frame(dlg, bg=Colors.SURFACE, padx=16, pady=16)
        f.pack(fill="both", expand=True, padx=12, pady=12)

        tk.Label(f, text=f"Propose New Version (Current: v{self.selected_skill.current_version})", font=Fonts.BODY_BOLD, bg=Colors.SURFACE, fg=Colors.TEXT_MAIN).pack(anchor="w", pady=(0, 10))

        tk.Label(f, text="New Version Tag (e.g. 1.1.0):", font=Fonts.SMALL_BOLD, bg=Colors.SURFACE, fg=Colors.TEXT_MUTED).pack(anchor="w")
        ver_e = ttk.Entry(f)
        ver_e.pack(fill="x", pady=(2, 8))

        tk.Label(f, text="Updated Instructions / Improvements:", font=Fonts.SMALL_BOLD, bg=Colors.SURFACE, fg=Colors.TEXT_MUTED).pack(anchor="w")
        inst_txt = tk.Text(f, height=6, bg=Colors.BG_DARK, fg=Colors.TEXT_MAIN, font=Fonts.CODE)
        inst_txt.pack(fill="both", expand=True, pady=(2, 10))

        def _propose():
            v_tag = ver_e.get().strip()
            new_inst = inst_txt.get("1.0", "end").strip()
            if not v_tag or not new_inst:
                messagebox.showerror("Error", "Version tag and instructions are required.", parent=dlg)
                return

            try:
                new_ver = self.app.skill_engine.propose_version(
                    skill_id=self.selected_skill.id,
                    version=v_tag,
                    instructions=new_inst,
                )
                dlg.destroy()
                self.refresh()
                messagebox.showinfo("Proposed", f"Created proposed version v{new_ver.version}.", parent=self.app.root)
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=dlg)

        btn_row = tk.Frame(f, bg=Colors.SURFACE)
        btn_row.pack(fill="x")
        ttk.Button(btn_row, text="Cancel", command=dlg.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(btn_row, text="Propose Version", style="Primary.TButton", command=_propose).pack(side="right")

    def _rollback_skill(self) -> None:
        if not self.selected_skill:
            return

        versions = self.app.skill_repo.list_versions(self.selected_skill.id)
        if len(versions) <= 1:
            messagebox.showinfo("Notice", "No earlier versions available for rollback.", parent=self.app.root)
            return

        earlier_ver = versions[-2].version if len(versions) >= 2 else versions[0].version
        if messagebox.askyesno("Confirm Rollback", f"Rollback skill '{self.selected_skill.name}' to version v{earlier_ver}?", parent=self.app.root):
            try:
                self.app.skill_engine.rollback_skill(self.selected_skill.id, earlier_ver)
                self.refresh()
                messagebox.showinfo("Success", f"Rolled back to v{earlier_ver}.", parent=self.app.root)
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=self.app.root)
