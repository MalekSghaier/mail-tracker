using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Linq;
using System.Windows.Forms;

namespace MailDetectorAgent
{
    /// <summary>
    /// Centre de notifications pour le scénario B — même style que
    /// NotificationCenterForm, sans la question Oui/Non (pas de rappel
    /// pour les mails reçus), juste un statut "Non lu depuis" par carte.
    /// </summary>
    public sealed class ImapNotificationCenterForm : Form
    {
        private static readonly Color PanelBg = Color.FromArgb(255, 16, 16, 22);
        private static readonly Color CardBg = Color.FromArgb(255, 26, 26, 34);
        private static readonly Color GoldAccent = Color.FromArgb(255, 212, 175, 90);
        private static readonly Color MetaColor = Color.FromArgb(255, 150, 150, 162);
        private static readonly Color DividerColor = Color.FromArgb(255, 42, 42, 52);
        private static readonly Color WarningColor = Color.FromArgb(255, 232, 160, 64);

        private const int CardWidth = 332;

        private readonly FlowLayoutPanel _list;
        private readonly Label _titleLabel;
        private readonly Label _countLabel;
        private readonly Action<string> _onDismiss;

        public ImapNotificationCenterForm(List<ImapAlertDto> alerts, Action<string> onDismiss)
        {
            _onDismiss = onDismiss;

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
                Text = "Mails non lus (équipe)",
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

        public void RefreshList(List<ImapAlertDto> alerts)
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

        private Control BuildCard(ImapAlertDto alert)
        {
            int cardHeight = 16 + 22 + (3 * 17) + 8 + 1 + 34;

            var card = new Panel
            {
                Width = CardWidth,
                Height = cardHeight,
                BackColor = CardBg,
                Margin = new Padding(0, 0, 0, 12),
            };
            ApplyRounded(card, 16, CardWidth, cardHeight);

            var accent = new Panel { BackColor = GoldAccent, Dock = DockStyle.Left, Width = 4 };

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
            close.Click += (_, _) => _onDismiss(alert.Key);

            var content = new Panel
            {
                Dock = DockStyle.Top,
                Height = 16 + (3 * 17) + 8,
                Padding = new Padding(16, 0, 14, 0),
            };

            var title = MakeLine("Mail non lu", Color.White, new Font("Segoe UI Semibold", 9.75f, FontStyle.Bold), 22);
            var who = MakeLine($"{alert.employee_username} ({alert.department})", MetaColor, new Font("Segoe UI", 8.25f), 17);
            var from = MakeLine($"De : {alert.sender}", MetaColor, new Font("Segoe UI", 8.25f), 17);
            var subject = MakeLine($"Sujet : {alert.subject}", MetaColor, new Font("Segoe UI", 8.25f), 17);

            content.Controls.Add(subject);
            content.Controls.Add(from);
            content.Controls.Add(who);
            content.Controls.Add(title);

            var innerDivider = new Panel { Dock = DockStyle.Top, Height = 1, BackColor = DividerColor };

            var statusPanel = new Panel { Dock = DockStyle.Top, Height = 34, BackColor = CardBg };
            var statusLabel = new Label
            {
                Text = $"●  Non lu — reçu le {FormatDate(alert.received_at)}",
                ForeColor = WarningColor,
                Font = new Font("Segoe UI", 8.5f, FontStyle.Bold),
                Dock = DockStyle.Fill,
                TextAlign = ContentAlignment.MiddleCenter,
            };
            statusPanel.Controls.Add(statusLabel);

            card.Controls.Add(statusPanel);
            card.Controls.Add(innerDivider);
            card.Controls.Add(content);
            card.Controls.Add(close);
            card.Controls.Add(accent);

            return card;
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