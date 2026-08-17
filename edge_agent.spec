# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: pacchetto portable EdgeAgent (onedir, senza console).

Pipeline supportata: build_exe.bat (build + copie top-level + zip datato).
Lo spec da solo produce comunque un bundle avviabile: config.ini, env.template
e assets sono nei datas e il bootstrap li semina accanto all'exe al primo avvio.
"""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Default dentro il bundle: il bootstrap li semina/ripristina accanto all'exe.
datas = [
    ("edge-agent/config.ini", "defaults"),
    ("edge-agent/defaults/env.template", "defaults"),
    ("edge-agent/assets", "assets"),
    # Catalogo prompt LLM: il loader preferisce la copia accanto all'exe
    # (creata da build_exe.bat) e usa questa come fallback.
    ("prompts/*.json", "prompts"),
]
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
    # pyarrow: extra opzionale di pandas mai importato dal progetto (81MB).
    # NON escludere scipy: imagehash.phash lo importa lazy a runtime.
    excludes=["tkinter", "matplotlib", "IPython", "streamlit", "pytest", "pyarrow"],
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
