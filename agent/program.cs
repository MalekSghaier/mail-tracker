using System;
using System.Windows.Forms;

namespace MailDetectorAgent
{
    internal static class Program
    {
        [STAThread]
        private static void Main()
        {
            Application.SetHighDpiMode(HighDpiMode.SystemAware);
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            using var trayApp = new TrayIconApp();
            Application.Run();
        }
    }
}