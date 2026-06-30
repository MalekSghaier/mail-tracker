using System;
using System.Net.Http;
using System.Text.Json;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace MailDetectorAgent
{
    public sealed class Poller
    {
        private readonly HttpClient _http = new();
        private readonly string _apiBase;
        private System.Windows.Forms.Timer? _timer;

        public Poller(NotifyIcon trayIcon)
        {
            // À adapter : l'IP/port de ton backend FastAPI (sur ton PC, donc localhost ici)
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
                        Console.WriteLine($"[Poller] erreur ack : {ex.Message}");
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
                        Console.WriteLine($"[Poller] erreur reminder : {ex.Message}");
                    }
                });
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
                var json = await _http.GetStringAsync($"{_apiBase}/api/alerts");
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
                Console.WriteLine($"[Poller] erreur : {ex.Message}");
            }
            finally
            {
                _busy = false;
            }
        }
    }
}