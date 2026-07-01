using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;

namespace MailDetectorAgent
{
    /// <summary>
    /// Point central qui décide quoi afficher :
    /// - 1 alerte en attente  -> un seul NotificationForm (popup classique)
    /// - 2+ alertes en attente -> BadgeForm (bulle avec le nombre) qui ouvre
    ///   NotificationCenterForm (panneau listant toutes les alertes)
    /// L'ack (POST /api/alerts/{id}/ack) n'est envoyé que quand l'utilisateur
    /// ferme réellement la notification (clic sur la croix ou sur le corps).
    /// </summary>
    public static class NotificationManager
    {
        private static readonly Dictionary<string, AlertDto> _pending = new();
        private static readonly Dictionary<string, bool?> _reminderStatus = new(); // cache local, source = backend
        private static readonly HashSet<string> _minimizedSet = new(); // alertes "X" : en attente, popup masqué
        private static NotificationForm? _singleForm;
        private static BadgeForm? _badgeForm;
        private static NotificationCenterForm? _centerForm;
        private static Func<string, Task>? _ackCallback;
        private static Func<string, bool, Task>? _reminderCallback;

        public static void Configure(Func<string, Task> ackCallback, Func<string, bool, Task> reminderCallback)
        {
            _ackCallback = ackCallback;
            _reminderCallback = reminderCallback;
        }

        public static bool? GetReminderStatus(string trackingId) =>
            _reminderStatus.TryGetValue(trackingId, out var v) ? v : null;

        public static void SetReminderStatus(string trackingId, bool done)
        {
            _reminderStatus[trackingId] = done;
            _ = _reminderCallback?.Invoke(trackingId, done); // persisté en base côté backend
            // La suppression effective (ack + retrait de l'UI) est désormais
            // déclenchée par le composant UI lui-même (popup ou carte), après
            // un court message de confirmation, via le même Dismiss() que
            // pour la croix — pour les deux réponses Oui et Non.
        }

        public static async Task AddAlertsAsync(IEnumerable<AlertDto> alerts)
        {
            bool centerNeedsRefresh = false;

            foreach (var a in alerts)
            {
                bool isSilent = a.category == "seen_no_answer" || a.category == "not_validated";
                bool isNew = !_pending.ContainsKey(a.tracking_id);

                if (isSilent)
                {
                    // Alertes silencieuses : ajoutées dans le panneau et le
                    // compteur de la bulle, mais sans jamais déclencher de popup.
                    if (isNew)
                    {
                        _pending[a.tracking_id] = a;
                        _reminderStatus[a.tracking_id] = a.reminder_done;
                        _minimizedSet.Add(a.tracking_id); // force le mode "bulle" dès le départ
                        centerNeedsRefresh = true;
                        Refresh(); // met à jour le compteur de la bulle
                    }
                    else
                    {
                        bool changed = !Equals(
                            _reminderStatus.GetValueOrDefault(a.tracking_id),
                            a.reminder_done);
                        if (changed)
                        {
                            _reminderStatus[a.tracking_id] = a.reminder_done;
                            centerNeedsRefresh = true;
                        }
                    }
                }
                else // "pending" : flux normal avec popup
                {
                    if (isNew)
                    {
                        _pending[a.tracking_id] = a;
                        _reminderStatus[a.tracking_id] = a.reminder_done;
                        Refresh();
                        await Task.Delay(600);
                    }
                    else
                    {
                        bool changed = !Equals(
                            _reminderStatus.GetValueOrDefault(a.tracking_id),
                            a.reminder_done);
                        if (changed)
                        {
                            _reminderStatus[a.tracking_id] = a.reminder_done;
                            centerNeedsRefresh = true;
                        }
                    }
                }
            }

            if (centerNeedsRefresh)
                _centerForm?.RefreshList(_pending.Values.ToList());
        }

        public static void Dismiss(string trackingId)
        {
            if (_pending.Remove(trackingId))
            {
                _ = _ackCallback?.Invoke(trackingId);
            }
            _reminderStatus.Remove(trackingId);
            _minimizedSet.Remove(trackingId);
            Refresh();
        }

        /// <summary>
        /// Appelé quand l'utilisateur clique sur la croix (ou le corps) du
        /// popup unique : le mail reste en attente (pas d'ack, pas de
        /// changement en base), seul l'affichage bascule sur la bulle.
        /// </summary>
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
                    // L'utilisateur a fermé (X) l'unique popup -> on affiche
                    // seulement la bulle, le mail reste en attente.
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
                        () => Dismiss(alert.tracking_id),            // utilisé après confirmation Oui/Non
                        () => MinimizeSingle(alert.tracking_id),     // utilisé par la croix / le corps
                        GetReminderStatus(alert.tracking_id),
                        done => SetReminderStatus(alert.tracking_id, done));
                    _singleForm.Show();
                }
                return;
            }

            // count > 1 : on bascule sur la bulle + le panneau, plus de popup individuel
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
            // Toujours ouvrir le panneau complet, même pour une seule alerte
            // minimisée (décision explicite : pas de réouverture directe du
            // popup individuel depuis la bulle).
            if (_centerForm == null || _centerForm.IsDisposed)
            {
                _centerForm = new NotificationCenterForm(
                    _pending.Values.ToList(),
                    Dismiss,
                    GetReminderStatus,
                    SetReminderStatus);
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