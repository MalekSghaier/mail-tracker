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
        private static NotificationForm? _singleForm;
        private static BadgeForm? _badgeForm;
        private static NotificationCenterForm? _centerForm;
        private static Func<string, Task>? _ackCallback;

        public static void Configure(Func<string, Task> ackCallback)
        {
            _ackCallback = ackCallback;
        }

        public static void AddAlerts(IEnumerable<AlertDto> alerts)
        {
            bool added = false;
            foreach (var a in alerts)
            {
                if (!_pending.ContainsKey(a.tracking_id))
                {
                    _pending[a.tracking_id] = a;
                    added = true;
                }
            }
            if (added) Refresh();
        }

        public static void Dismiss(string trackingId)
        {
            if (_pending.Remove(trackingId))
            {
                _ = _ackCallback?.Invoke(trackingId);
            }
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
                return;
            }

            if (count == 1)
            {
                CloseBadge();
                CloseCenter();
                if (_singleForm == null || _singleForm.IsDisposed)
                {
                    var alert = _pending.Values.First();
                    _singleForm = new NotificationForm(alert, () => Dismiss(alert.tracking_id));
                    _singleForm.Show();
                }
                return;
            }

            // count > 1 : on bascule sur la bulle + le panneau, plus de popup individuel
            CloseSingle();

            if (_badgeForm == null || _badgeForm.IsDisposed)
            {
                _badgeForm = new BadgeForm(count, OnBadgeClicked);
                _badgeForm.Show();
            }
            else
            {
                _badgeForm.UpdateCount(count);
            }

            _centerForm?.RefreshList(_pending.Values.ToList());
        }

        private static void OnBadgeClicked()
        {
            if (_centerForm == null || _centerForm.IsDisposed)
            {
                _centerForm = new NotificationCenterForm(_pending.Values.ToList(), Dismiss);
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