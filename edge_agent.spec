# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: pacchetto portable EdgeAgent (onedir, senza console).

Pipeline supportata: build_exe.bat (build + copie top-level + zip datato).
Lo spec da solo produce comunque un bundle avviabile: config.ini, env.template
e assets sono nei datas e il bootstrap li semina accanto all'exe al primo avvio.
"""

from PyInstaller.utils.hooks import collect_submodules

# Default dentro il bundle: il bootstrap li semina/ripristina accanto all'exe.
datas = [
    ("src/edge-agent/config.ini", "defaults"),
    ("src/edge-agent/defaults/env.template", "defaults"),
    ("src/edge-agent/assets", "assets"),
    # Catalogo prompt LLM: il loader preferisce la copia accanto all'exe
    # (creata da build_exe.bat) e usa questa come fallback.
    ("prompts/*.json", "prompts"),
]

# Le icone sono SVG (assets/icons, già nei datas): QtSvg e i suoi plugin vanno nel pacchetto.
hiddenimports = ["PyQt6.QtSvg"]
hiddenimports += collect_submodules("langchain_google_genai")
hiddenimports += collect_submodules("langchain_openai")

a = Analysis(
    ["src/edge-agent/edge_agent.py"],
    pathex=["src/edge-agent", "src", "."],
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
