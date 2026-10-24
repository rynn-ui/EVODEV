"""Metric card component displaying a key performance indicator with label and hint."""

import tkinter as tk
from tkinter import ttk
from typing import Optional

from evodev.gui.theme import Colors, Fonts


class MetricCard(tk.Frame):
    """Card widget featuring large stat value, label, and contextual hint."""

    def __init__(
        self,
        parent: tk.Widget,
        label: str,
        initial_value: str = "0",
        hint: str = "",
        value_color: str = Colors.ACCENT_CYAN,
        width: int = 180,
        height: int = 110,
    ):
        super().__init__(
            parent,
            bg=Colors.SURFACE,
            highlightbackground=Colors.BORDER,
            highlightthickness=1,
            padx=14,
            pady=12,
            width=width,
            height=height,
        )
        self.pack_propagate(False)

        self._label_var = tk.StringVar(value=label.upper())
        self._value_var = tk.StringVar(value=initial_value)
        self._hint_var = tk.StringVar(value=hint)
        self._val_color = value_color

        # Top label
        lbl = tk.Label(
            self,
            textvariable=self._label_var,
            bg=Colors.SURFACE,
            fg=Colors.TEXT_MUTED,
            font=Fonts.SMALL_BOLD,
            anchor="w",
        )
        lbl.pack(fill="x", side="top")

        # Value
        self.val_label = tk.Label(
            self,
            textvariable=self._value_var,
            bg=Colors.SURFACE,
            fg=value_color,
            font=Fonts.STAT_VALUE,
            anchor="w",
        )
        self.val_label.pack(fill="x", side="top", pady=(2, 2))

        # Hint
        if hint:
            hint_lbl = tk.Label(
                self,
                textvariable=self._hint_var,
                bg=Colors.SURFACE,
                fg=Colors.TEXT_DIM,
                font=Fonts.SMALL,
                anchor="w",
            )
            hint_lbl.pack(fill="x", side="bottom")

    def set_value(self, value: str, color: Optional[str] = None) -> None:
        """Update displayed stat value and optionally its color."""
        self._value_var.set(value)
        if color:
            self.val_label.configure(fg=color)

    def set_hint(self, hint: str) -> None:
        """Update contextual hint."""
        self._hint_var.set(hint)
