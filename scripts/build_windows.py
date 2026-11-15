"""Assemble the approved Windows dependencies into a portable folder and ZIP."""

import argparse
import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path

from windows_icon import replace_icon

ROOT = Path(__file__).resolve().parents[1]
PYTHON_SHA256 = "90905e64a840557d8c1bc4f5b74db3d7ee85e3ffb217611cac1c7813acea4159"
WEBVIEW_SHA256 = "90778deb1b77e36292828b4b5833c9255c27533f40e0ddd55891ae718944edc4"


def verify(path, expected):
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError(f"Checksum mismatch for {path.name}")


def build(runtime):
    python_zip = runtime / "python-3.14.10-embed-amd64.zip"
    webview_zip = runtime / "webview2.nupkg"
    verify(python_zip, PYTHON_SHA256)
    verify(webview_zip, WEBVIEW_SHA256)
    folder = ROOT / "dist" / "MSC Logger"
    folder.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(python_zip) as archive:
        archive.extractall(folder)
    (folder / "python314._pth").write_text("python314.zip\n.\nimport site\n")
    for name in ("msc_logger", "desktop", "tests", "scripts", "docs", "output"):
        shutil.copytree(ROOT / name, folder / name, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "node_modules"))
    for name in ("run.py", "LICENSE", "README.md"):
        if (ROOT / name).exists():
            shutil.copy2(ROOT / name, folder / name)
    sdk = folder / "desktop" / "webview2"
    sdk.mkdir(exist_ok=True)
    with zipfile.ZipFile(webview_zip) as archive:
        for name in ("Microsoft.Web.WebView2.Core.dll", "Microsoft.Web.WebView2.WinForms.dll"):
            (sdk / name).write_bytes(archive.read("lib/net462/" + name))
        loader = archive.read("runtimes/win-x64/native/WebView2Loader.dll")
        (sdk / "WebView2Loader.dll").write_bytes(loader)
        native = sdk / "runtimes" / "win-x64" / "native"
        native.mkdir(parents=True, exist_ok=True)
        (native / "WebView2Loader.dll").write_bytes(loader)
        (sdk / "LICENSE.txt").write_bytes(archive.read("LICENSE.txt"))
    executable = folder / "MSC Logger.exe"
    shutil.copy2(folder / "pythonw.exe", executable)
    replace_icon(executable, ROOT / "msc_logger/static/assets/msc-logger.ico")
    (folder / "sitecustomize.py").write_text('''"""Bootstrap the named desktop executable only."""
import os
import sys
from pathlib import Path

if Path(sys.executable).name.lower() == "msc logger.exe":
    from msc_logger.__main__ import desktop_entry
    arguments = ["--demo"] if os.environ.get("MSC_DEMO") == "1" else []
    os._exit(desktop_entry(arguments))
''')
    (folder / "Demo.cmd").write_text('@echo off\nsetlocal\nset MSC_DEMO=1\nstart "" "%~dp0MSC Logger.exe"\n', newline="\r\n")
    (folder / "Check app.cmd").write_text('@echo off\ncd /d "%~dp0"\npython.exe -m unittest discover -s tests -v\necho.\necho These tests check Python logic and the local API, not the desktop display.\npause\n', newline="\r\n")
    (folder / "Restore backup.cmd").write_text('@echo off\ncd /d "%~dp0"\necho Close MSC Logger first. Existing records will be preserved in a recovery folder.\nset /p "backup=Full path to the downloaded backup: "\npython.exe scripts\\recover.py "%backup%" --confirm-restore\npause\n', newline="\r\n")
    setup = folder / "setup"
    setup.mkdir(exist_ok=True)
    shutil.copy2(runtime / "MicrosoftEdgeWebview2Setup.exe", setup)
    (folder / "Setup WebView2.cmd").write_text('@echo off\necho Microsoft WebView2 setup may need an internet connection.\nstart /wait "" "%~dp0setup\\MicrosoftEdgeWebview2Setup.exe" /install\necho Setup has finished. Reopen MSC Logger.exe.\npause\n', newline="\r\n")
    (folder / "START HERE.txt").write_text(
        "MSC LOGGER - WINDOWS x64 REVIEW BUILD\n\n"
        "1. Extract the whole ZIP to a normal folder.\n"
        "2. Double-click MSC Logger.exe. Keep all files together.\n"
        "3. If WebView2 is missing, run Setup WebView2.cmd with internet access.\n"
        "4. Use Demo.cmd for a separate, resettable rehearsal workspace.\n"
        "5. Use Check app.cmd to run the included backend tests.\n\n"
        "The desktop wrapper does not open Chrome or Edge. Windows 10/11 x64,\n"
        ".NET Framework 4.6.2+ and Windows PowerShell 5.1 are required.\n"
        "The app works offline once WebView2 is installed. This is an unsigned\n"
        "review build. Native Windows launch has not been verified on the build Mac.\n\n"
        "Records: %LOCALAPPDATA%\\MSC Logger\\\n"
        "Exit using the app's Exit button or the window close button.\n"
        "No external mission APIs. All telemetry and ground receipts are simulated.\n"
    )
    manifest = {str(path.relative_to(folder)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(folder.rglob("*")) if path.is_file() and path.name != "SHA256SUMS.json"}
    (folder / "SHA256SUMS.json").write_text(json.dumps(manifest, indent=2) + "\n")
    output = ROOT / "dist" / "MSC-Logger-Windows-x64.zip"
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                archive.write(path, Path("MSC Logger") / path.relative_to(folder))
    print(output)
    print(f"Size: {output.stat().st_size / 1024 / 1024:.1f} MB")
    print("SHA256:", hashlib.sha256(output.read_bytes()).hexdigest())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-dir", type=Path, default=ROOT / "tmp" / "runtime")
    build(parser.parse_args().runtime_dir)
