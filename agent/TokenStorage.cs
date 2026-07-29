using System;
using System.IO;
using System.Security.Cryptography;
using System.Text;

namespace MailDetectorAgent
{
    /// <summary>
    /// Stocke le token JWT et le rôle du compte localement, chiffrés avec
    /// DPAPI (lié au compte Windows de l'utilisateur courant). Permet de
    /// ne demander le login qu'une seule fois par utilisateur/PC —
    /// personne d'autre que ce compte Windows ne peut déchiffrer les fichiers.
    /// </summary>
    public static class TokenStorage
    {
        private static readonly string FolderPath = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
            "MailDetectorAgent");

        private static readonly string FilePath = Path.Combine(FolderPath, "session.dat");
        private static readonly string RoleFilePath = Path.Combine(FolderPath, "role.dat");

        public static void Save(string token)
        {
            Directory.CreateDirectory(FolderPath);
            var plainBytes = Encoding.UTF8.GetBytes(token);
            var protectedBytes = ProtectedData.Protect(plainBytes, null, DataProtectionScope.CurrentUser);
            File.WriteAllBytes(FilePath, protectedBytes);
        }

        public static string? Load()
        {
            if (!File.Exists(FilePath)) return null;
            try
            {
                var protectedBytes = File.ReadAllBytes(FilePath);
                var plainBytes = ProtectedData.Unprotect(protectedBytes, null, DataProtectionScope.CurrentUser);
                return Encoding.UTF8.GetString(plainBytes);
            }
            catch
            {
                Clear();
                return null;
            }
        }

        public static void SaveRole(string? role)
        {
            if (string.IsNullOrEmpty(role))
            {
                try { if (File.Exists(RoleFilePath)) File.Delete(RoleFilePath); } catch { /* ignore */ }
                return;
            }

            Directory.CreateDirectory(FolderPath);
            var plainBytes = Encoding.UTF8.GetBytes(role);
            var protectedBytes = ProtectedData.Protect(plainBytes, null, DataProtectionScope.CurrentUser);
            File.WriteAllBytes(RoleFilePath, protectedBytes);
        }

        public static string? LoadRole()
        {
            if (!File.Exists(RoleFilePath)) return null;
            try
            {
                var protectedBytes = File.ReadAllBytes(RoleFilePath);
                var plainBytes = ProtectedData.Unprotect(protectedBytes, null, DataProtectionScope.CurrentUser);
                return Encoding.UTF8.GetString(plainBytes);
            }
            catch
            {
                try { if (File.Exists(RoleFilePath)) File.Delete(RoleFilePath); } catch { /* ignore */ }
                return null;
            }
        }

        public static void Clear()
        {
            try { if (File.Exists(FilePath)) File.Delete(FilePath); } catch { /* ignore */ }
            try { if (File.Exists(RoleFilePath)) File.Delete(RoleFilePath); } catch { /* ignore */ }
        }
    }
}