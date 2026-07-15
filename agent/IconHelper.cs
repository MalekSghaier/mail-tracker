using System;
using System.Drawing;
using System.IO;

namespace MailDetectorAgent
{
    /// <summary>
    /// Centralise le chargement de l'icône de l'application. Le chemin est
    /// relatif au dossier de l'exécutable (portable, peu importe le poste
    /// ou l'utilisateur Windows), avec repli silencieux si le fichier est
    /// absent ou illisible.
    /// </summary>
    internal static class IconHelper
    {
        private static readonly string IconPath =
            Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "Assets", "favicon.ico");

        public static Icon GetTrayIcon()
        {
            try
            {
                if (File.Exists(IconPath))
                {
                    return new Icon(IconPath);
                }
            }
            catch (Exception)
            {
                // Ignore : l'appelant doit gérer le cas null (repli emoji, etc.)
            }
            return SystemIcons.Application;
        }

        public static Image? GetLogoImage()
        {
            try
            {
                if (File.Exists(IconPath))
                {
                    return Image.FromFile(IconPath);
                }
            }
            catch (Exception)
            {
                // Ignore : l'appelant doit gérer le cas null (repli emoji, etc.)
            }
            return null;
        }
    }
}