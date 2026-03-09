from django.db import models

class Recipient(models.Model):
    name = models.CharField(max_length=255, blank=True)
    college = models.CharField(max_length=255, blank=True)
    year = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    mobile = models.CharField(max_length=20, blank=True)
    event_name = models.CharField(max_length=255, blank=True)

    # 🔥 NEW: extra excel columns store honge yahan
    extra_data = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.email

class EmailCampaign(models.Model):
    subject = models.CharField(max_length=255)
    body = models.TextField()
    sent_at = models.DateTimeField(auto_now_add=True)
    total_recipients = models.IntegerField(default=0)
    success_count = models.IntegerField(default=0)
    failed_count = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.subject} ({self.sent_at})"

class EmailLog(models.Model):
    campaign = models.ForeignKey(EmailCampaign, on_delete=models.CASCADE, related_name='logs')
    recipient_name = models.CharField(max_length=255)
    recipient_email = models.EmailField()
    status = models.CharField(max_length=20, choices=[('Sent', 'Sent'), ('Failed', 'Failed')])
    error_message = models.TextField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    
class MailSettings(models.Model):
    email_host = models.CharField(max_length=255, default='smtp.gmail.com')
    email_port = models.IntegerField(default=587)
    email_user = models.EmailField()
    email_password = models.CharField(max_length=255)
    use_tls = models.BooleanField(default=True)
    
    def __str__(self):
        return self.email_user