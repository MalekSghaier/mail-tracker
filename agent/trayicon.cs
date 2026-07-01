using System;
using System.Drawing;
using System.Windows.Forms;

namespace MailDetectorAgent
{
    /// <summary>
    /// Pour ce POC : pas de LoginForm (on est codé en dur comme destinataire).
    /// En production, c'est ici que LoginForm.cs s'afficherait une seule fois.
    /// </summary>
    public sealed class TrayIconApp : IDisposable
    {
        private readonly NotifyIcon _trayIcon;
        private readonly Poller _poller;

        public TrayIconApp()
        {
            _trayIcon = new NotifyIcon
            {
                Icon = new Icon(@"C:\Users\DELL\Desktop\mail-tracker\agent\Assets\favicon.ico"),
                Visible = true,
                Text = "Mail Detector Agent",
            };

            var menu = new ContextMenuStrip();
            menu.Items.Add("Quitter", null, (_, _) => Application.Exit());
            _trayIcon.ContextMenuStrip = menu;

            _poller = new Poller(_trayIcon);
            _poller.Start();
        }

        public void Dispose()
        {
            _poller.Stop();
            _trayIcon.Visible = false;
            _trayIcon.Dispose();
        }
    }
}