from django.db import models

class Recipient(models.Model):
    name = models.CharField(max_length=255)
    college = models.CharField(max_length=255)
    year = models.CharField(max_length=50)
    email = models.EmailField()
    mobile = models.CharField(max_length=20)
    event_name = models.CharField(max_length=255)
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