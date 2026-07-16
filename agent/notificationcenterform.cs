using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Windows.Forms;

namespace MailDetectorAgent
{
    /// <summary>
    /// Panneau type "Centre de notifications", style chic (navy + accent
    /// doré). Chaque carte affiche la question "Rappel effectué ?" centrée
    /// avec deux cases à cocher rondes (Oui/Non), ou le statut une fois
    /// répondu. Le badge de compteur dans l'en-tête est positionné
    /// dynamiquement pour ne jamais chevaucher le titre.
    /// </summary>
    public sealed class NotificationCenterForm : Form
    {
        private static readonly Color PanelBg = Color.FromArgb(255, 16, 16, 22);
        private static readonly Color CardBg = Color.FromArgb(255, 26, 26, 34);
        private static readonly Color GoldAccent = Color.FromArgb(255, 212, 175, 90);
        private static readonly Color MetaColor = Color.FromArgb(255, 150, 150, 162);
        private static readonly Color SummaryColor = Color.FromArgb(255, 222, 222, 230);
        private static readonly Color DividerColor = Color.FromArgb(255, 42, 42, 52);
        private static readonly Color ValidatedColor = Color.FromArgb(255, 72, 178, 128);
        private static readonly Color NotValidatedColor = Color.FromArgb(255, 212, 96, 96);

        private const int CardWidth = 332;

        private readonly FlowLayoutPanel _list;
        private readonly Label _titleLabel;
        private readonly Label _countLabel;
        private readonly Action<string> _onDismiss;
        private readonly Func<string, bool?> _getReminderStatus;
        private readonly Action<string, bool> _setReminderStatus;
        private readonly string _apiBase;

        public NotificationCenterForm(
            List<AlertDto> alerts,
            Action<string> onDismiss,
            Func<string, bool?> getReminderStatus,
            Action<string, bool> setReminderStatus,
            string apiBase)
        {
            _onDismiss = onDismiss;
            _getReminderStatus = getReminderStatus;
            _setReminderStatus = setReminderStatus;
            _apiBase = apiBase; 

            FormBorderStyle = FormBorderStyle.None;
            StartPosition = FormStartPosition.Manual;
            ShowInTaskbar = false;
            TopMost = true;
            BackColor = PanelBg;

            var workingArea = Screen.PrimaryScreen?.WorkingArea ?? new Rectangle(0, 0, 1920, 1080);
            Width = 380;
            Height = workingArea.Height - 20;
            Location = new Point(workingArea.Right - Width - 10, workingArea.Top + 10);

            var headerBar = new Panel { Dock = DockStyle.Top, Height = 56 };

            var titleRow = new Panel { Dock = DockStyle.Top, Height = 40, Padding = new Padding(20, 16, 16, 0) };

            _titleLabel = new Label
            {
                Text = "Notifications",
                ForeColor = Color.White,
                Font = new Font("Segoe UI Semibold", 12.5f, FontStyle.Bold),
                AutoSize = true,
                Location = new Point(0, 0),
            };

            _countLabel = new Label
            {
                ForeColor = Color.FromArgb(255, 20, 20, 26),
                BackColor = GoldAccent,
                Font = new Font("Segoe UI", 8f, FontStyle.Bold),
                AutoSize = false,
                Size = new Size(26, 20),
                TextAlign = ContentAlignment.MiddleCenter,
            };
            RoundLabel(_countLabel, 10);

            var closeHeader = new Label
            {
                Text = "✕",
                ForeColor = Color.FromArgb(255, 140, 140, 150),
                Font = new Font("Segoe UI", 10),
                Dock = DockStyle.Right,
                Width = 44,
                TextAlign = ContentAlignment.MiddleCenter,
                Cursor = Cursors.Hand,
            };
            closeHeader.MouseEnter += (_, _) => closeHeader.ForeColor = Color.White;
            closeHeader.MouseLeave += (_, _) => closeHeader.ForeColor = Color.FromArgb(255, 140, 140, 150);
            closeHeader.Click += (_, _) => Close();

            titleRow.Controls.Add(_countLabel);
            titleRow.Controls.Add(_titleLabel);

            // Position du badge calculée dynamiquement après mesure réelle du
            // texte du titre, pour ne jamais le chevaucher (corrige le bug
            // de chevauchement "Notification[4]s").
            PositionCountBadge();

            var divider = new Panel { Dock = DockStyle.Bottom, Height = 1, BackColor = DividerColor };
            headerBar.Controls.Add(divider);
            headerBar.Controls.Add(titleRow);
            headerBar.Controls.Add(closeHeader);

            _list = new FlowLayoutPanel
            {
                Dock = DockStyle.Fill,
                FlowDirection = FlowDirection.TopDown,
                WrapContents = false,
                AutoScroll = true,
                Padding = new Padding(16, 12, 16, 16),
                BackColor = PanelBg,
            };

            Controls.Add(_list);
            Controls.Add(headerBar);

            Deactivate += (_, _) => Close();

            RefreshList(alerts);
        }

