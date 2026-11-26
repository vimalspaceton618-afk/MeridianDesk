using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Threading.Tasks;
using System.Windows.Forms;
using System.Runtime.InteropServices;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

internal sealed class MeridianWindow : Form
{
    private readonly string root = AppDomain.CurrentDomain.BaseDirectory;
    private readonly WebView2 view = new WebView2();
    private readonly bool verify;
    private Process service;
    private Uri origin;

    [DllImport("user32.dll")] private static extern bool SetProcessDPIAware();

    [STAThread]
    public static int Main(string[] args)
    {
        SetProcessDPIAware();
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        Application.Run(new MeridianWindow(Array.IndexOf(args, "--verify") >= 0));
        return Environment.ExitCode;
    }

    private MeridianWindow(bool validation)
    {
        verify = validation;
        Text = "Meridian Desk";
        BackColor = Color.FromArgb(16, 23, 23);
        ClientSize = new Size(1380, 870);
        MinimumSize = new Size(840, 600);
        StartPosition = FormStartPosition.CenterScreen;
        Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
        view.Dock = DockStyle.Fill;
        view.DefaultBackgroundColor = BackColor;
        Controls.Add(view);
        Shown += async delegate { await OpenDesk(); };
        FormClosed += delegate {
            if (service != null && !service.HasExited) {
                try { service.StandardInput.WriteLine("close"); service.StandardInput.Flush(); }
                catch (IOException) { }
                if (!service.WaitForExit(3500)) service.Kill();
            }
        };
    }

    private async Task OpenDesk()
    {
        try {
            var cache = Path.Combine(root, "cache");
            var tmp = Path.Combine(cache, "temp");
            Directory.CreateDirectory(tmp);
            Environment.SetEnvironmentVariable("TEMP", tmp);
            Environment.SetEnvironmentVariable("TMP", tmp);
            var info = new ProcessStartInfo(Path.Combine(root,"runtime","python","python.exe"),
                "-B -u \"" + Path.Combine(root,"desk.py") + "\" --desktop" + (verify ? " --verify" : "")) {
                WorkingDirectory = root, UseShellExecute = false, CreateNoWindow = true,
                RedirectStandardOutput = true, RedirectStandardInput = true, RedirectStandardError = true
            };
            service = Process.Start(info);
            service.ErrorDataReceived += delegate(object sender, DataReceivedEventArgs e) {
                if (!String.IsNullOrEmpty(e.Data)) {
                    try { File.AppendAllText(Path.Combine(root,"logs","desktop.log"), e.Data + Environment.NewLine); } catch (IOException) { }
                }
            };
            service.BeginErrorReadLine();
            var read = service.StandardOutput.ReadLineAsync();
            if (await Task.WhenAny(read,Task.Delay(30000)) != read) throw new Exception("The local service did not start within 30 seconds.");
            string address = await read;
            if (address == null || !Uri.TryCreate(address,UriKind.Absolute,out origin) || origin.Host != "127.0.0.1")
                throw new Exception("Local service startup failed. See logs\\desktop.log.");
            var env = await CoreWebView2Environment.CreateAsync(null, Path.Combine(cache, verify ? "webview-test" : "webview"));
            await view.EnsureCoreWebView2Async(env);
            view.CoreWebView2.Settings.AreDevToolsEnabled = false;
            view.CoreWebView2.Settings.AreDefaultContextMenusEnabled = false;
            view.CoreWebView2.Settings.IsStatusBarEnabled = false;
            view.CoreWebView2.NewWindowRequested += (s,e) => e.Handled = true;
            view.CoreWebView2.NavigationStarting += (s,e) => {
                Uri dest;
                if (!Uri.TryCreate(e.Uri,UriKind.Absolute,out dest) || dest.GetLeftPart(UriPartial.Authority) != origin.GetLeftPart(UriPartial.Authority)) e.Cancel = true;
            };
            view.CoreWebView2.Navigate(origin.AbsoluteUri);
            if (verify) await Verify();
        } catch (Exception ex) {
            Environment.ExitCode = 1;
            Directory.CreateDirectory(Path.Combine(root,"logs"));
            File.AppendAllText(Path.Combine(root,"logs","desktop.log"), ex + Environment.NewLine);
            if (!verify) MessageBox.Show(this,ex.Message,"Meridian Desk",MessageBoxButtons.OK,MessageBoxIcon.Error);
            Close();
        }
    }

    private async Task Verify()
    {
        for (int i = 0; i < 100; i++) {
            if (await view.ExecuteScriptAsync("document.body && document.body.dataset.ready === 'yes'") == "true") {
                using (var file=File.Create(Path.Combine(root,"tests","desktop-preview.png")))
                    await view.CoreWebView2.CapturePreviewAsync(CoreWebView2CapturePreviewImageFormat.Png,file);
                string result = await view.ExecuteScriptAsync("window.verifyNavigation()");
                if (result != "true") throw new Exception("Workstation navigation did not verify. Result: "+result);
                File.WriteAllText(Path.Combine(root,"tests","desktop-smoke.txt"),"Native WebView2, authenticated API, market chart, and workspace navigation passed.");
                Close();
                return;
            }
            await Task.Delay(250);
        }
        throw new Exception("The workstation did not render market data in time.");
    }
}
