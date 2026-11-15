# Approved outside components

The user approved official Python runtime downloads, the local API/simulation,
and the Microsoft WebView2 desktop wrapper. No external mission service is used.

| Component | Version | Purpose |
| --- | --- | --- |
| Python embeddable x64 | 3.14.10 | Packaged Python standard library and interpreter |
| Microsoft.Web.WebView2 SDK | 1.0.4314.35 | Windows display control and loader |
| WebView2 Evergreen bootstrapper | Downloaded November 15, 2026 | Optional first-time runtime setup |
| Windows PowerShell / .NET Framework | Supplied by target Windows installation | Compiles and runs the small desktop host |

Python source and verified SHA-256:
https://www.python.org/downloads/release/python-31410/
https://www.python.org/ftp/python/3.14.10/python-3.14.10-embed-amd64.zip
`90905e64a840557d8c1bc4f5b74db3d7ee85e3ffb217611cac1c7813acea4159`

WebView2 SDK source:
https://www.nuget.org/packages/Microsoft.Web.WebView2/1.0.4314.35
https://www.nuget.org/api/v2/package/Microsoft.Web.WebView2/1.0.4314.35
Locally recorded SHA-256:
`90778deb1b77e36292828b4b5833c9255c27533f40e0ddd55891ae718944edc4`

WebView2 setup and distribution documentation:
https://go.microsoft.com/fwlink/p/?LinkId=2124703
https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution
https://learn.microsoft.com/en-us/microsoft-edge/hosting/webview2/gettingstarted

Python's license is bundled in `LICENSE.txt` in the Windows package. Microsoft's
SDK license is bundled under `desktop/webview2/LICENSE.txt`. The package checksum
manifest records the actual downloaded bootstrapper. Evergreen setup may download
an updated runtime when run; it is not a pinned offline runtime installer.

The Windows `.exe` has MSC icon resources and is therefore an unsigned derivative
of Python's windowed launcher. No original publisher signature is claimed for
that modified executable. Unmodified runtime DLLs remain as distributed.

The app's private API exposes GET state/export/backup and authenticated POST
commands. It listens on 127.0.0.1 at an automatically selected port. It has no
external API credentials. Backend source testing uses installed Python; document
generation uses the already bundled ReportLab and presentation tools. Those
build-only tools are not required by the delivered app.
