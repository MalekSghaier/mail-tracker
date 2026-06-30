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

            NotificationManager.Configure(async (trackingId) =>
            {
                try
                {
                    await _http.PostAsync($"{_apiBase}/api/alerts/{trackingId}/ack", null);
                }
                catch (Exception ex)
                {
                    Console.WriteLine($"[Poller] erreur ack : {ex.Message}");
                }
            });
        }

        public void Start()
        {
            _timer = new System.Windows.Forms.Timer { Interval = 15_000 }; // 15 sec
            _timer.Tick += async (_, _) => await CheckAlertsAsync();
            _timer.Start();
        }

        public void Stop() => _timer?.Stop();

        private async Task CheckAlertsAsync()
        {
            try
            {
                var json = await _http.GetStringAsync($"{_apiBase}/api/alerts");
                var alerts = JsonSerializer.Deserialize<AlertDto[]>(
                    json,
                    new JsonSerializerOptions { PropertyNameCaseInsensitive = true });

                if (alerts == null) return;

                // L'ack n'est plus fait ici automatiquement : NotificationManager
                // ne l'envoie que lorsque l'utilisateur ferme réellement la notification.
                NotificationManager.AddAlerts(alerts);
            }
            catch (Exception ex)
            {
                Console.WriteLine($"[Poller] erreur : {ex.Message}");
            }
        }
    }
}