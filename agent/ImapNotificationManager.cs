using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;

namespace MailDetectorAgent
{
    public static class ImapNotificationManager
    {
        private static readonly Dictionary<string, ImapAlertDto> _pending = new();
        private static readonly Dictionary<string, bool?> _reminderStatus = new();
        private static readonly HashSet<string> _minimizedSet = new();
        private static ImapNotificationForm? _singleForm;
        private static BadgeForm? _badgeForm;
        private static ImapNotificationCenterForm? _centerForm;
        private static Func<string, Task>? _ackCallback;
        private static Func<string, bool, Task>? _reminderCallback;
        private static string _apiBase = "http://localhost:8000";
        private static List<ImapAlertDto> VisibleAlerts() =>
           _pending.Values.Where(a => !_minimizedSet.Contains(a.Key)).ToList();

        public static void Configure(Func<string, Task> ackCallback, Func<string, bool, Task> reminderCallback, string apiBase)        {
            _ackCallback = ackCallback;
            _reminderCallback = reminderCallback;
            _apiBase = apiBase;
        }

        public static bool? GetReminderStatus(string key) =>
            _reminderStatus.TryGetValue(key, out var v) ? v : null;

        public static void SetReminderStatus(string key, bool done)
        {
            _reminderStatus[key] = done;
            if (_pending.TryGetValue(key, out var alert))
            {
                _ = _reminderCallback?.Invoke(alert.tracking_id, done);
            }
        }

        public static async Task AddAlertsAsync(IEnumerable<ImapAlertDto> alerts)
        {
            var alertList = alerts.ToList();
            var currentKeys = new HashSet<string>(alertList.Select(a => a.Key));
        
            var goneKeys = _pending.Keys.Where(k => !currentKeys.Contains(k)).ToList();
            bool anyGone = goneKeys.Count > 0;
            foreach (var key in goneKeys)
            {
                var goneAlert = _pending[key];
                bool wasAnsweredLocally = _reminderStatus.TryGetValue(key, out var status) && status.HasValue;
        
                _pending.Remove(key);
                _reminderStatus.Remove(key);
                _minimizedSet.Remove(key);
        
                if (wasAnsweredLocally)
                {
                    Console.WriteLine($"[ImapNotificationManager] {key} disparu avec réponse déjà donnée -> ack de secours");
                    _ = _ackCallback?.Invoke(goneAlert.tracking_id);
                }
        
                if (_singleForm != null && !_singleForm.IsDisposed && _singleForm.Key == key)
                    _singleForm.Close();
            }
        
            bool centerNeedsRefresh = false;
        
            foreach (var a in alertList)
            {
                bool isNew = !_pending.ContainsKey(a.Key);
        
                if (isNew)
                {
                    _pending[a.Key] = a;
                    _reminderStatus[a.Key] = a.reminder_done;
                    if (a.category == "seen_no_answer")
                        _minimizedSet.Add(a.Key);
                    Refresh();
                    if (a.category == "pending") await Task.Delay(600);
                }
                else
                {
                    var prev = _pending[a.Key];
                    bool categoryChanged = prev.category != a.category;
                    bool reminderChanged = !Equals(
                        _reminderStatus.GetValueOrDefault(a.Key),
                        a.reminder_done);
                    bool summaryChanged = prev.summary != a.summary;
        
                    if (categoryChanged || reminderChanged || summaryChanged)
                    {
                        _pending[a.Key] = a;
                        _reminderStatus[a.Key] = a.reminder_done;
        
                        if (a.category == "pending" && prev.category != "pending")
                        {
                            _minimizedSet.Remove(a.Key);
                        }
        
                        centerNeedsRefresh = true;
                        Refresh();
        
                        if (_singleForm != null && !_singleForm.IsDisposed && _singleForm.Key == a.Key)
                        {
                            if (a.reminder_done.HasValue)
                                _singleForm.ApplyExternalAnswer(a.reminder_done.Value);
                            if (summaryChanged)
                                _singleForm.ApplyExternalSummary(a.summary);
                        }
                    }
                }
            }
        
            if (anyGone) Refresh();
            if (centerNeedsRefresh) _centerForm?.RefreshList(_pending.Values.ToList());
        }

        public static void Dismiss(string key)
        {
            Console.WriteLine($"[ImapNotificationManager] Dismiss appelé pour {key}"); // <-- AJOUT
            if (_pending.TryGetValue(key, out var alert))
            {
                _pending.Remove(key);
                _ = _ackCallback?.Invoke(alert.tracking_id);
                Console.WriteLine($"[ImapNotificationManager] ackCallback invoqué pour {alert.tracking_id}"); // <-- AJOUT
            }
            else
            {
                Console.WriteLine($"[ImapNotificationManager] Dismiss : clé {key} introuvable dans _pending !"); // <-- AJOUT
            }
            _reminderStatus.Remove(key);
            _minimizedSet.Remove(key);
            Refresh();
        }

        public static void MinimizeSingle(string key)
        {
            _minimizedSet.Add(key);
            Refresh();
        }

        private static void Refresh()
        {
            int count = _pending.Count;

            if (count == 0)
            {
                CloseSingle();
                CloseBadge();
                CloseCenter();
                _minimizedSet.Clear();
                return;
            }

            if (count == 1)
            {
                var alert = _pending.Values.First();

                if (_minimizedSet.Contains(alert.Key))
                {
                    CloseSingle();
                    
                    ShowOrUpdateBadge(VisibleAlerts().Count);
                    _centerForm?.RefreshList(VisibleAlerts());  
                    return;
                }

                CloseBadge();
                CloseCenter();
                if (_singleForm == null || _singleForm.IsDisposed)
                {
                    _singleForm = new ImapNotificationForm(
                        alert,
                        () => Dismiss(alert.Key),
                        () => MinimizeSingle(alert.Key),
                        GetReminderStatus(alert.Key),
                        done => SetReminderStatus(alert.Key, done),
                        _apiBase);
                    _singleForm.Show();
                }
                return;
            }

            CloseSingle();
            ShowOrUpdateBadge(VisibleAlerts().Count);
            _centerForm?.RefreshList(VisibleAlerts());
        }

        private static void ShowOrUpdateBadge(int count)
        {
            if (count == 0)
            {
                CloseBadge();
                return;
            }
        
            if (_badgeForm == null || _badgeForm.IsDisposed)
            {
                _badgeForm = new BadgeForm(count, OnBadgeClicked);
                _badgeForm.Show();
            }
            else
            {
                _badgeForm.UpdateCount(count);
            }
}

        private static void OnBadgeClicked()
        {
            if (_centerForm == null || _centerForm.IsDisposed)
            {
                _centerForm = new ImapNotificationCenterForm(
                    VisibleAlerts(), 
                    Dismiss,
                    MinimizeSingle,
                    GetReminderStatus,
                    SetReminderStatus,
                    _apiBase);
                _centerForm.Show();
            }
            else
            {
                _centerForm.BringToFront();
            }
        }

        private static void CloseSingle()
        {
            if (_singleForm != null && !_singleForm.IsDisposed) _singleForm.Close();
            _singleForm = null;
        }

        private static void CloseBadge()
        {
            if (_badgeForm != null && !_badgeForm.IsDisposed) _badgeForm.Close();
            _badgeForm = null;
        }

        private static void CloseCenter()
        {
            if (_centerForm != null && !_centerForm.IsDisposed) _centerForm.Close();
            _centerForm = null;
        }
    }
}