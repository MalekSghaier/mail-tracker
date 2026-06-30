using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Windows.Forms;

namespace MailDetectorAgent
{
    /// <summary>
    /// Case à cocher circulaire moderne (cercle + coche ou croix + libellé),
    /// utilisée pour répondre "Oui" / "Non" à la question de rappel.
    /// Le clic déclenche immédiatement la réponse (pas d'état "coché en
    /// attente" : la sélection vaut validation).
    /// </summary>
    public sealed class AnswerOption : Control
    {
        private const int CircleSize = 20;
        private readonly bool _isYes;
        private readonly Color _accent;
        private bool _hover;

        public event Action<bool>? Answered;

        public AnswerOption(string label, bool isYes, Color accent)
        {
            _isYes = isYes;
            _accent = accent;
            Text = label;
            ForeColor = Color.FromArgb(255, 224, 224, 230);
            Font = new Font("Segoe UI", 8.75f, FontStyle.Regular);
            Cursor = Cursors.Hand;
            DoubleBuffered = true;
            SetStyle(ControlStyles.SupportsTransparentBackColor | ControlStyles.OptimizedDoubleBuffer
                     | ControlStyles.UserPaint | ControlStyles.AllPaintingInWmPaint, true);
            BackColor = Color.Transparent;

            using var g = CreateGraphics();
            int textWidth = TextRenderer.MeasureText(g, label, Font).Width;
            Size = new Size(CircleSize + 8 + textWidth + 4, CircleSize + 2);

            MouseEnter += (_, _) => { _hover = true; Invalidate(); };
            MouseLeave += (_, _) => { _hover = false; Invalidate(); };
            Click += (_, _) => Answered?.Invoke(_isYes);
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            var g = e.Graphics;
            g.SmoothingMode = SmoothingMode.AntiAlias;

            var circleRect = new Rectangle(0, (Height - CircleSize) / 2, CircleSize, CircleSize);

            using (var pen = new Pen(_hover ? _accent : Color.FromArgb(255, 110, 110, 120), 1.8f))
            {
                g.DrawEllipse(pen, circleRect);
            }

            using (var glyphPen = new Pen(_accent, 2f) { StartCap = LineCap.Round, EndCap = LineCap.Round })
            {
                if (_isYes)
                {
                    // Coche
                    var p1 = new Point(circleRect.Left + 5, circleRect.Top + 10);
                    var p2 = new Point(circleRect.Left + 8, circleRect.Top + 13);
                    var p3 = new Point(circleRect.Left + 15, circleRect.Top + 6);
                    g.DrawLine(glyphPen, p1, p2);
                    g.DrawLine(glyphPen, p2, p3);
                }
                else
                {
                    // Croix
                    g.DrawLine(glyphPen, circleRect.Left + 6, circleRect.Top + 6, circleRect.Right - 6, circleRect.Bottom - 6);
                    g.DrawLine(glyphPen, circleRect.Right - 6, circleRect.Top + 6, circleRect.Left + 6, circleRect.Bottom - 6);
                }
            }

            var textRect = new Rectangle(CircleSize + 8, 0, Width - CircleSize - 8, Height);
            TextRenderer.DrawText(g, Text, Font, textRect,
                _hover ? Color.White : ForeColor,
                TextFormatFlags.VerticalCenter | TextFormatFlags.Left);
        }
    }
}