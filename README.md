# MSC Logger

MSC Logger is a space-themed maintenance app written mainly in Python. It helps
crew members keep track of tasks, equipment problems, spare parts, and reports.
Everything is saved on the computer, so work can continue without an internet
connection.

The sensor readings and connection to mission control are simulated. This project
is for learning and demonstrations, not actual spacecraft use.

## Features

- Maintenance checklists with due dates and completion notes
- Troubleshooting steps and saved equipment reports
- Spare parts inventory
- Reports that wait in a queue when the simulated connection is down
- Simulated sensor readings with warnings for missing or invalid data
- CSV imports and exports, database backups, and a separate demo mode

## Running the app on Windows

1. Extract the whole `MSC-Logger-Windows-x64.zip` folder.
2. Open `MSC Logger.exe`. Keep the other files in the same folder.
3. If WebView2 is missing, run `Setup WebView2.cmd`, then open the app again.

Python is included in the ZIP. The app opens in its own window, without opening
your browser. WebView2 setup needs internet, but the app can run offline afterward.
It needs Windows 10 or 11 (64-bit), Windows PowerShell 5.1, and .NET Framework 4.6.2
or newer.

Use `Demo.cmd` to try the app with separate demo records. Use `Check app.cmd` to
run the tests.

The ZIP is in `dist/` after building and is not stored in Git.

## How it works

Python handles the tasks, reports, sensor simulation, and data checks. SQLite
stores the records. HTML, CSS, and JavaScript make up the interface, and a small
C# wrapper displays it using WebView2.

The main folders are:

- `msc_logger/` - Python code and interface files
- `desktop/` - Windows app window
- `tests/` - automated tests
- `scripts/` - packaging and backup recovery tools

## Tests

With Python 3.11 or newer installed, run:

```sh
python -m unittest discover -s tests -v
```

All 26 tests passed on macOS. They cover things like saving records, invalid
readings, report retries, and backup recovery. The Windows executable still needs
to be tested on a Windows computer.

## Saved data and backups

On Windows, records are saved in `%LOCALAPPDATA%\MSC Logger`. Demo mode uses a
separate database, so resetting the demo does not clear the normal workspace.

You can download a backup from **Demo & data**. To restore one, close the app and
run `Restore backup.cmd`. Keep a backup somewhere else in case the computer or
drive fails.

## Building the Windows ZIP

Place these downloads in `tmp/runtime`:

- [Python 3.14.10 embeddable package, 64-bit](https://www.python.org/downloads/release/python-31410/)
  as `python-3.14.10-embed-amd64.zip`
- [Microsoft WebView2 SDK 1.0.4314.35](https://www.nuget.org/packages/Microsoft.Web.WebView2/1.0.4314.35)
  as `webview2.nupkg`
- [Microsoft WebView2 setup](https://go.microsoft.com/fwlink/p/?LinkId=2124703)
  as `MicrosoftEdgeWebview2Setup.exe`

Then run:

```sh
python scripts/build_windows.py
```

The builder checks the Python and SDK downloads before creating the ZIP.

## References

The project uses the Crew Maintenance Assistant HTML prototype and the MEC
programming PDFs as references. Code explanations and guides are kept separately
in `MSC Logger Explanations`, next to the project folder.
