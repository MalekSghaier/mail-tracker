using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace MailDetectorAgent
{
    /// <summary>
    /// Écran de connexion — affiché uniquement au premier lancement de
    /// l'agent sur ce PC, ou si la session a expiré / a été révoquée.
    /// L'utilisateur doit être un abonné créé au préalable par un admin
    /// ARS via /admin — aucune auto-inscription possible ici.
    ///
    /// Carte flottante sans bordure système, coins arrondis, dégradé doré,
    /// cohérente avec le style des popups (NotificationForm) et de la page
    /// d'administration.
    /// </summary>
    public sealed class LoginForm : Form
    {
        private const int CardWidth = 380;
        private const int CardHeight = 470;
        private const int CornerRadius = 20;

        private static readonly Color BgColor = Color.FromArgb(255, 24, 24, 32);
        private static readonly Color FieldBg = Color.FromArgb(255, 30, 30, 40);
        private static readonly Color BorderColor = Color.FromArgb(255, 44, 44, 56);
        private static readonly Color GoldAccent = Color.FromArgb(255, 212, 175, 90);
        private static readonly Color GoldDim = Color.FromArgb(255, 160, 124, 48);
        private static readonly Color TextColor = Color.White;
        private static readonly Color MetaColor = Color.FromArgb(255, 150, 150, 162);
        private static readonly Color ErrorColor = Color.FromArgb(255, 212, 96, 96);

        private readonly TextBox _usernameBox;
        private readonly TextBox _passwordBox;
        private readonly Label _errorLabel;
        private readonly GoldButton _loginButton;
        private readonly string _apiBase;
        private readonly HttpClient _http;
        private Point _dragStart;

        public string? Token { get; private set; }

        public LoginForm(string apiBase, HttpClient http)
        {
            _apiBase = apiBase;
            _http = http;

            FormBorderStyle = FormBorderStyle.None;
            StartPosition = FormStartPosition.CenterScreen;
            ClientSize = new Size(CardWidth, CardHeight);
            BackColor = BgColor;
            ShowInTaskbar = true;
            Text = "Mail Detector — Connexion"; // texte affiché au survol dans la barre des tâches
            Icon = IconHelper.GetTrayIcon();


            ApplyRoundedRegion();

            // ---------- en-tête (draggable) ----------
            var header = new Panel { Bounds = new Rectangle(0, 0, CardWidth, 64), BackColor = BgColor };
            header.MouseDown += (_, e) => _dragStart = e.Location;
            header.MouseMove += (_, e) =>
            {
                if (e.Button == MouseButtons.Left)
                    Location = new Point(Location.X + e.X - _dragStart.X, Location.Y + e.Y - _dragStart.Y);
            };

            var logoBadge = new Panel
            {
                Bounds = new Rectangle(24, 16, 32, 32),
                BackColor = Color.Transparent,
            };
            logoBadge.Paint += (_, e) =>
            {
                e.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
                var rect = new Rectangle(0, 0, 31, 31);
                using var path = RoundedPath(rect, 9);
                using var brush = new LinearGradientBrush(rect, GoldAccent, GoldDim, LinearGradientMode.ForwardDiagonal);
                e.Graphics.FillPath(brush, path);

                // Essaie d'afficher le vrai logo ; retombe sur l'emoji enveloppe
                // si le fichier est introuvable (POC sur un autre PC, par ex.).
                using var logoImg = IconHelper.GetLogoImage();
                if (logoImg != null)
                {
                    var inset = new Rectangle(5, 5, 21, 21);
                    e.Graphics.SetClip(path);
                    e.Graphics.DrawImage(logoImg, inset);
                    e.Graphics.ResetClip();
                }
                else
                {
                    TextRenderer.DrawText(e.Graphics, "✉", new Font("Segoe UI Emoji", 12f),
                      rect, Color.FromArgb(255, 24, 20, 12), TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter);
                }
            };

            var appName = new Label
            {
                Text = "Mail Detector",
                ForeColor = TextColor,
                Font = new Font("Segoe UI Semibold", 11f, FontStyle.Bold),
                Location = new Point(66, 24),
                AutoSize = true,
                BackColor = Color.Transparent,
            };

            var closeBtn = new Label
            {
                Text = "✕",
                ForeColor = MetaColor,
                Font = new Font("Segoe UI", 10f),
                Size = new Size(40, 30),
                Location = new Point(CardWidth - 52, 18),
                TextAlign = ContentAlignment.MiddleCenter,
                Cursor = Cursors.Hand,
                BackColor = Color.Transparent,
            };
            closeBtn.MouseEnter += (_, _) => closeBtn.ForeColor = ErrorColor;
            closeBtn.MouseLeave += (_, _) => closeBtn.ForeColor = MetaColor;
            closeBtn.Click += (_, _) =>
            {
                DialogResult = DialogResult.Cancel;
                Close();
            };

            header.Controls.Add(logoBadge);
            header.Controls.Add(appName);
            header.Controls.Add(closeBtn);

            var divider = new Panel { Bounds = new Rectangle(0, 64, CardWidth, 1), BackColor = BorderColor };

            // ---------- corps ----------
            var title = new Label
            {
                Text = "Connexion",
                ForeColor = TextColor,
                Font = new Font("Segoe UI Semibold", 16f, FontStyle.Bold),
                Location = new Point(32, 88),
                AutoSize = true,
                BackColor = Color.Transparent,
            };

            var subtitle = new Label
            {
                Text = "Réservé aux utilisateurs abonnés, ajoutés par l'admin ARS.",
                ForeColor = MetaColor,
                Font = new Font("Segoe UI", 9f),
                Location = new Point(32, 122),
                Size = new Size(CardWidth - 64, 20),
                BackColor = Color.Transparent,
            };

            var userLabel = MakeFieldLabel("Nom d'utilisateur", 168);
            _usernameBox = new TextBox();
            var userWrapper = WrapInput(_usernameBox, 190);
            var passLabel = MakeFieldLabel("Mot de passe", 246);
            _passwordBox = new TextBox { UseSystemPasswordChar = true };
            var passWrapper = WrapInput(_passwordBox, 268);
            _usernameBox.KeyDown += (_, e) =>
            {
                if (e.KeyCode == Keys.Enter)
                {
                    e.SuppressKeyPress = true;
                    _passwordBox.Focus();
                }
            };
            _passwordBox.KeyDown += async (_, e) =>
            {
                if (e.KeyCode == Keys.Enter)
                {
                    e.SuppressKeyPress = true;
                    await AttemptLoginAsync();
                }
            };

            _errorLabel = new Label
            {
                Text = "",
                ForeColor = ErrorColor,
                Font = new Font("Segoe UI", 8.75f),
                Location = new Point(32, 314),
                Size = new Size(CardWidth - 64, 34),
                BackColor = Color.Transparent,
            };

            _loginButton = new GoldButton
            {
                Text = "Se connecter",
                Location = new Point(32, 354),
                Size = new Size(CardWidth - 64, 44),
            };
            _loginButton.Click += async (_, _) => await AttemptLoginAsync();

            var footerDivider = new Panel { Bounds = new Rectangle(32, 414, CardWidth - 64, 1), BackColor = BorderColor };
            var footer = new Label
            {
                Text = "Accès agent · ARS Tunisie",
                ForeColor = MetaColor,
                Font = new Font("Segoe UI", 8f),
                Location = new Point(32, 428),
                AutoSize = true,
                BackColor = Color.Transparent,
            };

            Controls.Add(footer);
            Controls.Add(footerDivider);
            Controls.Add(_loginButton);
            Controls.Add(_errorLabel);
            Controls.Add(passWrapper);
            Controls.Add(passLabel);
            Controls.Add(userWrapper);
            Controls.Add(userLabel);
            Controls.Add(subtitle);
            Controls.Add(title);
            Controls.Add(divider);
            Controls.Add(header);

            AcceptButton = _loginButton;
        }

        private static Label MakeFieldLabel(string text, int y) => new()
        {
            Text = text,
            ForeColor = MetaColor,
            Font = new Font("Segoe UI", 8.5f),
            Location = new Point(32, y),
            AutoSize = true,
            BackColor = Color.Transparent,
        };

        private Panel WrapInput(TextBox tb, int y)
        {
            var wrapper = new Panel
            {
                Location = new Point(32, y),
                Size = new Size(CardWidth - 64, 40),
                BackColor = BorderColor,
                Padding = new Padding(1),
            };
            tb.Dock = DockStyle.Fill;
            tb.BorderStyle = BorderStyle.None;
            tb.BackColor = FieldBg;
            tb.ForeColor = TextColor;
            tb.Font = new Font("Segoe UI", 10.5f);
            tb.Margin = new Padding(10, 8, 10, 0);
            var inner = new Panel { Dock = DockStyle.Fill, BackColor = FieldBg, Padding = new Padding(12, 9, 12, 0) };
            inner.Controls.Add(tb);
            wrapper.Controls.Add(inner);

            tb.Enter += (_, _) => wrapper.BackColor = GoldAccent;
            tb.Leave += (_, _) => wrapper.BackColor = BorderColor;

            return wrapper;
        }

        private void ApplyRoundedRegion()
        {
            using var path = RoundedPath(new Rectangle(0, 0, Width, Height), CornerRadius);
            Region = new Region(path);
        }

        private static GraphicsPath RoundedPath(Rectangle rect, int radius)
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

        private async Task AttemptLoginAsync()
        {
            var username = _usernameBox.Text.Trim();
            var password = _passwordBox.Text;

            if (string.IsNullOrWhiteSpace(username) || string.IsNullOrWhiteSpace(password))
            {
                _errorLabel.Text = "Merci de renseigner les deux champs.";
                return;
            }

            _loginButton.IsLoading = true;
            _usernameBox.Enabled = false;
            _passwordBox.Enabled = false;
            _errorLabel.Text = "";

            try
            {
                var body = JsonSerializer.Serialize(new { username, password });
                var content = new StringContent(body, Encoding.UTF8, "application/json");
                var resp = await _http.PostAsync($"{_apiBase}/api/auth/login", content);

                if (resp.StatusCode == System.Net.HttpStatusCode.Unauthorized)
                {
                    _errorLabel.Text = "Identifiants invalides.";
                    return;
                }
                if (resp.StatusCode == System.Net.HttpStatusCode.Forbidden)
                {
                    _errorLabel.Text = "Compte désactivé. Contactez l'administrateur ARS.";
                    return;
                }
                if (!resp.IsSuccessStatusCode)
                {
                    _errorLabel.Text = "Erreur serveur. Réessayez.";
                    return;
                }

                var json = await resp.Content.ReadAsStringAsync();
                using var doc = JsonDocument.Parse(json);
                Token = doc.RootElement.GetProperty("access_token").GetString();

                DialogResult = DialogResult.OK;
                Close();
            }
            catch (Exception)
            {
                _errorLabel.Text = "Serveur injoignable. Vérifiez votre connexion.";
            }
            finally
            {
                _loginButton.IsLoading = false;
                _usernameBox.Enabled = true;
                _passwordBox.Enabled = true;
            }
        }

        /// <summary>Bouton avec dégradé doré, coins arrondis, effet de survol
        /// et un spinner animé pendant le chargement (IsLoading = true).</summary>
        private sealed class GoldButton : Button
        {
            private bool _hover;
            private bool _loading;
            private float _spinAngle;
            private readonly System.Windows.Forms.Timer _spinTimer;

            /// <summary>Active/désactive l'état "chargement" : masque le texte,
            /// affiche un anneau doré qui tourne, et bloque les clics.</summary>
            public bool IsLoading
            {
                get => _loading;
                set
                {
                    _loading = value;
                    if (value) _spinTimer.Start(); else _spinTimer.Stop();
                    Invalidate();
                }
            }

            public GoldButton()
            {
                FlatStyle = FlatStyle.Flat;
                FlatAppearance.BorderSize = 0;
                BackColor = Color.Transparent;
                ForeColor = Color.FromArgb(255, 24, 20, 12);
                Font = new Font("Segoe UI", 10.5f, FontStyle.Bold);
                Cursor = Cursors.Hand;
                DoubleBuffered = true;

                _spinTimer = new System.Windows.Forms.Timer { Interval = 16 };
                _spinTimer.Tick += (_, _) =>
                {
                    _spinAngle = (_spinAngle + 9f) % 360f;
                    Invalidate();
                };
            }

            protected override void OnMouseEnter(EventArgs e) { _hover = true; Invalidate(); base.OnMouseEnter(e); }
            protected override void OnMouseLeave(EventArgs e) { _hover = false; Invalidate(); base.OnMouseLeave(e); }

            // Empêche tout clic (double soumission) pendant le chargement,
            // sans désactiver le contrôle (ce qui casserait le dessin custom).
            protected override void OnClick(EventArgs e)
            {
                if (_loading) return;
                base.OnClick(e);
            }

            protected override void OnPaint(PaintEventArgs pevent)
            {
                var g = pevent.Graphics;
                g.SmoothingMode = SmoothingMode.AntiAlias;
                var rect = new Rectangle(0, 0, Width - 1, Height - 1);
                using var path = RoundedPath(rect, 10);

                bool dim = _loading;
                Color c1 = dim ? Color.FromArgb(255, 196, 164, 100) : (_hover ? Color.FromArgb(255, 224, 190, 110) : GoldAccent);
                Color c2 = dim ? Color.FromArgb(255, 150, 118, 60) : (_hover ? Color.FromArgb(255, 184, 145, 68) : GoldDim);
                using var brush = new LinearGradientBrush(rect, c1, c2, LinearGradientMode.Vertical);
                g.FillPath(brush, path);

                if (_loading)
                {
                    int size = 20;
                    var spinRect = new Rectangle(Width / 2 - size / 2, Height / 2 - size / 2, size, size);
                    using var pen = new Pen(Color.FromArgb(200, 24, 20, 12), 3f) { StartCap = LineCap.Round, EndCap = LineCap.Round };
                    g.DrawArc(pen, spinRect, _spinAngle, 260);
                }
                else
                {
                    TextRenderer.DrawText(g, Text, Font, rect, ForeColor,
                        TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter);
                }
            }
        }
    }
}