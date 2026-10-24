"""Responsive vertically scrollable frame powered by Tkinter Canvas."""

import tkinter as tk
from tkinter import ttk

from evodev.gui.theme import Colors


class ScrollableFrame(tk.Frame):
    """Canvas-backed scrollable container with automatic layout resizing."""

    def __init__(self, parent: tk.Widget, bg: str = Colors.BG_DARK, **kwargs):
        super().__init__(parent, bg=bg, **kwargs)

        self.canvas = tk.Canvas(
            self,
            bg=bg,
            highlightthickness=0,
            borderwidth=0,
        )
        self.scrollbar = ttk.Scrollbar(
            self,
            orient="vertical",
            command=self.canvas.yview,
            style="Vertical.TScrollbar",
        )
        self.scrollable_content = tk.Frame(self.canvas, bg=bg)

        self.canvas_window = self.canvas.create_window(
            (0, 0),
            window=self.scrollable_content,
            anchor="nw",
        )

        self.canvas.configure(xscrollcommand=None, yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        self.scrollable_content.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self._bind_mousewheel(self)

    def _on_frame_configure(self, event=None):
        """Update canvas scroll region to encompass content."""
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        """Match content frame width to canvas width for responsive wrapping."""
        self.canvas.itemconfig(self.canvas_window, width=event.width)

    def _bind_mousewheel(self, widget: tk.Widget):
        """Recursively bind mouse wheel events to smoothly scroll."""
        widget.bind("<MouseWheel>", self._on_mousewheel, add="+")
        for child in widget.winfo_children():
            self._bind_mousewheel(child)

    def _on_mousewheel(self, event):
        """Handle Windows mouse wheel scroll delta."""
        if self.canvas.winfo_exists():
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