        private void PositionCountBadge()
        {
            using var g = CreateGraphics();
            int titleWidth = TextRenderer.MeasureText(g, _titleLabel.Text, _titleLabel.Font).Width;
            _countLabel.Location = new Point(titleWidth + 12, 1);
        }

        public void RefreshList(List<AlertDto> alerts)
        {
            _countLabel.Text = alerts.Count.ToString();
            PositionCountBadge();

            _list.SuspendLayout();
            _list.Controls.Clear();
            foreach (var alert in alerts)
            {
                _list.Controls.Add(BuildCard(alert));
            }
            _list.ResumeLayout();

            if (alerts.Count == 0) Close();
        }

        private Control BuildCard(AlertDto alert)
        {
            bool hasCc = !string.IsNullOrWhiteSpace(alert.cc);
            int metaLines = hasCc ? 3 : 2;
            int reminderHeight = 58;
            int cardHeight = 16 + 22 + (metaLines * 17) + 8 + 40 + 12 + 1 + reminderHeight;

            var card = new Panel
            {
                Width = CardWidth,
                Height = cardHeight,
                BackColor = CardBg,
                Margin = new Padding(0, 0, 0, 12),
            };
            ApplyRounded(card, 16, CardWidth, cardHeight);

            var accent = new Panel
            {
                BackColor = alert.category switch
                {
                    "seen_no_answer" => Color.FromArgb(255, 90, 156, 240), // bleu
                    _                => GoldAccent,                         // doré
                },
                Dock = DockStyle.Left,
                Width = 4,
            };

            var close = new Label
            {
                Text = "✕",
                ForeColor = Color.FromArgb(255, 120, 120, 130),
                Font = new Font("Segoe UI", 8.5f),
                Dock = DockStyle.Top,
                TextAlign = ContentAlignment.MiddleRight,
                Height = 24,
                Padding = new Padding(0, 8, 12, 0),
                Cursor = Cursors.Hand,
            };
            close.MouseEnter += (_, _) => close.ForeColor = Color.White;
            close.MouseLeave += (_, _) => close.ForeColor = Color.FromArgb(255, 120, 120, 130);
            close.Click += (_, _) => _onDismiss(alert.tracking_id);

            var content = new Panel
            {
                Dock = DockStyle.Top,
                Height = 16 + (metaLines * 17) + 8 + 40,
                Padding = new Padding(16, 0, 14, 0),
            };

            string titleText = alert.category switch
            {
                "seen_no_answer" => "Vu — rappel en attente",
                _                => "Mail non ouvert",
            };
            var title = MakeLine(titleText, Color.White, new Font("Segoe UI Semibold", 9.75f, FontStyle.Bold), 22);
            title.Cursor = Cursors.Hand;
            title.Click += (_, _) => OpenDetailPage(alert.tracking_id);
            var from = MakeLine($"De : {alert.sender}", MetaColor, new Font("Segoe UI", 8.25f), 17);
            var to = MakeLine($"À : {alert.recipient}", MetaColor, new Font("Segoe UI", 8.25f), 17);

            var summary = MakeLine("Résumé : " + alert.summary, SummaryColor,
                new Font("Segoe UI", 8.25f), 40, fill: true);
            summary.Padding = new Padding(0, 6, 0, 0);

            content.Controls.Add(summary);
            if (hasCc)
            {
                var cc = MakeLine($"Cc : {alert.cc}", MetaColor, new Font("Segoe UI", 8.25f), 17);
                content.Controls.Add(cc);
            }
            content.Controls.Add(to);
            content.Controls.Add(from);
            content.Controls.Add(title);

            var innerDivider = new Panel { Dock = DockStyle.Top, Height = 1, BackColor = DividerColor };

            var reminderPanel = new Panel
            {
                Dock = DockStyle.Top,
                Height = reminderHeight,
                BackColor = CardBg,
            };
            BuildReminderContent(reminderPanel, alert.tracking_id);

            card.Controls.Add(reminderPanel);
            card.Controls.Add(innerDivider);
            card.Controls.Add(content);
            card.Controls.Add(close);
            card.Controls.Add(accent);

            return card;
        }

