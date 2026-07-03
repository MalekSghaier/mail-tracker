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
        public string category { get; set; } = "pending";
    }
}