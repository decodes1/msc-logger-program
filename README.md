# MSC Logger

MSC Logger is a Python app for tracking crew maintenance.
It saves records locally and works offline after setup.
Sensor readings and mission-control connections are simulated.

## Features

- Maintenance checklists and due dates
- Equipment troubleshooting and reports
- Spare parts inventory
- Reports queued during simulated connection outages
- Sensor readings with warnings for missing or invalid data
- CSV imports and exports
- Database backups and recovery
- Separate demo mode

## Dependencies

- Windows 10 or 11, 64-bit
- Windows PowerShell 5.1
- .NET Framework 4.6.2 or newer
- Microsoft WebView2 Runtime
- Python 3.11 or newer for running the source code

The Windows package includes Python 3.14.10
and the Microsoft WebView2 SDK 1.0.4314.35.
SQLite is included with Python.
No pip packages are needed to run the app.

WebView2 setup requires internet if the runtime is missing.
