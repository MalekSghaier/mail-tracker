using System;
using System.Collections.Generic;
using System.Linq;

namespace MailDetectorAgent
{
    /// <summary>
    /// Équivalent de NotificationManager pour le scénario B. Gère
    /// l'affichage (popup unique / badge+centre) des mails reçus non lus,
    /// avec la même logique de purge que le scénario A : un mail qui
    /// disparaît de /api/imap-alerts (lu, ou compte désactivé) disparaît
    /// aussi de l'affichage au prochain poll.
    /// </summary>
    public static class ImapNotificationManager
    {
        private static readonly Dictionary<string, ImapAlertDto> _pending = new();
        private static ImapNotificationForm? _singleForm;
        private static BadgeForm? _badgeForm;
        private static ImapNotificationCenterForm? _centerForm;

        public static void AddAlerts(IEnumerable<ImapAlertDto> alerts)
        {
            var alertList = alerts.ToList();
            var currentKeys = new HashSet<string>(alertList.Select(a => a.Key));

            var goneKeys = _pending.Keys.Where(k => !currentKeys.Contains(k)).ToList();
            bool anyGone = goneKeys.Count > 0;
            foreach (var key in goneKeys)
            {
                _pending.Remove(key);
                if (_singleForm != null && !_singleForm.IsDisposed && _singleForm.Key == key)
                    _singleForm.Close();
            }

            bool anyNew = false;
            foreach (var a in alertList)
            {
                if (!_pending.ContainsKey(a.Key))
                {
                    _pending[a.Key] = a;
                    anyNew = true;
                }
            }

            if (anyGone || anyNew) Refresh();
        }

        public static void Dismiss(string key)
        {
            _pending.Remove(key);
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
                var alert = _pending.Values.First();
                if (_singleForm == null || _singleForm.IsDisposed)
                {
                    _singleForm = new ImapNotificationForm(alert, () => Dismiss(alert.Key));
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
                _centerForm = new ImapNotificationCenterForm(_pending.Values.ToList(), Dismiss);
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