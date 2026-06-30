using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Windows.Forms;

namespace MailDetectorAgent
{
    /// <summary>
    /// Icône flottante (carré arrondi bleu-teal) avec un badge rouge
    /// (cerclé de blanc) en haut à droite affichant le nombre d'alertes
    /// en attente. Tout est dessiné à la main via OnPaint (pas de contrôles
    /// enfants empilés) pour éviter les bugs de rendu/transparence/z-order
    /// classiques de WinForms avec des formes superposées.
    /// Un clic n'importe où ouvre le panneau listant toutes les alertes.
    /// </summary>
    public sealed class BadgeForm : Form
    {
        private const int IconSize = 56;
        private const int BadgeSize = 26;
        private const int RingPad = 3;
        private const int TotalSize = 72;

        private static readonly Color IconColor = Color.FromArgb(255, 0, 150, 199);   // bleu-teal
        private static readonly Color BadgeColor = Color.FromArgb(255, 220, 53, 69);  // rouge vif

        private readonly Rectangle _iconRect = new(0, TotalSize - IconSize, IconSize, IconSize);
        private readonly Rectangle _badgeRect;
        private readonly Rectangle _ringRect;
        private readonly ToolTip _toolTip = new();
        private readonly Action _onClick;
        private int _count;

        public BadgeForm(int count, Action onClick)
        {
            _onClick = onClick;
            _count = count;

            _badgeRect = new Rectangle(TotalSize - BadgeSize - 2, 2, BadgeSize, BadgeSize);
            _ringRect = Rectangle.Inflate(_badgeRect, RingPad, RingPad);

            FormBorderStyle = FormBorderStyle.None;
            StartPosition = FormStartPosition.Manual;
            ShowInTaskbar = false;
            TopMost = true;
            Width = TotalSize;
            Height = TotalSize;
            DoubleBuffered = true;
            Cursor = Cursors.Hand;

            var ringPath = new GraphicsPath();
            ringPath.AddEllipse(_ringRect);
            var combined = new Region(RoundedRectPath(_iconRect, 16));
            combined.Union(ringPath);
            Region = combined;

            var workingArea = Screen.PrimaryScreen.WorkingArea;
            Location = new Point(workingArea.Right - TotalSize - 12, workingArea.Bottom - TotalSize - 12);

            Click += (_, _) => _onClick();
            UpdateTooltip();
        }

        public void UpdateCount(int count)
        {
            _count = count;
            UpdateTooltip();
            Invalidate();
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            base.OnPaint(e);
            var g = e.Graphics;
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.TextRenderingHint = System.Drawing.Text.TextRenderingHint.ClearTypeGridFit;

            // Icône (carré arrondi bleu) + symbole enveloppe
            using (var iconBrush = new SolidBrush(IconColor))
            using (var iconPath = RoundedRectPath(_iconRect, 16))
            {
                g.FillPath(iconBrush, iconPath);
            }
            TextRenderer.DrawText(g, "✉", new Font("Segoe UI Symbol", 18), _iconRect,
                Color.White, TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter);

            // Anneau blanc puis badge rouge par-dessus (ordre de dessin = ordre d'empilement garanti)
            using (var ringBrush = new SolidBrush(Color.White))
            {
                g.FillEllipse(ringBrush, _ringRect);
            }
            using (var badgeBrush = new SolidBrush(BadgeColor))
            {
                g.FillEllipse(badgeBrush, _badgeRect);
            }

            string text = _count > 9 ? "9+" : _count.ToString();
            TextRenderer.DrawText(g, text, new Font("Segoe UI", 9.5f, FontStyle.Bold), _badgeRect,
                Color.White, TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter);
        }

        private void UpdateTooltip()
        {
            _toolTip.SetToolTip(this, $"{_count} mails non ouverts — cliquez pour les voir");
        }

        private static GraphicsPath RoundedRectPath(Rectangle rect, int radius)
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