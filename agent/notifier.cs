using System.Windows.Forms;

namespace MailDetectorAgent
{
    /// <summary>
    /// Pour ce POC : BalloonTip (WinForms natif, sans dépendance supplémentaire).
    /// En production finale : API Toast Notifications Windows (cf. mail_detector.md).
    /// </summary>
    public static class Notifier
    {
        public static void Show(NotifyIcon trayIcon, AlertDto alert)
        {
            trayIcon.BalloonTipTitle = "Mail non ouvert";
            trayIcon.BalloonTipText = $"De {alert.sender} à {alert.recipient}\n{alert.summary}";
            trayIcon.BalloonTipIcon = ToolTipIcon.Info;
            trayIcon.ShowBalloonTip(8000);
        }
    }
}