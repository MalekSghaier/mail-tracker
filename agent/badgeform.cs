using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Windows.Forms;

namespace MailDetectorAgent
{
    /// <summary>
    /// Bulle flottante circulaire au style "chic" : dégradé sombre, fine
    /// bordure dorée, ombre portée douce, icône d'enveloppe dessinée à la
    /// main (pas un emoji, pour un rendu net et cohérent sur toutes les
    /// machines), et un badge à dégradé rouge-orangé. Tout est dessiné via
    /// OnPaint pour un contrôle total du rendu.
    /// Un clic n'importe où ouvre le panneau listant toutes les alertes.
    /// </summary>
    public sealed class BadgeForm : Form
    {
        private const int BubbleSize = 64;
        private const int BadgeSize = 28;
        private const int ShadowOffset = 4;
        private const int TotalSize = BubbleSize + ShadowOffset + 6;

        private static readonly Color GoldAccent = Color.FromArgb(255, 212, 175, 90);

        private readonly Rectangle _bubbleRect;
        private readonly Rectangle _badgeRect;
        private readonly Rectangle _shadowRect;
        private readonly ToolTip _toolTip = new();
        private readonly Action _onClick;
        private readonly System.Windows.Forms.Timer _fadeTimer;
        private int _count;

        public BadgeForm(int count, Action onClick)
        {
            _onClick = onClick;
            _count = count;

            _bubbleRect = new Rectangle(2, 2, BubbleSize, BubbleSize);
            _shadowRect = new Rectangle(2 + ShadowOffset, 2 + ShadowOffset, BubbleSize, BubbleSize);
            _badgeRect = new Rectangle(
                _bubbleRect.Right - BadgeSize - 4,
                _bubbleRect.Top - 4,
                BadgeSize, BadgeSize);

            FormBorderStyle = FormBorderStyle.None;
            StartPosition = FormStartPosition.Manual;
            ShowInTaskbar = false;
            TopMost = true;
            Width = TotalSize;
            Height = TotalSize;
            DoubleBuffered = true;
            Cursor = Cursors.Hand;
            Opacity = 0;

            var combined = new Region(new Rectangle(0, 0, 0, 0));
            var shadowPath = new GraphicsPath();
            shadowPath.AddEllipse(Rectangle.Inflate(_shadowRect, 3, 3));
            combined.Union(shadowPath);
            var bubblePath = new GraphicsPath();
            bubblePath.AddEllipse(Rectangle.Inflate(_bubbleRect, 2, 2));
            combined.Union(bubblePath);
            var badgePath = new GraphicsPath();
            badgePath.AddEllipse(Rectangle.Inflate(_badgeRect, 2, 2));
            combined.Union(badgePath);
            Region = combined;

            var workingArea = Screen.PrimaryScreen.WorkingArea;
            Location = new Point(workingArea.Right - TotalSize - 12, workingArea.Bottom - TotalSize - 12);

            Click += (_, _) => _onClick();
            UpdateTooltip();

            _fadeTimer = new System.Windows.Forms.Timer { Interval = 15 };
            _fadeTimer.Tick += (_, _) =>
            {
                Opacity = Math.Min(1.0, Opacity + 0.10);
                if (Opacity >= 1.0) _fadeTimer.Stop();
            };
            Load += (_, _) => _fadeTimer.Start();
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

            // Ombre portée douce (cercle translucide décalé)
            using (var shadowBrush = new SolidBrush(Color.FromArgb(70, 0, 0, 0)))
            {
                g.FillEllipse(shadowBrush, _shadowRect);
            }

            // Bulle principale : dégradé sombre élégant (anthracite -> bleu nuit)
            using (var bubbleBrush = new LinearGradientBrush(
                _bubbleRect, Color.FromArgb(255, 44, 44, 84), Color.FromArgb(255, 22, 22, 42),
                LinearGradientMode.ForwardDiagonal))
            {
                g.FillEllipse(bubbleBrush, _bubbleRect);
            }

            // Fine bordure dorée façon "premium"
            using (var goldPen = new Pen(GoldAccent, 1.6f))
            {
                g.DrawEllipse(goldPen, Rectangle.Inflate(_bubbleRect, -1, -1));
            }

            // Icône enveloppe dessinée à la main (nette, pas un emoji)
            DrawEnvelope(g, _bubbleRect);

            // Badge : dégradé rouge-orangé
            using (var badgeBrush = new LinearGradientBrush(
                _badgeRect, Color.FromArgb(255, 255, 99, 72), Color.FromArgb(255, 214, 40, 40),
                LinearGradientMode.ForwardDiagonal))
            {
                g.FillEllipse(badgeBrush, _badgeRect);
            }

            string text = _count > 9 ? "9+" : _count.ToString();
            using (var font = new Font("Segoe UI", 11f, FontStyle.Bold))
            {
                TextRenderer.DrawText(g, text, font, _badgeRect, Color.White,
                    TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter);
            }
        }

        private static void DrawEnvelope(Graphics g, Rectangle bubbleRect)
        {
            int w = (int)(bubbleRect.Width * 0.46);
            int h = (int)(w * 0.68);
            int cx = bubbleRect.X + bubbleRect.Width / 2;
            int cy = bubbleRect.Y + bubbleRect.Height / 2;
            var rect = new Rectangle(cx - w / 2, cy - h / 2, w, h);

            using var pen = new Pen(Color.White, 1.8f) { LineJoin = LineJoin.Round };

            // Corps de l'enveloppe
            g.DrawRectangle(pen, rect);

            // Rabat (V renversé)
            var p1 = new Point(rect.Left, rect.Top);
            var pTop = new Point(rect.Left + rect.Width / 2, rect.Top + (int)(rect.Height * 0.55));
            var p2 = new Point(rect.Right, rect.Top);
            g.DrawLine(pen, p1, pTop);
            g.DrawLine(pen, pTop, p2);
        }

        private void UpdateTooltip()
        {
            _toolTip.SetToolTip(this, $"{_count} mails non ouverts — cliquez pour les voir");
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing) _fadeTimer?.Dispose();
            base.Dispose(disposing);
        }
    }
}