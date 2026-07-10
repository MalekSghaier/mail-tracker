using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;

namespace MailDetectorAgent
{
    public static class NotificationManager
    {
        private static readonly Dictionary<string, AlertDto> _pending = new();
        private static readonly Dictionary<string, bool?> _reminderStatus = new();
        private static readonly HashSet<string> _minimizedSet = new();
        private static NotificationForm? _singleForm;
        private static BadgeForm? _badgeForm;
        private static NotificationCenterForm? _centerForm;
        private static Func<string, Task>? _ackCallback;
        private static Func<string, bool, Task>? _reminderCallback;
        private static string _apiBase = "http://localhost:8000"; // valeur par défaut, peut être remplacée par Poller

        public static void Configure(Func<string, Task> ackCallback, Func<string, bool, Task> reminderCallback,string apiBase)
        {
            _ackCallback = ackCallback;
            _reminderCallback = reminderCallback;
            _apiBase = apiBase;
        }

        public static bool? GetReminderStatus(string trackingId) =>
            _reminderStatus.TryGetValue(trackingId, out var v) ? v : null;

        public static void SetReminderStatus(string trackingId, bool done)
        {
            _reminderStatus[trackingId] = done;
            _ = _reminderCallback?.Invoke(trackingId, done);
        }

        public static async Task AddAlertsAsync(IEnumerable<AlertDto> alerts)
        {
            var alertList = alerts.ToList();
            var currentIds = new HashSet<string>(alertList.Select(a => a.tracking_id));
            bool centerNeedsRefresh = false;

            // Purge : retire de la barre tout ce que le backend ne renvoie plus
            // (répondu "Oui" ou "Non" depuis la page web → disparu de /api/alerts).
            var goneIds = _pending.Keys.Where(id => !currentIds.Contains(id)).ToList();
            bool anyGone = goneIds.Count > 0;
            foreach (var id in goneIds)
            {
                _pending.Remove(id);
                _reminderStatus.Remove(id);
                _minimizedSet.Remove(id);
                if (_singleForm != null && !_singleForm.IsDisposed && _singleForm.TrackingId == id)
                    _singleForm.Close();
            }

            // Tous les items sont désormais "pending" (catégorie unique).
            foreach (var a in alertList)
            {
                bool isNew = !_pending.ContainsKey(a.tracking_id);

                if (isNew)
                {
                    _pending[a.tracking_id] = a;
                    _reminderStatus[a.tracking_id] = a.reminder_done;
                    if (a.category == "seen_no_answer" || a.category == "not_validated")
                        _minimizedSet.Add(a.tracking_id); // silencieux dès l'arrivée
                    Refresh();
                    if (a.category == "pending") await Task.Delay(600);
                }
                else
                {
                    var prevCategory = _pending[a.tracking_id].category;
                    bool categoryChanged = prevCategory != a.category;
                    bool reminderChanged = !Equals(
                        _reminderStatus.GetValueOrDefault(a.tracking_id),
                        a.reminder_done);

                    if (categoryChanged || reminderChanged)
                    {
                        _pending[a.tracking_id] = a;
                        _reminderStatus[a.tracking_id] = a.reminder_done;

                        // Cas recheck : l'alerte revient en "pending" avec
                        // reminder_done=NULL après avoir été "not_validated".
                        // On la retire de _minimizedSet pour qu'un nouveau popup
                        // s'affiche (pas juste la bulle silencieuse).
                        if (a.category == "pending" && prevCategory != "pending")
                        {
                            _minimizedSet.Remove(a.tracking_id);
                        }

                        centerNeedsRefresh = true;
                        Refresh();

                        if (_singleForm != null && !_singleForm.IsDisposed
                            && _singleForm.TrackingId == a.tracking_id
                            && a.reminder_done.HasValue)
                        {
                            _singleForm.ApplyExternalAnswer(a.reminder_done.Value);
                        }
                    }
                }
            }

            if (anyGone) Refresh();
            if (centerNeedsRefresh) _centerForm?.RefreshList(_pending.Values.ToList());
        }

        public static void Dismiss(string trackingId)
        {
            if (_pending.Remove(trackingId))
                _ = _ackCallback?.Invoke(trackingId);
            _reminderStatus.Remove(trackingId);
            _minimizedSet.Remove(trackingId);
            Refresh();
        }

        public static void MinimizeSingle(string trackingId)
        {
            _minimizedSet.Add(trackingId);
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

                if (_minimizedSet.Contains(alert.tracking_id))
                {
                    CloseSingle();
                    ShowOrUpdateBadge(count);
                    _centerForm?.RefreshList(_pending.Values.ToList());
                    return;
                }

                CloseBadge();
                CloseCenter();
                if (_singleForm == null || _singleForm.IsDisposed)
                {
                    _singleForm = new NotificationForm(
                        alert,
                        () => Dismiss(alert.tracking_id),
                        () => MinimizeSingle(alert.tracking_id),
                        GetReminderStatus(alert.tracking_id),
                        done => SetReminderStatus(alert.tracking_id, done),
                        _apiBase);
                    _singleForm.Show();
                }
                return;
            }

            CloseSingle();
            ShowOrUpdateBadge(count);
            _centerForm?.RefreshList(_pending.Values.ToList());
        }

        private static void ShowOrUpdateBadge(int count)
        {
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
                _centerForm = new NotificationCenterForm(
                    _pending.Values.ToList(),
                    Dismiss,
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