using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Windows.Forms;

namespace MailDetectorAgent
{
    /// <summary>
    /// Popup custom pour le scénario B (mail reçu non lu), même style que
    /// NotificationForm (navy + accent doré). Pas de question Oui/Non
    /// (pas de rappel côté mails reçus) — juste un statut "Non lu depuis".
    /// Reste affiché jusqu'au clic sur la croix.
    /// </summary>
    public sealed class ImapNotificationForm : Form
    {
        private const int CardWidth = 344;
        private const int CornerRadius = 16;
        private const int LineHeight = 18;
        private const int TitleHeight = 24;
        private const int TopRowHeight = 24;
        private const int FooterHeight = 40;

        private static readonly Color BgColor = Color.FromArgb(255, 26, 26, 34);
        private static readonly Color GoldAccent = Color.FromArgb(255, 212, 175, 90);
        private static readonly Color TitleColor = Color.White;
        private static readonly Color MetaColor = Color.FromArgb(255, 150, 150, 162);
        private static readonly Color CloseIdle = Color.FromArgb(255, 120, 120, 130);
        private static readonly Color DividerColor = Color.FromArgb(255, 42, 42, 52);
        private static readonly Color WarningColor = Color.FromArgb(255, 232, 160, 64);

        private static int _openCount = 0;
        private readonly int _slot;
        private readonly System.Windows.Forms.Timer _fadeTimer;
        private readonly Action _onDismiss;

        public string Key { get; }

        public ImapNotificationForm(ImapAlertDto alert, Action onDismiss)
        {
            _slot = _openCount++;
            _onDismiss = onDismiss;
            Key = alert.Key;

            int metaLines = 3; // employé/département, expéditeur, sujet
            int cardHeight = TopRowHeight + TitleHeight + (metaLines * LineHeight) + 1 + FooterHeight + 10;

            FormBorderStyle = FormBorderStyle.None;
            StartPosition = FormStartPosition.Manual;
            ShowInTaskbar = false;
            TopMost = true;
            BackColor = BgColor;
            Width = CardWidth;
            Height = cardHeight;
            Opacity = 0;

            ApplyRoundedRegion();
            PositionBottomRight();
            BuildLayout(alert);

            _fadeTimer = new System.Windows.Forms.Timer { Interval = 15 };
            _fadeTimer.Tick += (_, _) =>
            {
                Opacity = Math.Min(1.0, Opacity + 0.08);
                if (Opacity >= 1.0) _fadeTimer.Stop();
            };
            Load += (_, _) => _fadeTimer.Start();
        }

        private void ApplyRoundedRegion()
        {
            var path = new GraphicsPath();
            int r = CornerRadius;
            var rect = new Rectangle(0, 0, Width, Height);
            path.AddArc(rect.X, rect.Y, r, r, 180, 90);
            path.AddArc(rect.Right - r, rect.Y, r, r, 270, 90);
            path.AddArc(rect.Right - r, rect.Bottom - r, r, r, 0, 90);
            path.AddArc(rect.X, rect.Bottom - r, r, r, 90, 90);
            path.CloseFigure();
            Region = new Region(path);
        }

        private void PositionBottomRight()
        {
            var workingArea = Screen.PrimaryScreen?.WorkingArea ?? new Rectangle(0, 0, 1920, 1080);
            int x = workingArea.Right - Width - 14;
            int y = workingArea.Bottom - Height - 14 - (_slot * (Height + 10));
            Location = new Point(x, Math.Max(y, 10));
        }

        private void DismissByUser()
        {
            _onDismiss();
            Close();
        }

        private void BuildLayout(ImapAlertDto alert)
        {
            var accentBar = new Panel { BackColor = GoldAccent, Dock = DockStyle.Left, Width = 4 };

            var closeButton = new Label
            {
                Text = "✕",
                ForeColor = CloseIdle,
                Font = new Font("Segoe UI", 9f),
                Dock = DockStyle.Top,
                TextAlign = ContentAlignment.MiddleRight,
                Height = TopRowHeight,
                Padding = new Padding(0, 6, 12, 0),
                Cursor = Cursors.Hand,
            };
            closeButton.MouseEnter += (_, _) => closeButton.ForeColor = Color.White;
            closeButton.MouseLeave += (_, _) => closeButton.ForeColor = CloseIdle;
            closeButton.Click += (_, _) => DismissByUser();

            var divider = new Panel { Dock = DockStyle.Bottom, Height = 1, BackColor = DividerColor };

            var textHost = new Panel
            {
                Dock = DockStyle.Fill,
                Padding = new Padding(16, 0, 12, 10),
            };

            var titleLabel = MakeLine("Mail non lu", TitleColor,
                new Font("Segoe UI Semibold", 10.5f, FontStyle.Bold), TitleHeight);

            var whoLabel = MakeLine($"{alert.employee_username} ({alert.department})", MetaColor,
                new Font("Segoe UI", 8.5f), LineHeight);

            var fromLabel = MakeLine($"De : {alert.sender}", MetaColor,
                new Font("Segoe UI", 8.5f), LineHeight);

            var subjectLabel = MakeLine($"Sujet : {alert.subject}", MetaColor,
                new Font("Segoe UI", 8.5f), LineHeight);

            textHost.Controls.Add(subjectLabel);
            textHost.Controls.Add(fromLabel);
            textHost.Controls.Add(whoLabel);
            textHost.Controls.Add(titleLabel);

            var footerPanel = new Panel
            {
                Dock = DockStyle.Bottom,
                Height = FooterHeight,
                BackColor = BgColor,
            };
            var statusLabel = new Label
            {
                Text = $"●  Non lu — reçu le {FormatDate(alert.received_at)}",
                ForeColor = WarningColor,
                Font = new Font("Segoe UI", 8.5f, FontStyle.Bold),
                Dock = DockStyle.Fill,
                TextAlign = ContentAlignment.MiddleCenter,
            };
            footerPanel.Controls.Add(statusLabel);

            Controls.Add(footerPanel);
            Controls.Add(divider);
            Controls.Add(textHost);
            Controls.Add(closeButton);
            Controls.Add(accentBar);
        }

        private static string FormatDate(string raw)
        {
            if (string.IsNullOrWhiteSpace(raw)) return "—";
            return raw.Length >= 16 ? raw.Substring(0, 16).Replace("T", " ") : raw;
        }

        private static Label MakeLine(string text, Color color, Font font, int height)
        {
            return new Label
            {
                Text = text,
                ForeColor = color,
                Font = font,
                Dock = DockStyle.Top,
                Height = height,
                AutoEllipsis = true,
            };
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing)
            {
                _openCount = Math.Max(0, _openCount - 1);
                _fadeTimer?.Dispose();
            }
            base.Dispose(disposing);
        }
    }
}