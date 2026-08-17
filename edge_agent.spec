# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: pacchetto portable EdgeAgent (onedir, senza console).

Build: .venv\\Scripts\\python.exe -m PyInstaller edge_agent.spec --noconfirm
(oppure build_exe.bat, che copia anche config/asset accanto all'exe).
"""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# config.ini di default dentro il bundle: il bootstrap lo ricopia accanto
# all'exe se l'utente lo cancella per errore.
datas = [("edge-agent/config.ini", "defaults")]
# qt_material carica template XML/CSS da file: vanno raccolti esplicitamente.
datas += collect_data_files("qt_material")

hiddenimports = []
hiddenimports += collect_submodules("langchain_google_genai")
hiddenimports += collect_submodules("langchain_openai")

a = Analysis(
    ["edge-agent/edge_agent.py"],
    pathex=["edge-agent", "."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "IPython", "streamlit", "pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="EdgeAgent",
    debug=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="EdgeAgent",
)
