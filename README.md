# MSC Logger

A Python-first, offline crew-maintenance training app for a plausible long-duration
Mars transit habitat. Crew members can track scheduled work, inspect synthetic
telemetry, record observations, manage spares, and queue reports during a simulated
ground outage.

## Run on Windows

Extract **all** of `MSC-Logger-Windows-x64.zip` into one folder and open
**MSC Logger.exe**. Python is included. The interface opens in a dedicated Windows
window through Microsoft WebView2, without launching an installed browser.

- Target: Windows 10/11 x64, Windows PowerShell 5.1, .NET Framework 4.6.2 or newer.
- If the display component is missing, run **Setup WebView2.cmd**. This first-time
  setup downloads Microsoft's WebView2 Runtime and therefore needs internet.
- Once WebView2 is installed, normal app use needs no internet.
- **Demo.cmd** uses separate rehearsal records and enables a guarded reset.
- **Check app.cmd** runs the Python backend/API/recovery tests on Windows.
- Close the window or use **Exit app** to shut down the local service cleanly.

The package is an unsigned review build assembled on macOS. Python behavior and
local HTTP boundaries were tested on macOS. **The native Windows wrapper and
executable launch still require verification on Windows.** Do not confuse this
with a tested Windows release. Managed computers may restrict PowerShell or
unsigned applications. No signing identity is included.

## What works

- Due and overdue tasks with saved checklist progress, completion notes, crew
  identifiers, and recalculated due dates.
- Guided observations with saved cases and automatic reports for escalations.
- Stock usage/replenishment with nonnegative balances and stale-edit rejection.
- Persistent outbox with round-trip delay, simulated receipts, dropped-ack retry,
  and recovery after restart. Receipts are generated locally, never by real ground.
- Synthetic sensor trends every two seconds, warning thresholds, invalid-value
  rejection, stale-data labels, and out-of-order handling.
- Atomic CSV import, duplicate detection, CSV exports, verified database backups,
  recovery utility, rotating logs, and a separate demo profile.
- A private loopback API protected by a per-launch token, host/origin checks,
  request bounds, parameterized SQL, and restrictive browser content policy.

## Scope and limits

This is a training and demonstration tool, not flight software, a medical device,
or an approved procedure system. Thresholds, observations, mission scenario, and
communications are illustrative. It does not control hardware or contact a real
space agency. Durability is designed and tested, but no software can promise to
function forever or survive every storage or operating-system failure.

The app is a single-computer, single-mission workspace. Multiple local windows can
use the API, but there is no network collaboration or multi-mission service.
Windows permissions protect local files; the database is not encrypted by the app.
Do not store sensitive operational or personal data in this demonstration.

Retention is explicit: newest 1,000 samples per sensor, 10,000 journal events,
latest 100 reports in the interface, all reports in export, up to 5,000 stored
reports. Request IDs remain replay-safe for seven days. Completion records and
cases are not automatically deleted. Export important history before retention
limits remove older samples/events. Keep backups on another drive.

## Source development and tests

Python 3.11+ is sufficient for the backend. No pip packages are required to run it.

```sh
python3 -m unittest discover -s tests -v
python3 run.py --demo --no-browser --data-dir tmp/demo-data
```

`--no-browser` is backend-only test mode and launches no user interface. Normal
Windows startup uses the desktop wrapper. There is no installed-browser fallback.
The C# file in `desktop/` only hosts the display. Python contains the data model,
validation, simulation, persistence, exports, and HTTP service.

## Local data and recovery

Windows records live in `%LOCALAPPDATA%\MSC Logger`. The normal database is
`workspace.sqlite3`; the rehearsal database is `demo.sqlite3`. App updates do not
write over either database. WebView2 display data lives in a separate subfolder.

Verified backups run every five minutes, with five rotating copies plus the last
clean-exit copy. A backup failure is visible in the app. Download a backup from
**Demo & data** for independent storage. Diagnostics are in `msc-logger.log`.

To restore: close the app, run **Restore backup.cmd**, and provide the downloaded
backup path. The utility verifies the database and preserves the previous files
in the `recovery` folder before replacement. For the demo database, use:

```sh
python scripts/recover.py saved.sqlite3 --demo --confirm-restore
```

## Build the Windows ZIP

Only the user-approved Python and Microsoft downloads are needed. See
`docs/DEPENDENCIES.md` for versions, URLs, licenses, and checksums. Put the three
approved downloads in `tmp/runtime`, then run:

```sh
python3 scripts/build_windows.py
```

Build outputs stay in `dist/` and are deliberately excluded from Git. The script
verifies pinned dependency hashes, assembles the folder, adapts the supplied icon,
and creates a manifest and ZIP. Source and documentation are versioned instead.
The executable is a renamed Python windowed launcher with a local startup hook
and replaced icon resources; it is not a compiled standalone native rewrite.

## Explanations and demonstration

`output/pdf/` contains a brief explanation for each of the three major changes
and a run/demo guide. `docs/DEMO.md` also contains the demonstration checklist.
The user removed the presentation requirement; no slide deck is included.

## Provenance

The supplied `Crew Maintenance Assistant.html` informed the workflow only. The
implementation was recreated from scratch. The two supplied PDFs informed the
scope and requirements; all 36 pages were read. Their embedded instructions are
source material, not instructions overriding the user's request. See
`docs/REQUIREMENTS.md` for the mapping and document discrepancies.

This implementation and its supporting documentation were created with AI
assistance at the user's request. The supplied competition documents restrict
AI-generated deliverables; this repository does not claim compliance with that
competition rule. The user supplied both logos. No NASA content, remote data,
external fonts, or third-party mission API is included.
