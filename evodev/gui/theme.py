"""Theme and style configuration for EvoDev desktop application."""

import tkinter as tk
from tkinter import ttk


class Colors:
    """Modern dark theme palette for Windows desktop."""

    BG_DARK = "#0f172a"        # Deep slate background
    SURFACE = "#1e293b"        # Card and container surface
    SURFACE_HOVER = "#2d3c52"  # Hover state for items
    SURFACE_LIGHT = "#334155"  # Card borders and subtle separators
    SIDEBAR = "#0b1120"        # Darker sidebar background

    TEXT_MAIN = "#f8fafc"      # Primary white-slate text
    TEXT_MUTED = "#94a3b8"     # Secondary muted text
    TEXT_DIM = "#64748b"       # Hints and placeholders

    ACCENT_CYAN = "#06b6d4"    # Primary brand accent
    ACCENT_TEAL = "#14b8a6"    # Verified / success accent
    STATUS_GREEN = "#10b981"   # Passing tests / verified
    STATUS_YELLOW = "#f59e0b"  # Warning / candidate lessons
    STATUS_RED = "#ef4444"     # Error / regression / danger
    ACCENT_BLUE = "#3b82f6"    # Information

    BORDER = "#334155"
    INPUT_BG = "#0f172a"
    INPUT_FG = "#f8fafc"
    BUTTON_BG = "#1e293b"
    BUTTON_PRIMARY = "#0284c7"
    BUTTON_PRIMARY_HOVER = "#0369a1"
    BUTTON_DANGER = "#b91c1c"


class Fonts:
    """Typography hierarchy for desktop UI."""

    FAMILY = "Segoe UI"
    HEADER_LARGE = ("Segoe UI", 18, "bold")
    HEADER_MEDIUM = ("Segoe UI", 14, "bold")
    HEADER_SMALL = ("Segoe UI", 11, "bold")
    BODY = ("Segoe UI", 10)
    BODY_BOLD = ("Segoe UI", 10, "bold")
    SMALL = ("Segoe UI", 9)
    SMALL_BOLD = ("Segoe UI", 9, "bold")
    CODE = ("Consolas", 10)
    CODE_SMALL = ("Consolas", 9)
    STAT_VALUE = ("Segoe UI", 22, "bold")


