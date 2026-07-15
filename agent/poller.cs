using System;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text.Json;
using System.Threading.Tasks;
using System.Windows.Forms;
using Serilog;


namespace MailDetectorAgent
{
    public sealed class Poller
    {
        private readonly HttpClient _http = new();
        private readonly string _apiBase;
        private System.Windows.Forms.Timer? _timer;

        public event Action? SessionExpired;

        public string ApiBase => _apiBase;
        public HttpClient HttpClient => _http;

        public Poller(NotifyIcon trayIcon)
        {
            _apiBase = Environment.GetEnvironmentVariable("MAIL_DETECTOR_API") ?? "http://localhost:8000";

            NotificationManager.Configure(
                async (trackingId) =>
                {
                    try
                    {
                        await _http.PostAsync($"{_apiBase}/api/alerts/{trackingId}/ack", null);
                    }
                    catch (Exception ex)
                    {
                            Log.Error(ex, "[Poller] erreur ack");
                    }
                },
                async (trackingId, done) =>
                {
                    try
                    {
                        var json = JsonSerializer.Serialize(new { done });
                        var content = new StringContent(json, System.Text.Encoding.UTF8, "application/json");
                        await _http.PostAsync($"{_apiBase}/api/alerts/{trackingId}/reminder", content);
                    }
                    catch (Exception ex)
                    {
                        Log.Error(ex, "[Poller] erreur reminder");
                    }
                },
                _apiBase);
        }

        /// <summary>Attache le token JWT à toutes les futures requêtes.</summary>
        public void SetAuthToken(string token)
        {
            _http.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", token);
        }

        public void ClearAuthToken()
        {
            _http.DefaultRequestHeaders.Authorization = null;
        }
        public async Task<bool> VerifyTokenAsync()
        {
            if (_http.DefaultRequestHeaders.Authorization == null) return false;
            try
            {
                var resp = await _http.GetAsync($"{_apiBase}/api/auth/verify").ConfigureAwait(false);
                return resp.IsSuccessStatusCode;
            }
            catch
            {
                // Backend injoignable : on ne peut pas confirmer, on considère invalide
                // par prudence pour ne jamais afficher de popup sans certitude.
                return false;
            }
        }

        public void Start()
        {
            _timer = new System.Windows.Forms.Timer { Interval = 3_000 }; // 3 sec
            _timer.Tick += async (_, _) => await CheckAlertsAsync();
            _timer.Start();
        }

        public void Stop() => _timer?.Stop();

        private bool _busy = false;

        private async Task CheckAlertsAsync()
        {
            if (_busy) return; // évite le chevauchement si un cycle précédent est encore en cours
            _busy = true;
            try
            {
                var resp = await _http.GetAsync($"{_apiBase}/api/alerts");

                if (resp.StatusCode == System.Net.HttpStatusCode.Unauthorized
                    || resp.StatusCode == System.Net.HttpStatusCode.Forbidden)
                {
                    // Session invalide (expirée ou compte désactivé) : on arrête
                    // tout de suite le polling pour ne rien afficher, et on
                    // prévient l'appelant pour qu'il relance le login.
                    Stop();
                    ClearAuthToken();
                    TokenStorage.Clear();
                    SessionExpired?.Invoke();
                    return;
                }

                if (!resp.IsSuccessStatusCode) return;

                var json = await resp.Content.ReadAsStringAsync();
                var alerts = JsonSerializer.Deserialize<AlertDto[]>(
                    json,
                    new JsonSerializerOptions { PropertyNameCaseInsensitive = true });

                if (alerts == null) return;

                // Traite les alertes une par une (avec un court délai entre
                // chacune) pour que la transition popup -> badge=2 -> badge=3
                // soit visible, même si toutes arrivent dans le même poll.
                await NotificationManager.AddAlertsAsync(alerts);
            }
            catch (Exception ex)
            {
                Log.Error(ex, "[Poller] erreur pendant CheckAlertsAsync");
            }
            finally
            {
                _busy = false;
            }
        }
    }
}