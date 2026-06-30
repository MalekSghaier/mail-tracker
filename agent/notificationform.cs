using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Windows.Forms;

namespace MailDetectorAgent
{
    /// <summary>
    /// Popup custom : affiche "Mail non ouvert", puis De / À / Cc (si dispo)
    /// chacun sur sa propre ligne, puis le résumé. Reste affiché jusqu'au
    /// clic utilisateur (croix ou corps du message) — pas de fermeture auto.
    /// </summary>
    public sealed class NotificationForm : Form
    {
        private const int CardWidth = 340;
        private const int CornerRadius = 14;
        private const int LineHeight = 18;
        private const int TitleHeight = 24;
        private const int TopRowHeight = 26;
        private const int MinSummaryHeight = 36;

        private static readonly Color BgColor = Color.FromArgb(255, 32, 32, 36);
        private static readonly Color AccentColor = Color.FromArgb(255, 245, 166, 35);
        private static readonly Color TitleColor = Color.White;
        private static readonly Color MetaColor = Color.FromArgb(255, 160, 160, 166);
        private static readonly Color SummaryColor = Color.FromArgb(255, 225, 225, 230);
        private static readonly Color CloseIdle = Color.FromArgb(255, 130, 130, 136);

        private static int _openCount = 0;
        private readonly int _slot;
        private readonly System.Windows.Forms.Timer _fadeTimer;

        public NotificationForm(AlertDto alert, Action onUserDismiss)
        {
            _slot = _openCount++;

            bool hasCc = !string.IsNullOrWhiteSpace(alert.cc);
            int metaLines = hasCc ? 3 : 2; // De + À (+ Cc)
            int cardHeight = TopRowHeight + TitleHeight + (metaLines * LineHeight) + MinSummaryHeight + 14;

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
            BuildLayout(alert, hasCc, onUserDismiss);

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
            var workingArea = Screen.PrimaryScreen.WorkingArea;
            int x = workingArea.Right - Width - 14;
            int y = workingArea.Bottom - Height - 14 - (_slot * (Height + 10));
            Location = new Point(x, Math.Max(y, 10));
        }

        private void BuildLayout(AlertDto alert, bool hasCc, Action onUserDismiss)
        {
            void DismissByUser()
            {
                onUserDismiss();
                Close();
            }

            var accentBar = new Panel { BackColor = AccentColor, Dock = DockStyle.Left, Width = 5 };

            var closeButton = new Label
            {
                Text = "✕",
                ForeColor = CloseIdle,
                Font = new Font("Segoe UI", 9.5f),
                Dock = DockStyle.Top,
                TextAlign = ContentAlignment.MiddleRight,
                Height = TopRowHeight,
                Padding = new Padding(0, 6, 12, 0),
                Cursor = Cursors.Hand,
            };
            closeButton.MouseEnter += (_, _) => closeButton.ForeColor = Color.White;
            closeButton.MouseLeave += (_, _) => closeButton.ForeColor = CloseIdle;
            closeButton.Click += (_, _) => DismissByUser();

            var textHost = new Panel
            {
                Dock = DockStyle.Fill,
                Padding = new Padding(14, 0, 12, 10),
            };

            var titleLabel = MakeLine("Mail non ouvert", TitleColor,
                new Font("Segoe UI", 10.5f, FontStyle.Bold), TitleHeight);
            titleLabel.Click += (_, _) => DismissByUser();

            var fromLabel = MakeLine($"De : {alert.sender}", MetaColor,
                new Font("Segoe UI", 8.5f), LineHeight);

            var toLabel = MakeLine($"À : {alert.recipient}", MetaColor,
                new Font("Segoe UI", 8.5f), LineHeight);

            Label? ccLabel = null;
            if (hasCc)
            {
                ccLabel = MakeLine($"Cc : {alert.cc}", MetaColor,
                    new Font("Segoe UI", 8.5f), LineHeight);
            }

            var summaryFont = new Font("Segoe UI", 8.75f);
            int summaryWidth = CardWidth - 14 - 12;
            int summaryHeight = MinSummaryHeight;
            var summaryLabel = new Label
            {
                Text = "Résumé : " + TruncateToFit(alert.summary, summaryFont,
                    new Size(summaryWidth, summaryHeight), "Résumé : "),
                ForeColor = SummaryColor,
                Font = summaryFont,
                Dock = DockStyle.Fill,
                Padding = new Padding(0, 4, 0, 0),
                Cursor = Cursors.Hand,
            };
            summaryLabel.Click += (_, _) => DismissByUser();

            // Ordre d'ajout = ordre d'affichage de haut en bas pour les Dock=Top
            textHost.Controls.Add(summaryLabel); // Fill : occupe le reste, peu importe l'ordre
            if (ccLabel != null) textHost.Controls.Add(ccLabel);
            textHost.Controls.Add(toLabel);
            textHost.Controls.Add(fromLabel);
            textHost.Controls.Add(titleLabel);

            Controls.Add(textHost);
            Controls.Add(closeButton);
            Controls.Add(accentBar);
        }

        private static Label MakeLine(string text, Color color, Font font, int height)
        {
            var label = new Label
            {
                Text = text,
                ForeColor = color,
                Font = font,
                Dock = DockStyle.Top,
                Height = height,
                AutoEllipsis = true,
                Cursor = Cursors.Hand,
            };
            return label;
        }

        private static string TruncateToFit(string text, Font font, Size maxSize, string prefix)
        {
            if (string.IsNullOrWhiteSpace(text)) return text;

            var flags = TextFormatFlags.WordBreak | TextFormatFlags.TextBoxControl;
            var availableSize = new Size(maxSize.Width, maxSize.Height);

            var fullSize = TextRenderer.MeasureText(prefix + text, font, availableSize, flags);
            if (fullSize.Height <= maxSize.Height) return text;

            string truncated = text;
            while (truncated.Length > 1)
            {
                truncated = truncated[..^1];
                string candidate = truncated.TrimEnd() + "…";
                var size = TextRenderer.MeasureText(prefix + candidate, font, availableSize, flags);
                if (size.Height <= maxSize.Height)
                {
                    return candidate;
                }
            }
            return "…";
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