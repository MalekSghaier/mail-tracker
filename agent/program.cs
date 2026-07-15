using System;
using System.Threading;
using System.Windows.Forms;
using Serilog;

namespace MailDetectorAgent
{
    internal static class Program
    {
        private const string MutexName = "Global\\MailDetectorAgent_SingleInstance_Mutex";

        [STAThread]
        private static void Main()
        {
            Logging.Configure();

            // Handler pour les exceptions sur le thread UI (WinForms)
            Application.ThreadException += (sender, e) =>
            {
                Log.Error(e.Exception, "Exception non gérée sur le thread UI");
            };
            Application.SetUnhandledExceptionMode(UnhandledExceptionMode.CatchException);

            // Handler pour les exceptions sur les autres threads (thread pool, async void, etc.)
            AppDomain.CurrentDomain.UnhandledException += (sender, e) =>
            {
                Log.Fatal(e.ExceptionObject as Exception, "Exception non gérée (AppDomain) — arrêt imminent : {IsTerminating}", e.IsTerminating);
                Log.CloseAndFlush();
            };

            using var mutex = new Mutex(initiallyOwned: true, MutexName, out bool createdNew);

            if (!createdNew)
            {
                MessageBox.Show(
                    "Mail Detector Agent est déjà en cours d'exécution.",
                    "Mail Detector Agent",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Information
                );
                return;
            }

            Application.SetHighDpiMode(HighDpiMode.SystemAware);
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            try
            {
                using var trayApp = new TrayIconApp();
                Application.Run();
            }
            finally
            {
                Log.CloseAndFlush();
            }
        }
    }
}