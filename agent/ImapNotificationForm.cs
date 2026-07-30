using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Windows.Forms;

namespace MailDetectorAgent
{
    /// <summary>
    /// Popup custom pour le scénario B (mail reçu non lu), miroir exact de
    /// NotificationForm : clic sur le titre ouvre la page détail, question
    /// "Avez-vous relancé l'employé ?" avec Oui/Non, même logique de
    /// persistance et de fermeture automatique après réponse.
    /// </summary>
    public sealed class ImapNotificationForm : Form
    {
        private const int CardWidth = 344;
        private const int CornerRadius = 16;
        private const int LineHeight = 18;
        private const int TitleHeight = 24;
        private const int TopRowHeight = 24;
        private const int ReminderHeight = 60;

        private static readonly Color BgColor = Color.FromArgb(255, 26, 26, 34);
        private static readonly Color GoldAccent = Color.FromArgb(255, 212, 175, 90);
        private static readonly Color TitleColor = Color.White;
        private static readonly Color MetaColor = Color.FromArgb(255, 150, 150, 162);
        private static readonly Color CloseIdle = Color.FromArgb(255, 120, 120, 130);
        private static readonly Color DividerColor = Color.FromArgb(255, 42, 42, 52);
        private static readonly Color ValidatedColor = Color.FromArgb(255, 72, 178, 128);
        private static readonly Color NotValidatedColor = Color.FromArgb(255, 212, 96, 96);

        private static int _openCount = 0;
        private readonly int _slot;
        private readonly System.Windows.Forms.Timer _fadeTimer;
        private readonly Panel _reminderPanel;
        private bool? _reminderStatus;
        private readonly Action<bool> _onAnswer;
        private readonly Action _onUserDismiss;
        private readonly Action _onMinimize;
        private readonly string _detailUrl;

        public string Key { get; }

