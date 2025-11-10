# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for YOLO Annotator
Author: Ahmed Fekry
LinkedIn: www.linkedin.com/in/ahmed-fekry07

To build the executable:
    pyinstaller annotator.spec

This will create a single-file executable in the dist/ folder.
"""

block_cipher = None

a = Analysis(
    ['annotator_professional.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('yolo_annotator_logo.ico', '.'),
    ],
    hiddenimports=[],
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='YOLO_Annotator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Set to False for windowed app (no console)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='yolo_annotator_logo.ico',  # Application icon
    version_info={
        'version': '1.0',
        'Author': 'Ahmed Fekry',
        'file_description': 'YOLO Annotator - Professional Image Annotation Tool',
        'internal_name': 'YOLO_Annotator',
        'legal_copyright': '© 2025 Ahmed Fekry. Licensed under MIT.',
        'original_filename': 'YOLO_Annotator.exe',
        'product_name': 'YOLO Annotator',
        'product_version': '1.0'
    }
)
