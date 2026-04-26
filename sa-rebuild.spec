# PyInstaller spec — builds a single-binary desktop app wrapping the
# Streamlit UI. Use the build scripts (`packaging/build-mac.sh`,
# `packaging\build-windows.bat`) which run `pyinstaller sa-rebuild.spec`.
#
# The tricky bits handled here:
#   - Streamlit, keepa, pandas all have hidden imports + data files.
#   - Streamlit needs metadata at runtime (package version, entry points).
#   - sa_rebuild.web.app is loaded by Streamlit at runtime, not imported, so
#     we ship it as a data file alongside the rest of the package.

# ruff: noqa
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path("src").resolve()))
from sa_rebuild import __version__ as _PKG_VERSION  # noqa: E402

from PyInstaller.utils.hooks import collect_all, copy_metadata

datas = []
binaries = []
hiddenimports = []

for pkg in ("streamlit", "keepa", "pandas", "rapidfuzz", "yaml", "rich", "pydantic",
            "pydantic_settings", "tenacity", "typer", "dotenv"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

# Streamlit looks up its own metadata at runtime to render version info etc.
for pkg in ("streamlit", "altair", "pyarrow", "click", "typer", "rich"):
    try:
        datas += copy_metadata(pkg)
    except Exception:
        pass

# Ship the package source so Streamlit can `streamlit run` it from disk.
datas += [
    ("src/sa_rebuild", "sa_rebuild"),
    ("config.yaml", "."),
]


a = Analysis(
    ["desktop_launcher.py"],
    pathex=["src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + [
        "sa_rebuild",
        "sa_rebuild.web.app",
        "sa_rebuild.cli",
        "sa_rebuild.runner",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pytest", "vcr", "IPython", "jupyter"],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="sa-rebuild",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,           # Keep console so users see startup logs / can Ctrl+C
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="sa-rebuild",
)

# Build a Mac .app bundle when running on macOS so users get a Finder icon.
import sys
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="sa-rebuild.app",
        icon=None,
        bundle_identifier="dev.olatunde.sa-rebuild",
        info_plist={
            "CFBundleDisplayName": "sa-rebuild",
            "CFBundleShortVersionString": _PKG_VERSION,
            "CFBundleVersion": _PKG_VERSION,
            "NSHighResolutionCapable": True,
            "LSBackgroundOnly": False,
        },
    )
