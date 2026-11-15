using System;
using System.Drawing;
using System.IO;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace MscLogger
{
    // Windows owns the window. Python owns all application rules and records.
    public sealed class DesktopHost : Form
    {
        private readonly WebView2 view = new WebView2();
        private readonly Label status = new Label();
        private readonly Uri address;
        private readonly string dataFolder;
        private readonly string errorPath;

        public DesktopHost(string url, string userData, string iconPath)
        {
            address = new Uri(url);
            dataFolder = userData;
            errorPath = Path.Combine(userData, "desktop-error.txt");
            Text = "MSC Logger";
            StartPosition = FormStartPosition.CenterScreen;
            Size = new Size(1380, 940);
            MinimumSize = new Size(850, 650);
            BackColor = Color.FromArgb(244, 245, 247);
            AutoScaleMode = AutoScaleMode.Dpi;
            if (File.Exists(iconPath)) Icon = new Icon(iconPath);
            status.Text = "Opening MSC Logger...";
            status.Dock = DockStyle.Fill;
            status.TextAlign = ContentAlignment.MiddleCenter;
            status.Font = new Font("Segoe UI", 14);
            view.Dock = DockStyle.Fill;
            Controls.Add(view);
            Controls.Add(status);
            Shown += InitializeView;
        }

        private async void InitializeView(object sender, EventArgs args)
        {
            try
            {
                Directory.CreateDirectory(dataFolder);
                var environment = await CoreWebView2Environment.CreateAsync(null, dataFolder);
                await view.EnsureCoreWebView2Async(environment);
                var core = view.CoreWebView2;
                core.Settings.AreDevToolsEnabled = false;
                core.Settings.AreDefaultContextMenusEnabled = false;
                core.Settings.IsStatusBarEnabled = false;
                core.Settings.IsPasswordAutosaveEnabled = false;
                core.Settings.IsGeneralAutofillEnabled = false;
                core.NavigationStarting += (source, navigation) =>
                {
                    Uri destination;
                    if (!Uri.TryCreate(navigation.Uri, UriKind.Absolute, out destination) ||
                        destination.GetLeftPart(UriPartial.Authority) !=
                        address.GetLeftPart(UriPartial.Authority))
                    {
                        navigation.Cancel = true;
                    }
                };
                core.NewWindowRequested += (source, request) => { request.Handled = true; };
                core.PermissionRequested += (source, request) =>
                {
                    request.State = CoreWebView2PermissionState.Deny;
                };
                core.DownloadStarting += SaveDownload;
                core.ProcessFailed += (source, failure) =>
                {
                    MessageBox.Show(this,
                        "The display stopped responding. Close and reopen MSC Logger. " +
                        "Records already saved remain in the local database.",
                        "MSC Logger", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                };
                core.NavigationCompleted += (source, navigation) =>
                {
                    if (!navigation.IsSuccess)
                    {
                        status.Text = "The local workspace could not load. Close and reopen MSC Logger.";
                        status.Visible = true;
                    }
                };
                status.Visible = false;
                core.Navigate(address.AbsoluteUri);
            }
            catch (Exception error)
            {
                File.WriteAllText(errorPath, error.ToString());
                MessageBox.Show(this,
                    "MSC Logger could not open its desktop window.\n\n" +
                    "If Microsoft WebView2 Runtime is missing, run Setup WebView2.cmd " +
                    "from this package, then reopen the app.\n\n" +
                    "Details: " + error.Message,
                    "MSC Logger", MessageBoxButtons.OK, MessageBoxIcon.Error);
                Close();
            }
        }

        private void SaveDownload(object sender, CoreWebView2DownloadStartingEventArgs args)
        {
            var deferral = args.GetDeferral();
            BeginInvoke(new Action(() =>
            {
                try
                {
                    using (var dialog = new SaveFileDialog())
                    {
                        dialog.FileName = Path.GetFileName(args.ResultFilePath);
                        dialog.Title = "Save MSC Logger export";
                        dialog.OverwritePrompt = true;
                        if (dialog.ShowDialog(this) == DialogResult.OK)
                        {
                            args.ResultFilePath = dialog.FileName;
                        }
                        else
                        {
                            args.Cancel = true;
                        }
                    }
                }
                finally
                {
                    deferral.Complete();
                }
            }));
        }

        protected override void OnFormClosing(FormClosingEventArgs args)
        {
            if (view.CoreWebView2 != null && args.CloseReason == CloseReason.UserClosing &&
                MessageBox.Show(this,
                    "Close MSC Logger? Saved records remain on this computer. " +
                    "Unsaved form text will be lost.",
                    "MSC Logger", MessageBoxButtons.YesNo,
                    MessageBoxIcon.Question) != DialogResult.Yes)
            {
                args.Cancel = true;
                return;
            }
            base.OnFormClosing(args);
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing) view.Dispose();
            base.Dispose(disposing);
        }

        [STAThread]
        public static void Run(string url, string data, string icon)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            using (var host = new DesktopHost(url, data, icon))
            {
                Application.Run(host);
            }
        }
    }
}
