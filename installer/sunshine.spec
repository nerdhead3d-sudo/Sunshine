# PyInstaller spec for Sunshine. Build with:
#   pyinstaller installer/sunshine.spec --noconfirm
# from the repo root (paths below are relative to the repo root, not to
# this file, since PyInstaller resolves them against the current working
# directory it's invoked from).
#
# --onedir (not --onefile): Sunshine pulls in heavy native-extension
# libraries (torch, onnxruntime, opencv) and downloads further models at
# runtime into config.LOCAL_MODEL_DIR — a single huge self-extracting exe
# would re-unpack itself into a temp dir on every launch for no benefit
# here, since the app already needs a real folder on disk for its models.
#
# Sprites are built at first run (main.py:ensure_sprites) from the bundled
# source artwork — pet/assets/cat3d/ (3D renders) or the 2D sheet
# pet/assets/sheets/black_cat.png — and recognition models are
# downloaded/trained at runtime, so neither the generated sprites nor those
# models are bundled; only the source code, that artwork and the
# hand-written mood model weights (pet/mood/model/<lang>/*.pt + *.json),
# which never change without a retrain.

import sys
from pathlib import Path

import cv2

block_cipher = None
REPO_ROOT = Path.cwd()
CV2_DATA_DIR = str(Path(cv2.__file__).resolve().parent / "data")

datas = [
    (str(REPO_ROOT / "pet" / "mood" / "model"), "pet/mood/model"),
    # Non-.py data files PyInstaller's import analysis can't discover on
    # its own (it only follows actual Python imports): the SQLite schema
    # read at runtime by pet/memory/store.py, and the Haar cascade XML
    # files (cv2.data.haarcascades) the cat recognizer loads by path —
    # PyInstaller's cv2 hook brings in cv2/data/__init__.py but not the
    # actual .xml files sitting next to it, confirmed missing in a real
    # build (see CLAUDE.md "Programma di installazione Windows").
    (str(REPO_ROOT / "pet" / "memory" / "schema.sql"), "pet/memory"),
    (str(REPO_ROOT / "pet" / "assets" / "sheets"), "pet/assets/sheets"),
    (str(REPO_ROOT / "pet" / "assets" / "cat3d"), "pet/assets/cat3d"),
    (CV2_DATA_DIR, "cv2/data"),
]

a = Analysis(
    [str(REPO_ROOT / "main.py")],
    pathex=[str(REPO_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "pet.openai_client",
        "pet.ollama_client",
        "pet.local_llm_client",
        "installer.download_models",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Sunshine",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # no terminal window — same as pythonw.exe via the .vbs launcher today
    icon=None,      # TODO: point at an .ico once pet/assets has one
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="Sunshine",
)
