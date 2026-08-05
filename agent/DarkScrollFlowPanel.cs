using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Windows.Forms;

namespace MailDetectorAgent
{
    public class DarkScrollFlowPanel : Panel
    {
        private static readonly Color PanelBg = Color.FromArgb(255, 16, 16, 22);
        private static readonly Color ThumbColor = Color.FromArgb(255, 212, 175, 90);
        private static readonly Color ThumbHoverColor = Color.FromArgb(255, 240, 200, 110);
        private static readonly Color TrackColor = Color.FromArgb(255, 30, 30, 40);

        private const int ScrollbarWidth = 8;
        private const int ThumbMinHeight = 30;

        private int _scrollOffset;
        private int _contentHeight;
        private bool _thumbVisible;
        private int _thumbHeight;
        private int _thumbPosition;

        private bool _thumbHover;
        private bool _thumbPressed;
        private int _dragStartY;
        private int _dragStartOffset;

        // Pour pouvoir retirer le filtre lors du Dispose
        private ScrollMessageFilter? _messageFilter;

        public DarkScrollFlowPanel()
        {
            BackColor = PanelBg;
            SetStyle(ControlStyles.OptimizedDoubleBuffer |
                     ControlStyles.AllPaintingInWmPaint |
                     ControlStyles.ResizeRedraw |
                     ControlStyles.UserPaint, true);
            AutoScroll = false;

            Paint += OnPaintCustom;
            MouseDown += OnMouseDownCustom;
            MouseMove += OnMouseMoveCustom;
            MouseUp += OnMouseUpCustom;
            MouseLeave += (_, _) => { _thumbHover = false; InvalidateScrollbar(); };

            // Ajouter le filtre global (stocké pour suppression ultérieure)
            _messageFilter = new ScrollMessageFilter(this);
            Application.AddMessageFilter(_messageFilter);
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing)
            {
                // Retirer le filtre pour éviter les appels sur un contrôle détruit
                if (_messageFilter != null)
                {
                    Application.RemoveMessageFilter(_messageFilter);
                    _messageFilter = null;
                }
            }
            base.Dispose(disposing);
        }

        protected override void OnLayout(LayoutEventArgs e)
        {
            base.OnLayout(e);
            DoLayout();
        }

        protected override void OnControlAdded(ControlEventArgs e)
        {
            base.OnControlAdded(e);
            DoLayout();
        }

        protected override void OnControlRemoved(ControlEventArgs e)
        {
            base.OnControlRemoved(e);
            DoLayout();
        }

        private void DoLayout()
        {
            if (IsDisposed || Controls.Count == 0)
            {
                _contentHeight = 0;
                _thumbVisible = false;
                _scrollOffset = 0;
                InvalidateScrollbar();
                return;
            }

            int viewportHeight = ClientSize.Height;
            int y = Padding.Top;

            foreach (Control c in Controls)
            {
                int availableWidth = ClientSize.Width - Padding.Horizontal - ScrollbarWidth;
                c.Width = Math.Max(0, Math.Min(c.Width, availableWidth));
                c.Left = Padding.Left;

                int naturalY = y + c.Margin.Top;
                c.Top = naturalY - _scrollOffset;
                y += c.Margin.Top + c.Height + c.Margin.Bottom;
            }

            _contentHeight = y + Padding.Bottom;

            if (_contentHeight <= viewportHeight)
            {
                _thumbVisible = false;
                _scrollOffset = 0;
            }
            else
            {
                _thumbVisible = true;
                int maxScroll = _contentHeight - viewportHeight;

                if (_scrollOffset < 0) _scrollOffset = 0;
                if (_scrollOffset > maxScroll) _scrollOffset = maxScroll;

                _thumbHeight = Math.Max(ThumbMinHeight,
                    (int)((float)viewportHeight / _contentHeight * viewportHeight));
                int maxThumbPos = viewportHeight - _thumbHeight;
                _thumbPosition = (maxScroll > 0)
                    ? (int)((float)_scrollOffset / maxScroll * maxThumbPos)
                    : 0;
            }

            y = Padding.Top;
            foreach (Control c in Controls)
            {
                c.Top = y + c.Margin.Top - _scrollOffset;
                y += c.Margin.Top + c.Height + c.Margin.Bottom;
            }

            InvalidateScrollbar();
        }

        private void InvalidateScrollbar()
        {
            if (!IsHandleCreated) return;
            Rectangle scrollRect = new Rectangle(ClientSize.Width - ScrollbarWidth, 0,
                                                 ScrollbarWidth, ClientSize.Height);
            Invalidate(scrollRect);
        }