        public ImapNotificationForm(ImapAlertDto alert, Action onUserDismiss, Action onMinimize,
            bool? reminderStatus, Action<bool> onAnswer, string apiBase)
        {
            _slot = _openCount++;
            _reminderStatus = reminderStatus;
            _onAnswer = onAnswer;
            _onUserDismiss = onUserDismiss;
            _onMinimize = onMinimize;
            _detailUrl = $"{apiBase}/imap-mail/{alert.tracking_id}";
            Key = alert.Key;

            int metaLines = 3; // employé (département), expéditeur, sujet
            int cardHeight = TopRowHeight + TitleHeight + (metaLines * LineHeight) + 1 + ReminderHeight + 10;

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

            _reminderPanel = new Panel
            {
                Dock = DockStyle.Bottom,
                Height = ReminderHeight,
                BackColor = BgColor,
            };
            BuildReminderContent();

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

        private void BuildReminderContent()
        {
            _reminderPanel.Controls.Clear();

            if (_reminderStatus == null)
            {
                var question = new Label
                {
                    Text = "Avez-vous relancé l'employé ?",
                    ForeColor = Color.FromArgb(255, 205, 205, 212),
                    Font = new Font("Segoe UI", 8.75f),
                    Dock = DockStyle.Top,
                    Height = 22,
                    TextAlign = ContentAlignment.MiddleCenter,
                };

                var optionsRow = new Panel { Dock = DockStyle.Top, Height = 28 };

                var optOui = new AnswerOption("Oui", true, ValidatedColor);
                var optNon = new AnswerOption("Non", false, NotValidatedColor);

                int spacing = 28;
                int totalWidth = optOui.Width + spacing + optNon.Width;
                int startX = (CardWidth - totalWidth) / 2;

                optOui.Location = new Point(startX, 0);
                optNon.Location = new Point(startX + optOui.Width + spacing, 0);

                optOui.Answered += Answer;
                optNon.Answered += Answer;

                optionsRow.Controls.Add(optOui);
                optionsRow.Controls.Add(optNon);

                _reminderPanel.Controls.Add(optionsRow);
                _reminderPanel.Controls.Add(question);
            }
            else
            {
                bool done = _reminderStatus.Value;
                var statusLabel = new Label
                {
                    Text = done ? "●  Validé — employé relancé" : "●  Non validé — pas encore relancé",
                    ForeColor = done ? ValidatedColor : NotValidatedColor,
                    Font = new Font("Segoe UI", 9f, FontStyle.Bold),
                    Dock = DockStyle.Fill,
                    TextAlign = ContentAlignment.MiddleCenter,
                };
                _reminderPanel.Controls.Add(statusLabel);
            }
        }

        private void Answer(bool done)
        {
            _reminderStatus = done;
            _onAnswer(done);
            ShowConfirmationAndAutoClose(done);
        }

        public void ApplyExternalAnswer(bool done)
        {
            if (IsDisposed) return;
            if (InvokeRequired)
            {
                BeginInvoke(new Action(() => ApplyExternalAnswer(done)));
                return;
            }
            if (_reminderStatus == done) return;
            _reminderStatus = done;
            ShowConfirmationAndAutoClose(done);
        }

        private void ShowConfirmationAndAutoClose(bool done)
        {
            _reminderPanel.Controls.Clear();
            var confirmLabel = new Label
            {
                Text = done ? "✓ Réponse enregistrée — Oui" : "✓ Réponse enregistrée — Non",
                ForeColor = done ? ValidatedColor : NotValidatedColor,
                Font = new Font("Segoe UI", 9f, FontStyle.Bold),
                Dock = DockStyle.Fill,
                TextAlign = ContentAlignment.MiddleCenter,
            };
            _reminderPanel.Controls.Add(confirmLabel);

            var confirmTimer = new System.Windows.Forms.Timer { Interval = 1100 };
            confirmTimer.Tick += (_, _) =>
            {
                confirmTimer.Stop();
                confirmTimer.Dispose();
                if (!IsDisposed) DismissByUser();
            };
            confirmTimer.Start();
        }

        private void DismissByUser()
        {
            _onUserDismiss();
            Close();
        }

        private void MinimizeByUser()
        {
            _onMinimize();
            Close();
        }

        private void OpenDetailPage()
        {
            try
            {
                System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo
                {
                    FileName = _detailUrl,
                    UseShellExecute = true,
                });
            }
            catch { /* navigateur non disponible, on ignore */ }
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
            closeButton.Click += (_, _) => MinimizeByUser();

            var divider = new Panel { Dock = DockStyle.Bottom, Height = 1, BackColor = DividerColor };

            var textHost = new Panel
            {
                Dock = DockStyle.Fill,
                Padding = new Padding(16, 0, 12, 10),
            };

            var titleLabel = MakeLine("Mail non lu", TitleColor,
                new Font("Segoe UI Semibold", 10.5f, FontStyle.Bold), TitleHeight);
            titleLabel.Click += (_, _) => OpenDetailPage();

            var whoLabel = MakeLine($"{alert.employee_username} ({alert.department})", MetaColor,
                new Font("Segoe UI", 8.5f), LineHeight);
            whoLabel.Cursor = Cursors.Hand;
            whoLabel.Click += (_, _) => OpenDetailPage();

            var fromLabel = MakeLine($"De : {alert.sender}", MetaColor,
                new Font("Segoe UI", 8.5f), LineHeight);
            fromLabel.Cursor = Cursors.Hand;
            fromLabel.Click += (_, _) => OpenDetailPage();

            var subjectLabel = MakeLine($"Sujet : {alert.subject}", MetaColor,
                new Font("Segoe UI", 8.5f), LineHeight);
            subjectLabel.Cursor = Cursors.Hand;
            subjectLabel.Click += (_, _) => OpenDetailPage();

            textHost.Controls.Add(subjectLabel);
            textHost.Controls.Add(fromLabel);
            textHost.Controls.Add(whoLabel);
            textHost.Controls.Add(titleLabel);

            Controls.Add(_reminderPanel);
            Controls.Add(divider);
            Controls.Add(textHost);
            Controls.Add(closeButton);
            Controls.Add(accentBar);
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
                Cursor = Cursors.Hand,
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