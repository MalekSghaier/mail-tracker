using System;
using System.Drawing;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace MailDetectorAgent
{
    public sealed class TrayIconApp : IDisposable
    {
        private readonly NotifyIcon _trayIcon;
        private readonly Poller _poller;
        private ToolStripMenuItem? _refreshMenuItem;


        public TrayIconApp()
        {
            _trayIcon = new NotifyIcon
            {
                Icon = IconHelper.GetTrayIcon(),
                Visible = false,
                Text = "Mail Detector Agent",
            };

            var menu = new ContextMenuStrip();
            _refreshMenuItem = new ToolStripMenuItem("Actualiser maintenant", null, async (_, _) => await RefreshNowAsync());
            menu.Items.Add(_refreshMenuItem);
            menu.Items.Add(new ToolStripSeparator());
            menu.Items.Add("À propos", null, (_, _) => ShowAbout());
            menu.Items.Add(new ToolStripSeparator());
            menu.Items.Add("Se déconnecter", null, async (_, _) => await LogoutAsync());
            menu.Items.Add(new ToolStripSeparator());
            menu.Items.Add("Quitter", null, (_, _) => Application.Exit());
            _trayIcon.ContextMenuStrip = menu;

            _poller = new Poller(_trayIcon);
            _poller.SessionExpired += OnSessionExpired;

            if (!EnsureAuthenticated())
            {
                _trayIcon.Dispose();
                Application.Exit();
                return;
            }

            _trayIcon.Visible = true;
            _poller.Start();
        }

                private async Task RefreshNowAsync()
        {
            if (_refreshMenuItem == null) return;

            _refreshMenuItem.Enabled = false;
            try
            {
                await _poller.CheckNowAsync();
            }
            catch (Exception)
            {
                // Les erreurs réseau sont déjà loguées côté Poller — pas besoin
                // de bloquer l'utilisateur avec une popup pour un simple échec
                // de rafraîchissement manuel.
            }
            finally
            {
                _refreshMenuItem.Enabled = true;
            }
        }

        private void ShowAbout()
        {
            using var about = new AboutForm();
            about.ShowDialog();
        }

        private async Task LogoutAsync()
        {
            _poller.Stop();
            _trayIcon.Visible = false;

            var token = TokenStorage.Load();
            if (token != null)
            {
                try
                {
                    var request = new HttpRequestMessage(HttpMethod.Post, $"{_poller.ApiBase}/api/auth/logout");
                    request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);
                    await _poller.HttpClient.SendAsync(request);
                }
                catch (Exception)
                {

                }
            }

            TokenStorage.Clear();
            _poller.ClearAuthToken();

            if (EnsureAuthenticated())
            {
                _trayIcon.Visible = true;
                _poller.Start();
            }
            else
            {
                Dispose();
                Application.Exit();
            }
        }

        private bool EnsureAuthenticated()
        {
            var savedToken = TokenStorage.Load();
            var savedRole = TokenStorage.LoadRole();
            if (savedToken != null && savedRole != null)
            {
                _poller.SetAuthToken(savedToken);
                bool stillValid = Task.Run(() => _poller.VerifyTokenAsync()).GetAwaiter().GetResult();
                if (stillValid)
                {
                    _poller.SetAccountRole(savedRole);
                    return true;
                }
        
                _poller.ClearAuthToken();
                TokenStorage.Clear();
            }

            using var loginForm = new LoginForm(_poller.ApiBase, _poller.HttpClient);
            if (loginForm.ShowDialog() == DialogResult.OK && loginForm.Token != null)
            {
                TokenStorage.Save(loginForm.Token);
                TokenStorage.SaveRole(loginForm.AccountRole);
                _poller.SetAuthToken(loginForm.Token);
                _poller.SetAccountRole(loginForm.AccountRole);
                return true;
            }

            return false;
        }

        private void OnSessionExpired()
        {
            _trayIcon.Visible = false;

            if (EnsureAuthenticated())
            {
                _trayIcon.Visible = true;
                _poller.Start();
            }
            else
            {
                Dispose();
                Application.Exit();
            }
        }

        public void Dispose()
        {
            _poller.Stop();
            _trayIcon.Visible = false;
            _trayIcon.Dispose();
        }
    }
}