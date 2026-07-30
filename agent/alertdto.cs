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

    public class ImapAlertDto
    {
        public int id { get; set; }
        public string account_label { get; set; } = "";
        public string account_email { get; set; } = "";
        public string employee_username { get; set; } = "";
        public string department { get; set; } = "";
        public string sender { get; set; } = "";
        public string subject { get; set; } = "";
        public string received_at { get; set; } = "";
        public bool? reminder_done { get; set; } = null;
        public string category { get; set; } = "pending";
        public string Key => id.ToString();
    }
}