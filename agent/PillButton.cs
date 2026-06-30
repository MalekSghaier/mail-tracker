using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Windows.Forms;

namespace MailDetectorAgent
{
    /// <summary>
    /// Bouton en forme de pilule (coins totalement arrondis), dessiné à la
    /// main pour un rendu net et cohérent, sans bordure WinForms par défaut.
    /// Légère réaction visuelle au survol.
    /// </summary>
    public sealed class PillButton : Control
    {
        private Color _baseColor;
        private bool _hover;

        public PillButton(string text, Color baseColor)
        {
            Text = text;
            _baseColor = baseColor;
            ForeColor = Color.White;
            Font = new Font("Segoe UI", 8.5f, FontStyle.Bold);
            Cursor = Cursors.Hand;
            DoubleBuffered = true;
            SetStyle(ControlStyles.SupportsTransparentBackColor, true);
            BackColor = Color.Transparent;

            MouseEnter += (_, _) => { _hover = true; Invalidate(); };
            MouseLeave += (_, _) => { _hover = false; Invalidate(); };
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            var g = e.Graphics;
            g.SmoothingMode = SmoothingMode.AntiAlias;

            var rect = new Rectangle(0, 0, Width - 1, Height - 1);
            var radius = Height;
            using var path = RoundedRect(rect, radius);

            var fillColor = _hover ? ControlPaint.Light(_baseColor, 0.15f) : _baseColor;
            using (var brush = new SolidBrush(fillColor))
            {
                g.FillPath(brush, path);
            }

            TextRenderer.DrawText(g, Text, Font, rect, ForeColor,
                TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter);
        }

        private static GraphicsPath RoundedRect(Rectangle rect, int diameter)
        {
            var path = new GraphicsPath();
            var arcRect = new Rectangle(rect.X, rect.Y, diameter, rect.Height);
            path.AddArc(arcRect, 90, 180);
            arcRect.X = rect.Right - diameter;
            path.AddArc(arcRect, 270, 180);
            path.CloseFigure();
            return path;
        }
    }
}