        private void AnswerAndConfirm(Panel reminderPanel, string trackingId, bool done)
        {
            _setReminderStatus(trackingId, done); // persiste en base via le backend

            // Affiche un message de confirmation dans la carte, puis retire
            // l'alerte (comme la croix) après un court délai — pour Oui ET Non.
            reminderPanel.Controls.Clear();
            var confirmLabel = new Label
            {
                Text = done ? "✓ Réponse enregistrée — Oui" : "✓ Réponse enregistrée — Non",
                ForeColor = done ? ValidatedColor : NotValidatedColor,
                Font = new Font("Segoe UI", 8.5f, FontStyle.Bold),
                Dock = DockStyle.Fill,
                TextAlign = ContentAlignment.MiddleCenter,
            };
            reminderPanel.Controls.Add(confirmLabel);

            var confirmTimer = new System.Windows.Forms.Timer { Interval = 1100 };
            confirmTimer.Tick += (_, _) =>
            {
                confirmTimer.Stop();
                confirmTimer.Dispose();
                _onDismiss(trackingId); // ack + retrait, déclenche RefreshList via le manager
            };
            confirmTimer.Start();
        }

        private void BuildReminderContent(Panel reminderPanel, string trackingId)
        {
            reminderPanel.Controls.Clear();
            var status = _getReminderStatus(trackingId);

            if (status == null)
            {
                var question = new Label
                {
                    Text = "Rappel effectué ?",
                    ForeColor = Color.FromArgb(255, 200, 200, 208),
                    Font = new Font("Segoe UI", 8.5f),
                    Dock = DockStyle.Top,
                    Height = 20,
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

                optOui.Answered += (done) => AnswerAndConfirm(reminderPanel, trackingId, done);
                optNon.Answered += (done) => AnswerAndConfirm(reminderPanel, trackingId, done);

                optionsRow.Controls.Add(optOui);
                optionsRow.Controls.Add(optNon);

                reminderPanel.Controls.Add(optionsRow);
                reminderPanel.Controls.Add(question);
            }
            else
            {
                bool done = status.Value;
                var statusLabel = new Label
                {
                    Text = done ? "●  Validé — rappel effectué" : "●  Non validé — rappel non effectué",
                    ForeColor = done ? ValidatedColor : NotValidatedColor,
                    Font = new Font("Segoe UI", 8.5f, FontStyle.Bold),
                    Dock = DockStyle.Fill,
                    TextAlign = ContentAlignment.MiddleCenter,
                };
                reminderPanel.Controls.Add(statusLabel);
            }
        }

        private void OpenDetailPage(string trackingId)
        {
            try
            {
                System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo
                {
                    FileName = $"{_apiBase}/mail/{trackingId}",
                    UseShellExecute = true,
                });
            }
            catch { }
        }

        private static Label MakeLine(string text, Color color, Font font, int height, bool fill = false)
        {
            return new Label
            {
                Text = text,
                ForeColor = color,
                Font = font,
                Dock = fill ? DockStyle.Fill : DockStyle.Top,
                Height = height,
                AutoEllipsis = true,
            };
        }

        private static void ApplyRounded(Control control, int radius, int width, int height)
        {
            var path = new GraphicsPath();
            var rect = new Rectangle(0, 0, width, height);
            int r = radius;
            path.AddArc(rect.X, rect.Y, r, r, 180, 90);
            path.AddArc(rect.Right - r, rect.Y, r, r, 270, 90);
            path.AddArc(rect.Right - r, rect.Bottom - r, r, r, 0, 90);
            path.AddArc(rect.X, rect.Bottom - r, r, r, 90, 90);
            path.CloseFigure();
            control.Region = new Region(path);
        }

        private static void RoundLabel(Label label, int radius)
        {
            var path = new GraphicsPath();
            var rect = new Rectangle(0, 0, label.Width, label.Height);
            int r = radius;
            path.AddArc(rect.X, rect.Y, r, r, 180, 90);
            path.AddArc(rect.Right - r, rect.Y, r, r, 270, 90);
            path.AddArc(rect.Right - r, rect.Bottom - r, r, r, 0, 90);
            path.AddArc(rect.X, rect.Bottom - r, r, r, 90, 90);
            path.CloseFigure();
            label.Region = new Region(path);
        }
    }
}