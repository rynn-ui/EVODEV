# Windows Packaging & Distribution Guide

EvoDev 2.0 provides multiple ways to run and distribute the native Windows desktop application and CLI tools:

1. **Development / Local Environment**: Direct execution via `pip install -e .` and `evodev gui` or `python -m evodev.gui`.
2. **Standard Pip Wheel**: Distribution via standard Python package wheels.
3. **Standalone Windows Executable**: Bundled portable executable package created using PyInstaller.

---

## 1. Prerequisites for Building Standalone Executables

Ensure you are working in Python 3.10+ on Windows with Tkinter available:

```powershell
python -c "import tkinter; print('Tkinter version:', tkinter.TkVersion)"
```

Install the project dependencies and PyInstaller:

```powershell
pip install -e .
pip install pyinstaller
```

---

## 2. Building with PyInstaller

EvoDev includes an explicit build specification file: `evodev.spec`.

To build the standalone bundle:

```powershell
pyinstaller evodev.spec --clean --noconfirm
```

This outputs a bundled application directory at:
```text
dist\EvoDev\
├── EvoDevGUI.exe       # Native Windows desktop application binary
├── _internal\          # Bundled Python runtime, Tcl/Tk DLLs, and dependencies
```

### Build Options
- **One-Folder Mode (Recommended for Tkinter)**: The provided `evodev.spec` generates a `dist\EvoDev` directory. This loads significantly faster and ensures Windows Antivirus does not delay decompression on startup.
- **Single-File Executable**: If a single `.exe` is preferred, run:
  ```powershell
  pyinstaller --noconfirm --onedir --windowed --add-data "evodev/dashboard/static;evodev/dashboard/static" --name "EvoDevGUI" evodev/gui/__main__.py
  ```

---

## 3. Verifying the Packaged Build

Once built, verify the application launches properly:

```powershell
.\dist\EvoDev\EvoDevGUI.exe
```

The desktop application will display:
- Dark slate theme (`#0f172a`, `#1e293b`)
- Navigation sidebar (Overview, Inspector, Lessons, Strategies, Experiences, Benchmarks, Connectors, System Diagnostics, Safe Uninstall)
- Active profile metrics and connector health

---

## 4. Uninstallation of Packaged vs Pip Installations

- When installed via `pip install -e .`, EvoDev provides the `evodev uninstall` CLI command and the desktop GUI **Safe Uninstall** dialog.
- For packaged portable folders (`dist\EvoDev`), running `evodev uninstall` cleans the managed database (`~/.evodev/evodev.db`), local configuration (`~/.evodev/config.json`), and connector registrations (e.g. in OpenCode or Gemini).
- User-owned `.vxp` archives outside EvoDev's managed directory are **never** touched or deleted.