        // Correction des avertissements de nullabilité : paramètre 'sender' nullable
        private void OnPaintCustom(object? sender, PaintEventArgs e)
        {
            if (!_thumbVisible) return;
            Graphics g = e.Graphics;
            Rectangle scrollRect = new Rectangle(ClientSize.Width - ScrollbarWidth, 0,
                                                 ScrollbarWidth, ClientSize.Height);

            using (SolidBrush trackBrush = new SolidBrush(TrackColor))
                g.FillRectangle(trackBrush, scrollRect);

            Rectangle thumbRect = new Rectangle(
                scrollRect.X + 1, _thumbPosition + 1,
                scrollRect.Width - 2, _thumbHeight - 2);

            Color thumbCol = _thumbPressed ? ThumbHoverColor :
                             _thumbHover ? ThumbHoverColor : ThumbColor;

            using (GraphicsPath path = RoundedRect(thumbRect, 4))
            using (SolidBrush thumbBrush = new SolidBrush(thumbCol))
            {
                g.SmoothingMode = SmoothingMode.AntiAlias;
                g.FillPath(thumbBrush, path);
            }
        }

        private void OnMouseDownCustom(object? sender, MouseEventArgs e)
        {
            if (!_thumbVisible || e.Button != MouseButtons.Left) return;
            Point client = e.Location;
            Rectangle thumbRect = GetThumbRect();
            if (thumbRect.Contains(client))
            {
                _thumbPressed = true;
                _dragStartY = client.Y;
                _dragStartOffset = _scrollOffset;
                InvalidateScrollbar();
            }
        }

        private void OnMouseMoveCustom(object? sender, MouseEventArgs e)
        {
            if (!_thumbVisible) return;
            Point client = e.Location;

            if (_thumbPressed)
            {
                int maxScroll = _contentHeight - ClientSize.Height;
                if (maxScroll <= 0) return;
                int deltaY = client.Y - _dragStartY;
                int maxThumbTravel = ClientSize.Height - _thumbHeight;
                float ratio = (float)maxScroll / maxThumbTravel;
                _scrollOffset = Math.Max(0, Math.Min(maxScroll,
                    _dragStartOffset + (int)(deltaY * ratio)));
                DoLayout();
                return;
            }

            Rectangle thumbRect = GetThumbRect();
            bool hover = thumbRect.Contains(client);
            if (hover != _thumbHover)
            {
                _thumbHover = hover;
                InvalidateScrollbar();
            }
        }

        private void OnMouseUpCustom(object? sender, MouseEventArgs e)
        {
            if (_thumbPressed)
            {
                _thumbPressed = false;
                InvalidateScrollbar();
            }
        }

        private Rectangle GetThumbRect()
        {
            return new Rectangle(ClientSize.Width - ScrollbarWidth + 1, _thumbPosition + 1,
                                 ScrollbarWidth - 2, _thumbHeight - 2);
        }

        private GraphicsPath RoundedRect(Rectangle bounds, int radius)
        {
            int diameter = radius * 2;
            Rectangle arc = new Rectangle(bounds.Location, new Size(diameter, diameter));
            GraphicsPath path = new GraphicsPath();

            if (radius == 0)
            {
                path.AddRectangle(bounds);
                return path;
            }

            path.AddArc(arc, 180, 90);
            arc.X = bounds.Right - diameter;
            path.AddArc(arc, 270, 90);
            arc.Y = bounds.Bottom - diameter;
            path.AddArc(arc, 0, 90);
            arc.X = bounds.Left;
            path.AddArc(arc, 90, 90);

            path.CloseFigure();
            return path;
        }

        private class ScrollMessageFilter : IMessageFilter
        {
            private readonly DarkScrollFlowPanel _panel;
            private const int WM_MOUSEWHEEL = 0x020A;

            public ScrollMessageFilter(DarkScrollFlowPanel panel)
            {
                _panel = panel;
            }

            public bool PreFilterMessage(ref Message m)
            {
                if (m.Msg == WM_MOUSEWHEEL)
                {
                    // Sécurité : ne rien faire si le panneau est déjà détruit
                    if (_panel.IsDisposed) return false;

                    try
                    {
                        Point pt = Control.MousePosition;
                        if (_panel.RectangleToScreen(_panel.ClientRectangle).Contains(pt) && _panel._thumbVisible)
                        {
                            int delta = (short)((m.WParam.ToInt32() >> 16) & 0xFFFF);
                            int step = 40;
                            _panel._scrollOffset = Math.Max(0,
                                _panel._scrollOffset - delta / SystemInformation.MouseWheelScrollDelta * step);
                            _panel.DoLayout();
                            return true; // message traité
                        }
                    }
                    catch (Exception ex)
                    {
                        // Journaliser l'erreur sans faire planter l'application
                        System.Diagnostics.Debug.WriteLine($"ScrollMessageFilter error: {ex.Message}");
                    }
                }
                return false;
            }
        }
    }
}