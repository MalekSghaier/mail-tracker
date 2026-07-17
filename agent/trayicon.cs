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

        public TrayIconApp()
        {
            _trayIcon = new NotifyIcon
            {
                Icon = IconHelper.GetTrayIcon(),
                Visible = false,
                Text = "Mail Detector Agent",
            };

            var menu = new ContextMenuStrip();
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
            if (savedToken != null)
            {
                _poller.SetAuthToken(savedToken);
                bool stillValid = Task.Run(() => _poller.VerifyTokenAsync()).GetAwaiter().GetResult();
                if (stillValid) return true;

                _poller.ClearAuthToken();
                TokenStorage.Clear();
            }

            using var loginForm = new LoginForm(_poller.ApiBase, _poller.HttpClient);
            if (loginForm.ShowDialog() == DialogResult.OK && loginForm.Token != null)
            {
                TokenStorage.Save(loginForm.Token);
                _poller.SetAuthToken(loginForm.Token);
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