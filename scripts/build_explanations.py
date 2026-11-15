"""Build concise explanation PDFs with the already bundled ReportLab tooling."""

from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "pdf"
OUTPUT.mkdir(parents=True, exist_ok=True)
STYLES = getSampleStyleSheet()
STYLES.add(ParagraphStyle("HeadingMSC", fontName="Helvetica-Bold", fontSize=13,
                          leading=17, textColor=colors.HexColor("#494d70"), spaceBefore=14, spaceAfter=6))
STYLES.add(ParagraphStyle("BodyMSC", fontName="Helvetica", fontSize=10.4,
                          leading=15.5, textColor=colors.HexColor("#303549"), spaceAfter=8))
STYLES.add(ParagraphStyle("TitleMSC", fontName="Helvetica-Bold", fontSize=25,
                          leading=30, textColor=colors.HexColor("#393c56"), spaceAfter=14))


def footer(canvas, doc):
    canvas.setStrokeColor(colors.HexColor("#dce0e9"))
    canvas.line(46, 42, 566, 42)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#687083"))
    canvas.drawString(46, 28, "MSC LOGGER  /  CODE EXPLANATIONS  /  NOVEMBER 15, 2026")
    canvas.drawRightString(566, 28, str(doc.page))


def build(filename, title, subtitle, sections):
    flow = [Image(str(ROOT / "msc_logger/static/assets/banner.png"), width=312, height=75.6),
            Spacer(1, 20), Paragraph(title, STYLES["TitleMSC"]),
            Paragraph(subtitle, STYLES["BodyMSC"])]
    for heading, paragraphs in sections:
        flow.append(Paragraph(escape(heading), STYLES["HeadingMSC"]))
        for paragraph in paragraphs:
            flow.append(Paragraph(escape(paragraph), STYLES["BodyMSC"]))
    document = SimpleDocTemplate(str(OUTPUT / filename), pagesize=(612, 792),
                                 leftMargin=46, rightMargin=46, topMargin=38, bottomMargin=58,
                                 title=title, author="MSC Logger project")
    document.build(flow, onFirstPage=footer, onLaterPages=footer)


build("01-python-core.pdf", "01 / The Python core", "Major change: replace temporary browser state with validated, durable records.", [
    ("What changed", ["The app now stores tasks, checklist progress, stock, reports, observations, and sensor samples in SQLite. Closing the app does not erase saved work. Python contains the rules; the interface only asks Python to apply them."]),
    ("The important code", ["catalog.py holds the illustrative training content. storage.py opens the database, checks its integrity, and groups writes into transactions. A transaction saves the whole change or rolls it back, so a half-finished stock adjustment is not recorded.", "engine.py validates each command. A task requires every checklist step before completion. Inventory updates include the balance revision that the user saw; an outdated revision is rejected. Each request has an ID so a retried request does not apply the same change twice."]),
    ("How telemetry and reports work", ["The simulator creates readings every two seconds. Non-numeric, non-finite, or out-of-range samples are rejected. Older samples cannot replace a newer reading. A valid reading older than 12 seconds is labelled stale.", "Reports move from queued to in-flight to delivered only after a simulated round-trip receipt. A lost receipt causes a delayed retry with the same report identity. Queue state lives in the database, so a restart does not forget an in-flight report."]),
    ("Evidence and limits", ["Twenty engine tests cover completion rules, concurrent stock edits, request replay, restart recovery, corrupted readings, atomic imports, retention, and backups. The entire suite contains 26 tests, including API and recovery checks.", "All sensor values, thresholds, and ground receipts are simulated. This is a single-computer training system, not flight software. Retention is bounded: 1,000 samples per sensor and 10,000 activity events. Back up and export important records."]),
])

build("02-desktop-interface.pdf", "02 / The desktop workspace", "Major change: a new interface in a dedicated Windows window, backed by a private local API.", [
    ("What changed", ["The original HTML was recreated as an overview, maintenance queue, troubleshooting flow, reports outbox, spares inventory, activity log, and demo/data screen. The supplied logos were adapted into a square PNG and multi-size Windows ICO."]),
    ("The important code", ["static/app.js renders the interface and sends commands. It escapes user text, preserves open forms during background polling, prevents repeated button presses while saving, and keeps request IDs for uncertain retries. app.css controls the layout and keyboard focus styling.", "server.py listens only on 127.0.0.1. A fresh session token protects API access. Host and origin checks reject other sites. Request size limits and a maximum of 16 workers keep local requests bounded. SQL values use parameters rather than string concatenation."]),
    ("Why there is a small Windows wrapper", ["Python starts desktop/launch.ps1, which compiles the small Host.cs window using Windows' existing .NET Framework. Microsoft WebView2 displays the interface inside that window. There is no Chrome, Edge, or other installed-browser launch fallback.", "The wrapper blocks navigation away from the local app, blocks new browser windows, and uses a Windows save dialog for exports. Python still owns all application data and rules. The extra language is limited to the Windows display host."]),
    ("Evidence and remaining validation", ["Five HTTP tests check session authorization, origin/host rejection, malformed and oversized requests, path traversal, exports, and database downloads. An initial dashboard preview loaded without JavaScript errors before browser previewing stopped at the user's request.", "The native Windows window, first-launch compilation, and file dialogs have not been run on this Mac. The package is a Windows review build until those checks pass on the target PC. Microsoft WebView2 Runtime must be installed; its setup is included."]),
])

