using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Windows.Forms;

namespace MailDetectorAgent
{
    /// <summary>
    /// Panneau type "Centre de notifications Windows" : ancré sur le bord
    /// droit de l'écran, hauteur pleine, liste défilante de toutes les
    /// alertes en attente. Fermer une carte (croix) déclenche l'ack et
    /// retire la carte de la liste.
    /// </summary>
    public sealed class NotificationCenterForm : Form
    {
        private readonly FlowLayoutPanel _list;
        private readonly Action<string> _onDismiss;

        public NotificationCenterForm(List<AlertDto> alerts, Action<string> onDismiss)
        {
            _onDismiss = onDismiss;

            FormBorderStyle = FormBorderStyle.None;
            StartPosition = FormStartPosition.Manual;
            ShowInTaskbar = false;
            TopMost = true;
            BackColor = Color.FromArgb(255, 24, 24, 27);

            var workingArea = Screen.PrimaryScreen.WorkingArea;
            Width = 360;
            Height = workingArea.Height - 20;
            Location = new Point(workingArea.Right - Width - 10, workingArea.Top + 10);

            var header = new Label
            {
                Text = "Notifications",
                ForeColor = Color.White,
                Font = new Font("Segoe UI", 11, FontStyle.Bold),
                Dock = DockStyle.Top,
                Height = 42,
                Padding = new Padding(14, 12, 0, 0),
            };

            var closeHeader = new Label
            {
                Text = "✕",
                ForeColor = Color.FromArgb(255, 160, 160, 166),
                Font = new Font("Segoe UI", 10),
                Dock = DockStyle.Right,
                Width = 36,
                TextAlign = ContentAlignment.MiddleCenter,
                Cursor = Cursors.Hand,
            };
            closeHeader.Click += (_, _) => Close();

            var headerBar = new Panel { Dock = DockStyle.Top, Height = 42 };
            headerBar.Controls.Add(closeHeader);
            headerBar.Controls.Add(header);

            _list = new FlowLayoutPanel
            {
                Dock = DockStyle.Fill,
                FlowDirection = FlowDirection.TopDown,
                WrapContents = false,
                AutoScroll = true,
                Padding = new Padding(10, 4, 10, 10),
                BackColor = BackColor,
            };

            Controls.Add(_list);
            Controls.Add(headerBar);

            // Clic n'importe où ailleurs sur l'écran -> le panneau se cache,
            // seule la bulle reste affichée (comportement type Action Center)
            Deactivate += (_, _) => Close();

            RefreshList(alerts);
        }

        public void RefreshList(List<AlertDto> alerts)
        {
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
            int cardWidth = 320;
            int cardHeight = 24 + 20 + (metaLines * 16) + 46;

            var card = new Panel
            {
                Width = cardWidth,
                Height = cardHeight,
                BackColor = Color.FromArgb(255, 38, 38, 42),
                Margin = new Padding(0, 0, 0, 10),
            };
            ApplyRounded(card, 12, cardWidth, cardHeight);

            var accent = new Panel
            {
                BackColor = Color.FromArgb(255, 245, 166, 35),
                Dock = DockStyle.Left,
                Width = 4,
            };

            var close = new Label
            {
                Text = "✕",
                ForeColor = Color.FromArgb(255, 130, 130, 136),
                Font = new Font("Segoe UI", 9),
                Dock = DockStyle.Top,
                TextAlign = ContentAlignment.MiddleRight,
                Height = 22,
                Padding = new Padding(0, 4, 10, 0),
                Cursor = Cursors.Hand,
            };
            close.MouseEnter += (_, _) => close.ForeColor = Color.White;
            close.MouseLeave += (_, _) => close.ForeColor = Color.FromArgb(255, 130, 130, 136);
            close.Click += (_, _) => _onDismiss(alert.tracking_id);

            var content = new Panel
            {
                Dock = DockStyle.Fill,
                Padding = new Padding(12, 0, 10, 8),
            };

            var title = MakeLine("Mail non ouvert", Color.White, new Font("Segoe UI", 9.5f, FontStyle.Bold), 20);
            var from = MakeLine($"De : {alert.sender}", Color.FromArgb(255, 160, 160, 166), new Font("Segoe UI", 8f), 16);
            var to = MakeLine($"À : {alert.recipient}", Color.FromArgb(255, 160, 160, 166), new Font("Segoe UI", 8f), 16);

            content.Controls.Add(MakeLine("Résumé : " + alert.summary, Color.FromArgb(255, 220, 220, 226),
                new Font("Segoe UI", 8.25f), 40, fill: true));

            if (hasCc)
            {
                content.Controls.Add(MakeLine($"Cc : {alert.cc}", Color.FromArgb(255, 160, 160, 166),
                    new Font("Segoe UI", 8f), 16));
            }
            content.Controls.Add(to);
            content.Controls.Add(from);
            content.Controls.Add(title);

            card.Controls.Add(content);
            card.Controls.Add(close);
            card.Controls.Add(accent);

            return card;
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
    }
}