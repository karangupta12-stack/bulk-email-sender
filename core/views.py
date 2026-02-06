from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.mail import EmailMultiAlternatives, get_connection
from django.conf import settings
from django.http import HttpResponse
from .models import Recipient, EmailCampaign, EmailLog
import pandas as pd
import threading
import time
import uuid
import csv

# --- BACKGROUND WORKER ---
def send_bulk_emails_task(subject, body, recipients, campaign_id):
    try:
        # Campaign fetch karo
        campaign = EmailCampaign.objects.get(id=campaign_id)
        
        # Settings
        BATCH_SIZE = 50   # 50 emails ka batch
        SLEEP_TIME = 2    # 2 second rest
        
        # --- 1. SETUP CONTENT ---
        # Unique ID generate (Short version for cleaner look)
        unique_id = str(uuid.uuid4()).split('-')[0]
        
        # Spacing Fix (Paragraph gap hatana)
        clean_body = body.replace("<p>", "<p style='margin:0; margin-bottom:8px; line-height:1.5;'>")
        clean_body = clean_body.replace("<p><br></p>", "<br>")
        
        # --- NEW: PROFESSIONAL FOOTER (Ref No at Bottom) ---
        footer_style = """
        <br><br>
        <div style="margin-top: 20px; padding-top: 10px; border-top: 1px solid #eaeaea; color: #999999; font-size: 11px; font-family: sans-serif;">
            <p style="margin:0;">Ref ID: {uid} | This is an automated email.</p>
        </div>
        """
        # Footer HTML create karo
        email_footer = footer_style.format(uid=unique_id)
        
        # Body + Footer jod do
        final_content = clean_body + email_footer
        # ------------------------

        total_sent = 0
        total_failed = 0
        
        # Batch processing logic
        chunks = [recipients[i:i + BATCH_SIZE] for i in range(0, len(recipients), BATCH_SIZE)]

        for chunk in chunks:
            connection = get_connection()
            connection.open()
            
            for recipient in chunk:
                status = 'Failed'
                error_msg = ''
                
                # IMPORTANT: Reset content for every user
                content = final_content

                try:
                    # --- 2. REPLACEMENTS ---
                    r_name = str(recipient.name).strip()
                    content = content.replace('{{name}}', r_name).replace('@Name', r_name).replace('@name', r_name)

                    r_college = str(recipient.college).strip()
                    content = content.replace('{{college}}', r_college).replace('@College', r_college).replace('@college', r_college)

                    r_year = str(recipient.year).strip()
                    content = content.replace('{{year}}', r_year).replace('@Year', r_year).replace('@year', r_year)

                    r_event = str(recipient.event_name).strip()
                    content = content.replace('{{event_name}}', r_event).replace('@Event', r_event).replace('@event', r_event)

                    # --- 3. SENDING ---
                    msg = EmailMultiAlternatives(
                        subject,
                        content, # Plain text fallback
                        settings.EMAIL_HOST_USER,
                        [recipient.email],
                        connection=connection
                    )
                    msg.attach_alternative(content, "text/html")
                    msg.send()
                    
                    status = 'Sent'
                    total_sent += 1
                
                except Exception as e:
                    error_msg = str(e)
                    total_failed += 1
                    print(f"Failed to send to {recipient.email}: {e}")

                # --- 4. LOGGING ---
                EmailLog.objects.create(
                    campaign=campaign,
                    recipient_name=recipient.name,
                    recipient_email=recipient.email,
                    status=status,
                    error_message=error_msg
                )

            connection.close()
            
            # Stats update
            campaign.success_count = total_sent
            campaign.failed_count = total_failed
            campaign.save()
            
            # Gmail Rate Limit Protection
            time.sleep(SLEEP_TIME)

    except Exception as e:
        print(f"CRITICAL WORKER ERROR: {e}")


# --- MAIN VIEWS ---

def dashboard(request):
    total_contacts = Recipient.objects.count()
    campaigns = EmailCampaign.objects.all().order_by('-sent_at')
    return render(request, 'dashboard.html', {'total_contacts': total_contacts, 'campaigns': campaigns})

# core/views.py

