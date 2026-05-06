# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


project_dir = Path(SPECPATH)
datas = []

for name in ("requirements.txt",):
    path = project_dir / name
    if path.exists():
        datas.append((str(path), "."))

for pattern in ("*.md", "*.json", "*.png"):
    for path in project_dir.glob(pattern):
        datas.append((str(path), "."))


a = Analysis(
    ["waterRPA_GUI.py"],
    pathex=[str(project_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "PIL",
        "PIL.Image",
        "cv2",
        "pyautogui",
        "pyperclip",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="WaterRPA",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
