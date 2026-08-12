using System;
using System.Collections.Generic;
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
        private readonly NotifyIcon _trayIcon;
        private System.Windows.Forms.Timer? _timer;

        public event Action? SessionExpired;

        public string ApiBase => _apiBase;
        public HttpClient HttpClient => _http;
        public Poller(NotifyIcon trayIcon)
        {
            _trayIcon = trayIcon;
            _apiBase = Environment.GetEnvironmentVariable("MAIL_DETECTOR_API") ?? "http://localhost:8000";

            NotificationManager.Configure(
                async (trackingId) =>
                {
                    try { await _http.PostAsync($"{_apiBase}/api/alerts/{trackingId}/ack", null); }
                    catch (Exception ex) { Log.Error(ex, "[Poller] erreur ack"); }
                },
                async (trackingId, done) =>
                {
                    try
                    {
                        var json = JsonSerializer.Serialize(new { done });
                        var content = new StringContent(json, System.Text.Encoding.UTF8, "application/json");
                        await _http.PostAsync($"{_apiBase}/api/alerts/{trackingId}/reminder", content);
                    }
                    catch (Exception ex) { Log.Error(ex, "[Poller] erreur reminder"); }
                },
                _apiBase);

            ImapNotificationManager.Configure(
                async (mailId) =>
                {
                    try { await _http.PostAsync($"{_apiBase}/api/imap-alerts/{mailId}/ack", null); }
                    catch (Exception ex) { Log.Error(ex, "[Poller] erreur imap ack"); }
                },
                async (mailId, done) =>
                {
                    try
                    {
                        var json = JsonSerializer.Serialize(new { done });
                        var content = new StringContent(json, System.Text.Encoding.UTF8, "application/json");
                        await _http.PostAsync($"{_apiBase}/api/imap-alerts/{mailId}/reminder", content);
                    }
                    catch (Exception ex) { Log.Error(ex, "[Poller] erreur imap reminder"); }
                },
                _apiBase);
        }

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
                return false;
            }
        }

        private string? _accountRole;

        public void SetAccountRole(string? role)
        {
            _accountRole = role;
        }

        public void Start()
        {
            _timer = new System.Windows.Forms.Timer { Interval = 3_000 };
            _timer.Tick += async (_, _) =>
            {
                // --- Scénario A désactivé (mails envoyés non ouverts) ---
                // await CheckAlertsAsync();

                // --- Scénario B actif (mails reçus non ouverts) ---
                await CheckImapAlertsAsync();
            };
            _timer.Start();
        }

        public void Stop() => _timer?.Stop();

        private bool _busy = false;

        /*
        --- SCÉNARIO A DÉSACTIVÉ — code conservé pour réactivation future ---

        private async Task CheckAlertsAsync()
        {
            if (_busy) return;
            _busy = true;
            try
            {
                var resp = await _http.GetAsync($"{_apiBase}/api/alerts");

                if (resp.StatusCode == System.Net.HttpStatusCode.Unauthorized
                    || resp.StatusCode == System.Net.HttpStatusCode.Forbidden)
                {
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
        */

        private bool _imapBusy = false;

        private async Task CheckImapAlertsAsync()
        {
            if (_accountRole != "dept_admin" && _accountRole != "superadmin") return;
            if (_imapBusy) return;
            _imapBusy = true;

            try
            {
                var resp = await _http.GetAsync($"{_apiBase}/api/imap-alerts");

                if (resp.StatusCode == System.Net.HttpStatusCode.Unauthorized
                    || resp.StatusCode == System.Net.HttpStatusCode.Forbidden)
                {
                    Stop();
                    ClearAuthToken();
                    TokenStorage.Clear();
                    SessionExpired?.Invoke();
                    return;
                }

                if (!resp.IsSuccessStatusCode) return;

                var json = await resp.Content.ReadAsStringAsync();
                var imapAlerts = JsonSerializer.Deserialize<ImapAlertDto[]>(
                    json,
                    new JsonSerializerOptions { PropertyNameCaseInsensitive = true });

                if (imapAlerts == null) return;
                await ImapNotificationManager.AddAlertsAsync(imapAlerts);
            }
            catch (Exception ex)
            {
                Log.Error(ex, "[Poller] erreur pendant CheckImapAlertsAsync");
            }
            finally
            {
                _imapBusy = false;
            }
        }

    }
}