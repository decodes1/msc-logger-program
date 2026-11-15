"""Windows WebView2 host. Never launches an installed web browser."""

import os
import subprocess
import sys
from pathlib import Path


def start_window(url, data_path):
    if sys.platform != "win32":
        raise RuntimeError("The desktop window requires Windows. Use --no-browser for backend testing only.")
    root = Path(__file__).resolve().parent.parent
    folder = root / "desktop"
    sdk = folder / "webview2"
    if not (sdk / "Microsoft.Web.WebView2.Core.dll").is_file():
        raise RuntimeError("Desktop components are missing. Extract the complete Windows ZIP before launching.")
    data_path = Path(data_path).resolve()
    data_path.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment.update({
        "MSC_WINDOW_URL": url,
        "MSC_WINDOW_DATA": str(data_path),
        "MSC_WINDOW_ICON": str(root / "msc_logger" / "static" / "assets" / "msc-logger.ico"),
        "PATH": str(sdk) + os.pathsep + environment.get("PATH", ""),
    })
    powershell = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    return subprocess.Popen(
        [str(powershell), "-NoLogo", "-NoProfile", "-NonInteractive", "-STA",
         "-ExecutionPolicy", "Bypass", "-File", str(folder / "launch.ps1")],
        env=environment,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
