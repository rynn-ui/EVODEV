# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification file for EvoDev 2.0 Native Windows Desktop GUI and CLI."""

from pathlib import Path
import sys

block_cipher = None

repo_root = Path.cwd().resolve()

a = Analysis(
    ['evodev/gui/__main__.py'],
    pathex=[str(repo_root)],
    binaries=[],
    datas=[
        ('evodev/dashboard/static', 'evodev/dashboard/static'),
    ],
    hiddenimports=[
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
        'tkinter.filedialog',
        'evodev',
        'evodev.gui',
        'evodev.gui.app',
        'evodev.gui.theme',
        'evodev.gui.workers',
        'evodev.gui.views',
        'evodev.gui.views.overview_view',
        'evodev.gui.views.inspector_view',
        'evodev.gui.views.lessons_view',
        'evodev.gui.views.strategies_view',
        'evodev.gui.views.experiences_view',
        'evodev.gui.views.benchmarks_view',
        'evodev.gui.views.connectors_view',
        'evodev.gui.views.doctor_view',
        'evodev.gui.views.uninstall_view',
        'evodev.gui.components',
        'evodev.gui.components.metric_card',
        'evodev.gui.components.scrollable_frame',
        'evodev.gui.components.dialogs',
        'evodev.connectors',
        'evodev.connectors.contract',
        'evodev.connectors.manager',
        'evodev.connectors.base',
        'evodev.connectors.opencode',
        'evodev.connectors.gemini',
        'evodev.connectors.kilocode',
        'evodev.connectors.generic',
        'evodev.connectors.opencode_mcp',
        'evodev.lifecycle',
        'evodev.lifecycle.uninstaller',
        'evodev.storage',
        'evodev.storage.db',
        'evodev.storage.migrations',
        'evodev.storage.repositories',
        'evodev.learning',
        'evodev.retrieval',
        'evodev.profiles',
        'evodev.security',
        'evodev.evaluation',
        'evodev.collector',
        'evodev.cli.main',
        'typer',
        'pydantic',
        'rich',
        'cryptography',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='EvoDevGUI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='EvoDev',
)
