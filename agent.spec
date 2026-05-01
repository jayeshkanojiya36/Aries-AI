# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all
import os

block_cipher = None

# -------------------------
# Base Data Files
# -------------------------

datas = [
    ('Tools', 'Tools'),          # Folder include
    ('prompts.py', '.'),         # Prompt file
]

# Include .env only if exists
if os.path.exists('.env'):
    datas.append(('.env', '.'))

binaries = []

hiddenimports = [
    'pyautogui',
    'pyscreeze',
    'pymsgbox',
    'pytweening',
    'mouseinfo',
    'PIL',
    'PIL._tkinter_finder',
]

# -------------------------
# LiveKit + mem0 Packages
# -------------------------

for module in [
    'livekit',
    'livekit.rtc',
    'mem0',
    'mem0.memory',
    'mem0.vector_stores'
]:
    tmp_ret = collect_all(module)
    datas += tmp_ret[0]
    binaries += tmp_ret[1]
    hiddenimports += tmp_ret[2]

# -------------------------
# Analysis
# -------------------------

a = Analysis(
    ['agent.py'],
    pathex=[os.getcwd()],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    name='Aries',   # exe name changed clean
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # GUI app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
