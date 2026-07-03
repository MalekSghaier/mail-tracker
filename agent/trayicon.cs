using System;
using System.Drawing;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace MailDetectorAgent
{
    /// <summary>
    /// Point d'entrée de l'agent. L'icône système et le polling ne
    /// démarrent QUE si l'utilisateur est authentifié comme abonné
    /// (créé au préalable par un admin ARS via /admin). Sans session
    /// valide : aucune icône, aucun popup, aucune bulle.
    /// </summary>
    public sealed class TrayIconApp : IDisposable
    {
        private readonly NotifyIcon _trayIcon;
        private readonly Poller _poller;

        public TrayIconApp()
        {
            _trayIcon = new NotifyIcon
            {
                Icon = new Icon(@"C:\Users\DELL\Desktop\mail-tracker\agent\Assets\favicon.ico"),
                Visible = false, // caché tant que l'authentification n'est pas confirmée
                Text = "Mail Detector Agent",
            };

            var menu = new ContextMenuStrip();
            menu.Items.Add("Quitter", null, (_, _) => Application.Exit());
            _trayIcon.ContextMenuStrip = menu;

            _poller = new Poller(_trayIcon);
            _poller.SessionExpired += OnSessionExpired;

            if (!EnsureAuthenticated())
            {
                // Pas de session valide et login annulé par l'utilisateur :
                // on ferme l'agent sans jamais afficher l'icône ni démarrer
                // le polling.
                _trayIcon.Dispose();
                Application.Exit();
                return;
            }

            _trayIcon.Visible = true;
            _poller.Start();
        }

        /// <summary>
        /// Vrai si un token valide est déjà stocké sur ce PC (aucune fenêtre
        /// affichée), ou si l'utilisateur vient de se connecter avec succès
        /// via LoginForm. Faux s'il annule le login ou saisit de mauvais
        /// identifiants et ferme la fenêtre.
        /// </summary>
        private bool EnsureAuthenticated()
        {
            var savedToken = TokenStorage.Load();
            if (savedToken != null)
            {
                _poller.SetAuthToken(savedToken);

                // Task.Run isole cet appel du thread UI courant : la tâche s'exécute
                // sur un thread du pool, sans contexte de synchronisation WinForms
                // à capturer. Combiné à ConfigureAwait(false) dans VerifyTokenAsync,
                // ça élimine le risque de deadlock au démarrage (avant Application.Run).
                bool stillValid = Task.Run(() => _poller.VerifyTokenAsync()).GetAwaiter().GetResult();
                if (stillValid) return true;

                // Token présent mais rejeté par le backend (expiré, ou
                // compte désactivé entre-temps par l'admin) : on l'efface.
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

        /// <summary>
        /// Appelé par le Poller quand le backend renvoie 401/403 en cours
        /// de route. On masque tout de suite l'icône (donc plus aucun
        /// nouveau popup/bulle ne peut se déclencher), puis on retente une
        /// authentification.
        /// </summary>
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