build("03-packaging-recovery.pdf", "03 / Packaging and recovery", "Major change: a reproducible Windows package, verified backups, and a safe recovery path.", [
    ("What changed", ["The Windows ZIP includes Python, the application source, the approved WebView2 SDK, an optional Microsoft runtime setup program, launchers, tests, and these explanations. Keep the extracted folder together. The normal and demo workspaces use different databases."]),
    ("The important code", ["scripts/build_windows.py verifies pinned Python and SDK hashes, assembles the folder, and writes a checksum manifest. MSC Logger.exe is Python's windowed launcher with the supplied icon and a local startup hook. The modified executable is unsigned.", "scripts/windows_icon.py preserves the executable code and existing resources, adds the ICO resources, and verifies that the rebuilt resource tree can be read back. No original publisher signature is claimed for the modified launcher.", "The app creates verified database backups every five minutes and at clean exit. scripts/recover.py requires the app to be closed, validates a chosen backup, preserves the old database and journal files, and then replaces the active copy. A recovery test checks that a report survives this process."]),
    ("How to run and diagnose", ["Extract the ZIP and open MSC Logger.exe on Windows 10/11 x64. If needed, run Setup WebView2.cmd with internet access. Then normal app use works offline. Demo.cmd opens separate rehearsal records. Check app.cmd runs the 26 backend tests on Windows.", "Data lives in %LOCALAPPDATA%\\MSC Logger. Errors go to msc-logger.log; display failures also produce desktop-error.txt in the display data folder. Restore backup.cmd guides recovery of the saved workspace. Download backups to a different drive for disk-failure protection."]),
    ("What is and is not verified", ["All 26 Python, HTTP, and recovery tests passed on macOS. The official Python download matched its published SHA-256. Package resources and contents were checked. Native Windows execution is pending. No system can be guaranteed to function forever; runtime updates and periodic verification remain necessary."]),
])

build("04-run-and-demo-guide.pdf", "Run and demonstrate", "A short checklist for reviewing the Windows package. No presentation deck is required.", [
    ("First launch", ["1. Extract the entire Windows ZIP. Open MSC Logger.exe. Do not move only the executable out of its folder.", "2. If WebView2 is missing, close the app, run Setup WebView2.cmd while online, and reopen it. Windows PowerShell 5.1 and .NET Framework 4.6.2+ are also required.", "3. Run Check app.cmd. Confirm the 26 automated checks pass on the actual Windows machine. Then test opening the window, resizing it, saving a report, downloading a backup, and closing/reopening it."]),
    ("A short live demonstration", ["Open Demo.cmd. In Demo & data, reset rehearsal records with RESET DEMO. Set normal telemetry, four-second one-way delay, and ground link unavailable.", "Complete the intake checklist with a crew identifier. Show its next due date and saved completion. Use one intake filter in Spares inventory and give a reason.", "Save a report while the link is down. Restore the link and show queued, awaiting receipt, then simulated receipt after about eight seconds. State clearly that no real ground endpoint is involved.", "Select Low airflow warning and show the warning. Then select Corrupted airflow sample: the last valid reading stays visible and becomes stale after about 12 seconds. Show the rejection event in Activity log.", "Download a backup, close the app, and reopen Demo.cmd. Confirm that saved completions, inventory, and reports remain. This also gives the user a concrete approval check."]),
    ("If a check fails", ["Keep the error message and the app log. Do not overwrite or delete the database. Restart the app for a display failure; use Restore backup.cmd for a verified database recovery. The old files are preserved in a recovery folder.", "This package is ready for Windows review, not yet a Windows-verified release. Approve the app after the desktop launch and demonstration work on your PC. Git commits and remote push remain separate steps requiring the user's requested message approval and SSH access."]),
])
