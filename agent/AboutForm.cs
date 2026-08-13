using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Reflection;
using System.Windows.Forms;

namespace MailDetectorAgent
{
    /// <summary>F43 : boîte "À propos" stylée selon le thème sombre/doré de
    /// l'application, plutôt qu'un MessageBox système générique.</summary>
    public sealed class AboutForm : Form
    {
        private static readonly Color PanelBg = Color.FromArgb(255, 16, 16, 22);
        private static readonly Color GoldAccent = Color.FromArgb(255, 212, 175, 90);
        private static readonly Color GoldDim = Color.FromArgb(255, 160, 124, 48);
        private static readonly Color MetaColor = Color.FromArgb(255, 150, 150, 162);
        private static readonly Color DividerColor = Color.FromArgb(255, 42, 42, 52);

        private const int FormWidth = 340;
        private const int FormHeight = 280;

        public AboutForm()
        {
            FormBorderStyle = FormBorderStyle.None;
            StartPosition = FormStartPosition.CenterScreen;
            ShowInTaskbar = false;
            TopMost = true;
            BackColor = PanelBg;
            Width = FormWidth;
            Height = FormHeight;

            ApplyRoundedRegion();
            BuildLayout();

            Deactivate += (_, _) => Close();
        }

        private void ApplyRoundedRegion()
        {
            var path = new GraphicsPath();
            const int r = 16;
            var rect = new Rectangle(0, 0, Width, Height);
            path.AddArc(rect.X, rect.Y, r, r, 180, 90);
            path.AddArc(rect.Right - r, rect.Y, r, r, 270, 90);
            path.AddArc(rect.Right - r, rect.Bottom - r, r, r, 0, 90);
            path.AddArc(rect.X, rect.Bottom - r, r, r, 90, 90);
            path.CloseFigure();
            Region = new Region(path);
        }

        private void BuildLayout()
        {
            var closeButton = new Label
            {
                Text = "✕",
                ForeColor = Color.FromArgb(255, 140, 140, 150),
                Font = new Font("Segoe UI", 10),
                TextAlign = ContentAlignment.MiddleCenter,
                Size = new Size(32, 28),
                Location = new Point(FormWidth - 40, 8),
                Cursor = Cursors.Hand,
            };
            closeButton.MouseEnter += (_, _) => closeButton.ForeColor = Color.White;
            closeButton.MouseLeave += (_, _) => closeButton.ForeColor = Color.FromArgb(255, 140, 140, 150);
            closeButton.Click += (_, _) => Close();

            var iconBadge = new Panel
            {
                Size = new Size(56, 56),
                BackColor = Color.Transparent,
            };
            iconBadge.Location = new Point((FormWidth - iconBadge.Width) / 2, 40);
            iconBadge.Paint += (_, e) =>
            {
                using var brush = new LinearGradientBrush(
                    new Rectangle(0, 0, iconBadge.Width, iconBadge.Height), GoldAccent, GoldDim, 45f);
                using var path = RoundedRect(new Rectangle(0, 0, iconBadge.Width, iconBadge.Height), 14);
                e.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
                e.Graphics.FillPath(brush, path);
                using var font = new Font("Segoe UI", 22f, FontStyle.Bold);
                var sf = new StringFormat { Alignment = StringAlignment.Center, LineAlignment = StringAlignment.Center };
                using var textBrush = new SolidBrush(Color.FromArgb(255, 23, 23, 26));
                e.Graphics.DrawString("✉", font, textBrush, new Rectangle(0, 0, iconBadge.Width, iconBadge.Height), sf);
            };

            var version = Assembly.GetExecutingAssembly().GetName().Version;
            var versionText = version != null ? version.ToString() : "inconnue";

            var titleLabel = new Label
            {
                Text = "Mail Detector Agent",
                ForeColor = Color.White,
                Font = new Font("Segoe UI Semibold", 13f, FontStyle.Bold),
                TextAlign = ContentAlignment.MiddleCenter,
                Size = new Size(FormWidth, 26),
                Location = new Point(0, 112),
            };

            var versionLabel = new Label
            {
                Text = $"Version {versionText}",
                ForeColor = GoldAccent,
                Font = new Font("Segoe UI", 9.5f),
                TextAlign = ContentAlignment.MiddleCenter,
                Size = new Size(FormWidth, 20),
                Location = new Point(0, 140),
            };

            var divider = new Panel
            {
                BackColor = DividerColor,
                Size = new Size(FormWidth - 64, 1),
                Location = new Point(32, 182),
            };

            var footerLabel = new Label
            {
                Text = "ARS Tunisie",
                ForeColor = MetaColor,
                Font = new Font("Segoe UI", 9f),
                TextAlign = ContentAlignment.MiddleCenter,
                Size = new Size(FormWidth, 22),
                Location = new Point(0, 200),
            };

            Controls.Add(footerLabel);
            Controls.Add(divider);
            Controls.Add(versionLabel);
            Controls.Add(titleLabel);
            Controls.Add(iconBadge);
            Controls.Add(closeButton);
        }

        private static GraphicsPath RoundedRect(Rectangle rect, int radius)
        {
            var path = new GraphicsPath();
            int r = radius;
            path.AddArc(rect.X, rect.Y, r, r, 180, 90);
            path.AddArc(rect.Right - r, rect.Y, r, r, 270, 90);
            path.AddArc(rect.Right - r, rect.Bottom - r, r, r, 0, 90);
            path.AddArc(rect.X, rect.Bottom - r, r, r, 90, 90);
            path.CloseFigure();
            return path;
        }
    }
}