# Building YOLO Annotator for Windows

## Prerequisites

1. Install Python 3.8 or higher
2. Install required packages:
```bash
pip install PyQt6 Pillow pyinstaller
```

## Building the Executable

### Step 1: Prepare Files

Ensure you have:
- `app.py`
- `annotator.spec`
- `yolo_annotator_logo.ico`

### Step 2: Build

```bash
pyinstaller annotator.spec
```

### Step 3: Test

The executable will be in `dist/YOLO_Annotator.exe`

Test it by double-clicking or running:
```bash
cd dist
YOLO_Annotator.exe
```

## Distribution

The resulting `YOLO_Annotator.exe` is a standalone application that can be distributed without Python installation.

**File Size:** Approximately 50-100 MB  
**Dependencies:** All bundled (PyQt6, Pillow, Python runtime)

## Troubleshooting

**Issue:** Missing DLL errors  
**Solution:** Install Visual C++ Redistributable

**Issue:** Icon not showing  
**Solution:** Ensure `yolo_annotator_logo.ico` is in same directory as spec file

**Issue:** Large file size  
**Solution:** Use `--onefile` flag (already in spec)

---

**Author:** Ahmed Fekry  
**Contact:** [www.linkedin.com/in/ahmed-fekry07]
