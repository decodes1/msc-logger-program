$ErrorActionPreference = 'Stop'
try {
    $sdk = Join-Path $PSScriptRoot 'webview2'
    $core = Join-Path $sdk 'Microsoft.Web.WebView2.Core.dll'
    $forms = Join-Path $sdk 'Microsoft.Web.WebView2.WinForms.dll'
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    [System.Reflection.Assembly]::LoadFrom($core) | Out-Null
    [System.Reflection.Assembly]::LoadFrom($forms) | Out-Null
    Add-Type -Path (Join-Path $PSScriptRoot 'Host.cs') -ReferencedAssemblies @(
        'System.dll', 'System.Core.dll', 'System.Windows.Forms.dll',
        'System.Drawing.dll', $core, $forms
    )
    [MscLogger.DesktopHost]::Run($env:MSC_WINDOW_URL, $env:MSC_WINDOW_DATA, $env:MSC_WINDOW_ICON)
}
catch {
    $_ | Out-String | Set-Content (Join-Path $env:MSC_WINDOW_DATA 'desktop-error.txt')
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show(
        "MSC Logger could not open its window. See desktop-error.txt in the app data folder.`n`n$($_.Exception.Message)",
        'MSC Logger'
    ) | Out-Null
    exit 1
}
