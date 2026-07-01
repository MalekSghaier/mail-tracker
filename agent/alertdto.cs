namespace MailDetectorAgent
{
    public class AlertDto
    {
        public string tracking_id { get; set; } = "";
        public string sender { get; set; } = "";
        public string recipient { get; set; } = "";
        public string cc { get; set; } = "";
        public string subject { get; set; } = "";
        public string summary { get; set; } = "";
        public string sent_at { get; set; } = "";
        public bool? reminder_done { get; set; } = null;
        /// <summary>
        /// "pending"        = en attente (déclenche popup)
        /// "seen_no_answer" = vu sans réponse au rappel (silencieux)
        /// "not_validated"  = rappel non effectué (silencieux)
        /// </summary>
        public string category { get; set; } = "pending";
    }
}