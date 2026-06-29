using System;
using System.Net.Http;
using System.Text.Json;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace MailDetectorAgent
{
    public sealed class Poller
    {
        private readonly NotifyIcon _trayIcon;
        private readonly HttpClient _http = new();
        private readonly string _apiBase;
        private System.Windows.Forms.Timer? _timer;

        public Poller(NotifyIcon trayIcon)
        {
            _trayIcon = trayIcon;
            // À adapter : l'IP/port de ton backend FastAPI (sur ton PC, donc localhost ici)
            _apiBase = Environment.GetEnvironmentVariable("MAIL_DETECTOR_API") ?? "http://localhost:8000";
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

                foreach (var alert in alerts)
                {
                    Notifier.Show(_trayIcon, alert);
                    await _http.PostAsync($"{_apiBase}/api/alerts/{alert.tracking_id}/ack", null);
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine($"[Poller] erreur : {ex.Message}");
            }
        }
    }
}