def apply_theme(root: tk.Tk) -> ttk.Style:
    """Apply modern dark styles to Tk root and ttk widget hierarchy."""
    root.configure(bg=Colors.BG_DARK)

    style = ttk.Style(root)
    # Use 'clam' as cross-platform baseline for complete color control
    try:
        style.theme_use("clam")
    except Exception:
        pass

    # Generic Frame styles
    style.configure("TFrame", background=Colors.BG_DARK)
    style.configure("Surface.TFrame", background=Colors.SURFACE)
    style.configure("Card.TFrame", background=Colors.SURFACE, relief="solid", borderwidth=1)
    style.configure("Sidebar.TFrame", background=Colors.SIDEBAR)
    style.configure("Topbar.TFrame", background=Colors.SURFACE)

    # Generic Label styles
    style.configure(
        "TLabel",
        background=Colors.BG_DARK,
        foreground=Colors.TEXT_MAIN,
        font=Fonts.BODY,
    )
    style.configure(
        "Surface.TLabel",
        background=Colors.SURFACE,
        foreground=Colors.TEXT_MAIN,
        font=Fonts.BODY,
    )
    style.configure(
        "Muted.TLabel",
        background=Colors.SURFACE,
        foreground=Colors.TEXT_MUTED,
        font=Fonts.SMALL,
    )
    style.configure(
        "Title.TLabel",
        background=Colors.BG_DARK,
        foreground=Colors.TEXT_MAIN,
        font=Fonts.HEADER_LARGE,
    )
    style.configure(
        "Section.TLabel",
        background=Colors.SURFACE,
        foreground=Colors.TEXT_MAIN,
        font=Fonts.HEADER_MEDIUM,
    )
    style.configure(
        "SubSection.TLabel",
        background=Colors.SURFACE,
        foreground=Colors.TEXT_MAIN,
        font=Fonts.HEADER_SMALL,
    )
    style.configure(
        "StatVal.TLabel",
        background=Colors.SURFACE,
        foreground=Colors.ACCENT_CYAN,
        font=Fonts.STAT_VALUE,
    )
    style.configure(
        "StatValGreen.TLabel",
        background=Colors.SURFACE,
        foreground=Colors.STATUS_GREEN,
        font=Fonts.STAT_VALUE,
    )
    style.configure(
        "StatValYellow.TLabel",
        background=Colors.SURFACE,
        foreground=Colors.STATUS_YELLOW,
        font=Fonts.STAT_VALUE,
    )
    style.configure(
        "StatLabel.TLabel",
        background=Colors.SURFACE,
        foreground=Colors.TEXT_MUTED,
        font=Fonts.SMALL_BOLD,
    )
    style.configure(
        "StatHint.TLabel",
        background=Colors.SURFACE,
        foreground=Colors.TEXT_DIM,
        font=Fonts.SMALL,
    )

    # Sidebar Navigation Buttons
    style.configure(
        "Nav.TButton",
        background=Colors.SIDEBAR,
        foreground=Colors.TEXT_MAIN,
        font=Fonts.BODY_BOLD,
        borderwidth=0,
        anchor="w",
        padding=(14, 8),
    )
    style.map(
        "Nav.TButton",
        background=[("active", Colors.SURFACE_HOVER), ("pressed", Colors.SURFACE_LIGHT)],
        foreground=[("active", Colors.ACCENT_CYAN)],
    )

    style.configure(
        "ActiveNav.TButton",
        background=Colors.SURFACE_LIGHT,
        foreground=Colors.ACCENT_CYAN,
        font=Fonts.BODY_BOLD,
        borderwidth=0,
        anchor="w",
        padding=(14, 8),
    )
    style.map(
        "ActiveNav.TButton",
        background=[("active", Colors.SURFACE_LIGHT)],
        foreground=[("active", Colors.ACCENT_CYAN)],
    )

    # Regular Buttons
    style.configure(
        "TButton",
        background=Colors.SURFACE_LIGHT,
        foreground=Colors.TEXT_MAIN,
        font=Fonts.BODY_BOLD,
        padding=(12, 6),
        borderwidth=0,
    )
    style.map(
        "TButton",
        background=[("active", Colors.SURFACE_HOVER), ("pressed", Colors.SURFACE)],
        foreground=[("active", Colors.TEXT_MAIN)],
    )

    # Primary Action Button
    style.configure(
        "Primary.TButton",
        background=Colors.BUTTON_PRIMARY,
        foreground="#ffffff",
        font=Fonts.BODY_BOLD,
        padding=(14, 7),
        borderwidth=0,
    )
    style.map(
        "Primary.TButton",
        background=[("active", Colors.BUTTON_PRIMARY_HOVER), ("pressed", Colors.BUTTON_PRIMARY)],
        foreground=[("active", "#ffffff")],
    )

    # Danger Button
    style.configure(
        "Danger.TButton",
        background=Colors.BUTTON_DANGER,
        foreground="#ffffff",
        font=Fonts.BODY_BOLD,
        padding=(12, 6),
        borderwidth=0,
    )
    style.map(
        "Danger.TButton",
        background=[("active", "#dc2626"), ("pressed", "#991b1b")],
        foreground=[("active", "#ffffff")],
    )

    # Success / Connect Button
    style.configure(
        "Success.TButton",
        background=Colors.STATUS_GREEN,
        foreground="#ffffff",
        font=Fonts.BODY_BOLD,
        padding=(12, 6),
        borderwidth=0,
    )
    style.map(
        "Success.TButton",
        background=[("active", "#059669"), ("pressed", "#047857")],
        foreground=[("active", "#ffffff")],
    )

    # Launch Button
    style.configure(
        "Launch.TButton",
        background=Colors.ACCENT_CYAN,
        foreground="#0b1120",
        font=Fonts.BODY_BOLD,
        padding=(12, 6),
        borderwidth=0,
    )
    style.map(
        "Launch.TButton",
        background=[("active", "#22d3ee"), ("pressed", "#0891b2")],
        foreground=[("active", "#0b1120")],
    )

    # Outline Button
    style.configure(
        "Outline.TButton",
        background=Colors.SURFACE,
        foreground=Colors.TEXT_MAIN,
        font=Fonts.BODY,
        padding=(10, 5),
        borderwidth=1,
    )
    style.map(
        "Outline.TButton",
        background=[("active", Colors.SURFACE_HOVER)],
        foreground=[("active", Colors.ACCENT_CYAN)],
    )

    # Small Sub-tab buttons
    style.configure(
        "SubTab.TButton",
        background=Colors.SURFACE,
        foreground=Colors.TEXT_MUTED,
        font=Fonts.SMALL_BOLD,
        padding=(10, 5),
        borderwidth=0,
    )
    style.map(
        "SubTab.TButton",
        background=[("active", Colors.SURFACE_HOVER)],
        foreground=[("active", Colors.TEXT_MAIN)],
    )

    style.configure(
        "ActiveSubTab.TButton",
        background=Colors.SURFACE_LIGHT,
        foreground=Colors.ACCENT_CYAN,
        font=Fonts.SMALL_BOLD,
        padding=(10, 5),
        borderwidth=0,
    )

    # Treeview (Data Tables)
    style.configure(
        "Treeview",
        background=Colors.SURFACE,
        foreground=Colors.TEXT_MAIN,
        fieldbackground=Colors.SURFACE,
        rowheight=28,
        font=Fonts.BODY,
        borderwidth=0,
    )
    style.map(
        "Treeview",
        background=[("selected", Colors.SURFACE_LIGHT)],
        foreground=[("selected", Colors.ACCENT_CYAN)],
    )
    style.configure(
        "Treeview.Heading",
        background=Colors.BG_DARK,
        foreground=Colors.TEXT_MUTED,
        font=Fonts.SMALL_BOLD,
        padding=(6, 6),
        borderwidth=1,
        relief="flat",
    )
    style.map(
        "Treeview.Heading",
        background=[("active", Colors.SURFACE_LIGHT)],
        foreground=[("active", Colors.TEXT_MAIN)],
    )

    # Combobox
    style.configure(
        "TCombobox",
        background=Colors.SURFACE,
        foreground=Colors.TEXT_MAIN,
        fieldbackground=Colors.SURFACE,
        arrowcolor=Colors.TEXT_MUTED,
        font=Fonts.BODY,
        padding=4,
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", Colors.SURFACE)],
        foreground=[("readonly", Colors.TEXT_MAIN)],
    )

    # Entry
    style.configure(
        "TEntry",
        fieldbackground=Colors.INPUT_BG,
        foreground=Colors.INPUT_FG,
        insertcolor=Colors.TEXT_MAIN,
        font=Fonts.BODY,
        padding=6,
    )

    # Scrollbars
    style.configure(
        "Vertical.TScrollbar",
        background=Colors.SURFACE_LIGHT,
        troughcolor=Colors.BG_DARK,
        bordercolor=Colors.BG_DARK,
        arrowcolor=Colors.TEXT_MUTED,
        relief="flat",
    )
    style.map(
        "Vertical.TScrollbar",
        background=[("active", Colors.TEXT_DIM)],
    )

    # Notebook Tabs
    style.configure(
        "TNotebook",
        background=Colors.SURFACE,
        borderwidth=0,
    )
    style.configure(
        "TNotebook.Tab",
        background=Colors.SURFACE,
        foreground=Colors.TEXT_MUTED,
        font=Fonts.SMALL_BOLD,
        padding=(12, 6),
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", Colors.SURFACE_LIGHT), ("active", Colors.SURFACE_HOVER)],
        foreground=[("selected", Colors.ACCENT_CYAN), ("active", Colors.TEXT_MAIN)],
    )

    # Progressbar
    style.configure(
        "Horizontal.TProgressbar",
        troughcolor=Colors.SURFACE_LIGHT,
        background=Colors.ACCENT_CYAN,
        relief="flat",
        borderwidth=0,
    )

    return style