def compose_email(request):
    # GET Request: Page khulte hi saare recipients bhejo taaki user select kar sake
    all_recipients = Recipient.objects.all().order_by('-id')

    if request.method == "POST":
        subject = request.POST.get('subject')
        body = request.POST.get('body')
        
        # --- NEW CHANGE: Capture Selected IDs ---
        selected_ids = request.POST.getlist('selected_ids')
        
        if not selected_ids:
            messages.error(request, "Please select at least one recipient.")
            return render(request, 'compose.html', {'recipients': all_recipients})
            
        # Sirf wahi recipients nikalo jinki ID list mein hai
        target_recipients = list(Recipient.objects.filter(id__in=selected_ids))
        # ----------------------------------------

        # Campaign Create
        campaign = EmailCampaign.objects.create(
            subject=subject,
            body=body,
            total_recipients=len(target_recipients)
        )

        # Start Thread (Background Task)
        t = threading.Thread(
            target=send_bulk_emails_task,
            args=(subject, body, target_recipients, campaign.id)
        )
        t.setDaemon(True)
        t.start()

        messages.success(request, f"Campaign started for {len(target_recipients)} selected students! Check Dashboard.")
        return redirect('dashboard')

    return render(request, 'compose.html', {'recipients': all_recipients})

def upload_excel(request):
    if request.method == "POST" and request.FILES.get('excel_file'):
        excel_file = request.FILES['excel_file']
        try:
            df = pd.read_excel(excel_file)
            df.columns = [str(c).lower().strip().replace(" ", "_") for c in df.columns]
            objs = [
                Recipient(
                    name=row.get('name', ''),
                    college=row.get('college', ''),
                    year=row.get('year', ''),
                    email=row.get('email_id', ''),
                    mobile=row.get('mobile_number', ''),
                    event_name=row.get('event_name', '')
                ) for _, row in df.iterrows()
            ]
            Recipient.objects.bulk_create(objs)
            messages.success(request, f"Imported {len(objs)} contacts.")
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")
    return redirect('dashboard')

def export_report(request, campaign_id):
    campaign = get_object_or_404(EmailCampaign, id=campaign_id)
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="Report_{campaign.id}.csv"'
    writer = csv.writer(response)
    writer.writerow(['Recipient Name', 'Email', 'Status', 'Time', 'Error Details'])
    for log in campaign.logs.all():
        writer.writerow([log.recipient_name, log.recipient_email, log.status, log.timestamp, log.error_message])
    return response

# --- CONTACT MANAGEMENT VIEWS ---

def manage_contacts(request):
    contacts = Recipient.objects.all().order_by('-id')
    return render(request, 'manage_contacts.html', {'contacts': contacts})

def add_contact(request):
    if request.method == "POST":
        Recipient.objects.create(
            name=request.POST.get('name'),
            college=request.POST.get('college'),
            year=request.POST.get('year'),
            email=request.POST.get('email'),
            mobile=request.POST.get('mobile'),
            event_name=request.POST.get('event_name')
        )
        messages.success(request, "New contact added successfully!")
        return redirect('manage_contacts')
    return redirect('manage_contacts')

def edit_contact(request, id):
    contact = get_object_or_404(Recipient, id=id)
    if request.method == "POST":
        contact.name = request.POST.get('name')
        contact.college = request.POST.get('college')
        contact.year = request.POST.get('year')
        contact.email = request.POST.get('email')
        contact.mobile = request.POST.get('mobile')
        contact.event_name = request.POST.get('event_name')
        contact.save()
        messages.success(request, "Contact updated successfully!")
        return redirect('manage_contacts')
    return redirect('manage_contacts')

def delete_contact(request, id):
    contact = get_object_or_404(Recipient, id=id)
    contact.delete()
    messages.success(request, "Contact deleted.")
    return redirect('manage_contacts')

def delete_all_contacts(request):
    if request.method == "POST":
        count = Recipient.objects.count()
        Recipient.objects.all().delete()
        messages.warning(request, f"All {count} contacts deleted.")
    return redirect('manage_contacts')

def delete_campaign(request, campaign_id):
    campaign = get_object_or_404(EmailCampaign, id=campaign_id)
    campaign.delete()
    messages.success(request, "Campaign deleted successfully.")
    return redirect('dashboard')

# --- NEW: Get Failed Emails for Modal ---
def get_failed_emails(request, campaign_id):
    campaign = get_object_or_404(EmailCampaign, id=campaign_id)
    # Sirf failed logs nikalo
    failed_logs = campaign.logs.filter(status='Failed')
    
    return render(request, 'partials/failed_list.html', {'logs': failed_logs})