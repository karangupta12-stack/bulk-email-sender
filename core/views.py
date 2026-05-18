import re
from urllib import request
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.mail import EmailMultiAlternatives, get_connection
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from .models import Recipient, EmailCampaign, EmailLog
import pandas as pd
import threading
import time
import uuid
import csv
from django.core.files.storage import default_storage
from PIL import Image, ImageDraw, ImageFont, ImageColor
import io, base64
from django.db.models import Sum
import traceback
from django.core.mail.backends.smtp import EmailBackend
from .models import MailSettings
import concurrent.futures
import zipfile
from django.db import connection as db_conn


# --- CERTIFICATE GENERATION ---
def generate_certificate(template_bytes, student_name, x, y, font_size, color_hex, output_format='PDF'):
    try:
        img = Image.open(io.BytesIO(template_bytes))
        draw = ImageDraw.Draw(img)

        # Font Logic
        try:
            # Linux server ke liye path adjust karna pad sakta hai
            font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", size=int(font_size))
        except IOError:
            font = ImageFont.load_default()

        # Text Centering Logic
        text_bbox = draw.textbbox((0, 0), student_name, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        
        final_x = int(x) - (text_width / 2)
        final_y = int(y) - (text_height / 2)

        rgb_color = ImageColor.getrgb(color_hex)
        draw.text((final_x, final_y), student_name, fill=rgb_color, font=font)

        output_stream = io.BytesIO()
        
        # --- CHANGE IS HERE: Support PNG for Preview ---
        if output_format == 'PNG':
            img.save(output_stream, format='PNG')
        else:
            img.convert('RGB').save(output_stream, format='PDF')
            
        output_stream.seek(0)
        return output_stream.read()
    except Exception as e:
        print(f"Cert Error: {e}")
        return None



def process_email_batch(batch, subject, final_content, attachments, cert_data, mail_settings, campaign):
    from django.db import connection as db_conn
    
    custom_backend = EmailBackend(
        host=mail_settings.email_host,
        port=mail_settings.email_port,
        username=mail_settings.email_user,
        password=mail_settings.email_password,
        use_tls=mail_settings.use_tls,
        fail_silently=False
    )
    custom_backend.open()
    
    success_count = 0
    failed_count = 0
    logs_to_save = []

    for recipient in batch:
        content = final_content
        status = 'Failed'
        error_msg = ''
        
        try:
            r_name = str(recipient.name).strip() if recipient.name else ''
            content = content.replace('{{name}}', r_name).replace('@Name', r_name).replace('@name', r_name)

            r_college = str(recipient.college).strip() if recipient.college else ''
            content = content.replace('{{college}}', r_college).replace('@College', r_college).replace('@college', r_college)

            r_year = str(recipient.year).strip() if recipient.year else ''
            content = content.replace('{{year}}', r_year).replace('@Year', r_year).replace('@year', r_year)

            r_event = str(recipient.event_name).strip() if recipient.event_name else ''
            content = content.replace('{{event_name}}', r_event).replace('@Event', r_event).replace('@event', r_event)
            
            r_mobile = str(recipient.mobile).strip() if recipient.mobile else ''
            content = content.replace('{{mobile}}', r_mobile).replace('@Mobile', r_mobile).replace('@mobile', r_mobile)

            plain_text = re.sub(r'<[^>]+>', '', content)
            msg = EmailMultiAlternatives(
                subject, plain_text, mail_settings.email_user,
                [recipient.email], connection=custom_backend
            )
            msg.attach_alternative(content, "text/html")

            for att in attachments:
                msg.attach(att['name'], att['content'], att['content_type'])

            if cert_data:
                cert_pdf_bytes = generate_certificate(
                    cert_data['template_bytes'], r_name, cert_data['x'],
                    cert_data['y'], cert_data['font_size'], cert_data['color']
                )
                if cert_pdf_bytes:
                    filename = f"Certificate_{r_name.replace(' ', '_')}.pdf"
                    msg.attach(filename, cert_pdf_bytes, 'application/pdf')

            msg.send()
            status = 'Sent'
            success_count += 1
        
        except Exception as e:
            error_msg = str(e)
            failed_count += 1
            print(f"Failed: {recipient.email} - {e}")

        logs_to_save.append(EmailLog(
            campaign=campaign, 
            recipient_name=recipient.name, 
            recipient_email=recipient.email, 
            status=status, 
            error_message=error_msg
        ))

    custom_backend.close()
    
    # ✅ Batch complete hone pe turant DB save karo
    EmailLog.objects.bulk_create(logs_to_save)
    
    # ✅ Thread ka DB connection free karo
    try:
        db_conn.close()
    except:
        pass
    
    return success_count, failed_count

# ---------------------------------------------------------
# MAIN TASK: Ye function Multi-Threading chalu karega
# ---------------------------------------------------------
def send_bulk_emails_task(subject, body, recipients, campaign_id, attachments=[], cert_data=None):
    try:
        campaign = EmailCampaign.objects.get(id=campaign_id)
        BATCH_SIZE = 10  # Ek chunk mein 20 emails
        
        mail_settings = MailSettings.objects.first()
        if not mail_settings or not mail_settings.email_user:
            print("ERROR: Settings page par email configure nahi hai!")
            return

        unique_id = str(uuid.uuid4()).split('-')[0]
        clean_body = body.replace("<p>", "<div style='margin:0; padding:0; line-height:1.2;'>").replace("</p>", "</div>")
        clean_body = clean_body.replace("<p><br></p>", "<br>")
        email_footer = f"<br><br><div style='border-top:1px solid #ddd; color:#999; font-size:11px;'>Ref ID: {unique_id}</div>"
        final_content = clean_body + email_footer

        total_sent = 0
        total_failed = 0
        all_logs = []
        
        # Recipients ko batches mein todo
        chunks = [recipients[i:i + BATCH_SIZE] for i in range(0, len(recipients), BATCH_SIZE)]

        # 🔥 MAGIC HAPPENS HERE: Multi-Threading (4 workers ek sath kaam karenge)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = []
            for chunk in chunks:
                # 4 workers ko alag-alag batches de do
                futures.append(executor.submit(
                    process_email_batch, chunk, subject, final_content, attachments, cert_data, mail_settings, campaign
                ))
            
            # Jaise-jaise batches complete honge, result collect karo
            for future in concurrent.futures.as_completed(futures):
                # s_count, f_count, logs = future.result()
                s_count, f_count = future.result()
                total_sent += s_count
                total_failed += f_count
                # all_logs.extend(logs) # Saare logs ek badi list mein jod lo

        # 🔥 DATABASE MAGIC: 1000 logs ko bhi sirf 1 second mein save kar dega!
        EmailLog.objects.bulk_create(all_logs)  

        # Update Campaign final stats
        campaign.success_count = total_sent
        campaign.failed_count = total_failed
        campaign.save()

    except Exception as e:
        import traceback
        print(f"CRITICAL ERROR: {e}")
        traceback.print_exc()

# --- MAIN VIEWS ---
def dashboard(request):
    total_contacts = Recipient.objects.count()
    campaigns = EmailCampaign.objects.all().order_by('-sent_at')
    
    # Ye 2 lines missing thi dashboard mein
    total_sent = campaigns.aggregate(Sum('success_count'))['success_count__sum'] or 0
    total_failed = campaigns.aggregate(Sum('failed_count'))['failed_count__sum'] or 0

    return render(request, 'dashboard.html', {
        'total_contacts': total_contacts, 
        'campaigns': campaigns,
        'total_sent': total_sent,
        'total_failed': total_failed
    })

def compose_email(request):
    all_recipients = Recipient.objects.all().order_by('-id')

    if request.method == "POST":
        subject = request.POST.get('subject')
        body = request.POST.get('body')
        selected_ids = request.POST.getlist('selected_ids')
        
        # ---------------------------------------------------------
        # 🔥 SMART AUTO-ZIP ATTACHMENT LOGIC (Speed up upload)
        # ---------------------------------------------------------
        raw_attachments = request.FILES.getlist('attachments')
        attachment_data = []
        
        # Agar 1 se zyada files hain, toh unki ZIP file bana do
        if len(raw_attachments) > 1:
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                for f in raw_attachments:
                    zip_file.writestr(f.name, f.read())
            
            attachment_data.append({
                'name': 'All_Attachments.zip',
                'content': zip_buffer.getvalue(),
                'content_type': 'application/zip'
            })
        else:
            # Agar sirf 1 file hai toh normally attach karo (bina zip ke)
            for f in raw_attachments:
                attachment_data.append({'name': f.name, 'content': f.read(), 'content_type': f.content_type})
        # ---------------------------------------------------------
        
        cert_data = None
        cert_file = request.FILES.get('cert_template')
        if cert_file:
            cert_data = {
                'template_bytes': cert_file.read(),
                'x': request.POST.get('cert_x', 960),
                'y': request.POST.get('cert_y', 540),
                'font_size': request.POST.get('cert_font_size', 60),
                'color': request.POST.get('cert_color', '#000000')
            }

        if not selected_ids:
            messages.error(request, "Please select at least one recipient.")
            return render(request, 'compose.html', {'recipients': all_recipients})
            
        target_recipients = list(Recipient.objects.filter(id__in=selected_ids))
        
        campaign = EmailCampaign.objects.create(
            subject=subject,
            body=body,
            total_recipients=len(target_recipients)
        )

        t = threading.Thread(
            target=send_bulk_emails_task,
            args=(subject, body, target_recipients, campaign.id, attachment_data, cert_data)
        )
        t.setDaemon(True)
        t.start()

        msg = f"Campaign started for {len(target_recipients)} recipients"
        if cert_data:
            msg += " with certificates"
        if attachment_data:
            msg += f" and attachments"
        msg += "!"
        
        messages.success(request, msg)
        return redirect('dashboard')

    return render(request, 'compose.html', {'recipients': all_recipients})


def upload_excel(request):
    if request.method == "POST" and request.FILES.get('excel_file'):
        excel_file = request.FILES['excel_file']

        try:
            df = pd.read_excel(excel_file)

            # 1️⃣ Normalize column names
            df.columns = df.columns.str.strip().str.lower()

            # 2️⃣ Column mapping (Excel → Model)
            COLUMN_MAP = {
                'name': 'name',

                'email': 'email',
                'e-mail id': 'email',
                'email id': 'email',

                'college': 'college',
                'course': 'college',

                'year': 'year',

                'mobile': 'mobile',
                'mobile no': 'mobile',
                'mobile number': 'mobile',

                'event': 'event_name',
                'event name': 'event_name'
            }

            df = df.rename(columns=COLUMN_MAP)

            # 3️⃣ Safe value function (NO nan)
            def safe(val):
                if pd.isna(val):
                    return ''
                return str(val).strip()

            objs = []
            for _, row in df.iterrows():
                objs.append(
                    Recipient(
                        name=safe(row.get('name')),
                        email=safe(row.get('email')),
                        college=safe(row.get('college')),
                        year=safe(row.get('year')),
                        mobile=safe(row.get('mobile')),
                        event_name=safe(row.get('event_name')),
                    )
                )

            Recipient.objects.bulk_create(objs)

            messages.success(request, f"Imported {len(objs)} contacts successfully.")

        except Exception as e:
            messages.error(request, f"Excel import error: {str(e)}")

    return redirect('manage_contacts')


def export_report(request, campaign_id):
    campaign = get_object_or_404(EmailCampaign, id=campaign_id)
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="Report_{campaign.id}.csv"'
    writer = csv.writer(response)
    writer.writerow(['Recipient Name', 'Email', 'Status', 'Time', 'Error Details'])
    for log in campaign.logs.all():
        writer.writerow([
            log.recipient_name, 
            log.recipient_email, 
            log.status, 
            log.timestamp, 
            log.error_message
        ])
    return response


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


def get_failed_emails(request, campaign_id):
    campaign = get_object_or_404(EmailCampaign, id=campaign_id)
    failed_logs = campaign.logs.filter(status='Failed')
    return render(request, 'partials/failed_list.html', {'logs': failed_logs})


# core/views.py (Bottom mein add karein)

def preview_certificate(request):
    if request.method == "POST" and request.FILES.get('cert_template'):
        try:
            image_file = request.FILES['cert_template']
            x = float(request.POST.get('x', 960))
            y = float(request.POST.get('y', 540))
            font_size = int(request.POST.get('font_size', 60))
            color = request.POST.get('color', '#000000')
            
            img = Image.open(image_file)
            draw = ImageDraw.Draw(img)
            
            # Font Loading
            try:
                font = ImageFont.truetype("arial.ttf", size=font_size)
            except Exception:
                font = ImageFont.load_default()
                
            dummy_text = "Amit Kumar Sharma"
            
            # Position Calculation (Supports both Old and New Pillow versions)
            try:
                text_bbox = draw.textbbox((0, 0), dummy_text, font=font)
                text_width = text_bbox[2] - text_bbox[0]
                text_height = text_bbox[3] - text_bbox[1]
            except AttributeError:
                # Fallback for older versions
                text_width, text_height = draw.textsize(dummy_text, font=font)
                
            final_x = x - (text_width / 2)
            final_y = y - (text_height / 2)
            
            draw.text((final_x, final_y), dummy_text, fill=color, font=font)
            
            buffered = io.BytesIO()
            img.save(buffered, format="PNG")
            img_str = base64.b64encode(buffered.getvalue()).decode('utf-8')
            
            return JsonResponse({'status': 'success', 'image': img_str})
            
        except Exception as e:
            print(traceback.format_exc()) # Terminal mein exact error dikhega
            return JsonResponse({'status': 'error', 'message': f"Processing Error: {str(e)}"})
            
    return JsonResponse({'status': 'error', 'message': 'No image uploaded'})


def sent_mails(request):
    campaigns = EmailCampaign.objects.all().order_by('-sent_at')
    
    total_campaigns = campaigns.count()
    total_sent = campaigns.aggregate(Sum('success_count'))['success_count__sum'] or 0
    total_failed = campaigns.aggregate(Sum('failed_count'))['failed_count__sum'] or 0
    total_recipients = campaigns.aggregate(Sum('total_recipients'))['total_recipients__sum'] or 0

    return render(request, 'sent_mails.html', {
        'campaigns': campaigns,
        'total_campaigns': total_campaigns,
        'total_sent': total_sent,
        'total_failed': total_failed,
        'total_recipients': total_recipients
    })

def analytics(request):
    campaigns = EmailCampaign.objects.all().order_by('-sent_at')
    
    total_campaigns = campaigns.count()
    total_sent = campaigns.aggregate(Sum('success_count'))['success_count__sum'] or 0
    total_failed = campaigns.aggregate(Sum('failed_count'))['failed_count__sum'] or 0
    
    total_emails = total_sent + total_failed
    success_rate = round((total_sent / total_emails * 100) if total_emails > 0 else 0)

    # Chart Data (Last 5 Campaigns)
    recent_camps = campaigns[:5][::-1] # Reverse to show oldest to newest on chart
    chart_labels = [c.sent_at.strftime("%b %d") for c in recent_camps]
    chart_sent = [c.success_count for c in recent_camps]
    chart_failed = [c.failed_count for c in recent_camps]

    return render(request, 'analytics.html', {
        'campaigns': campaigns,
        'total_campaigns': total_campaigns,
        'total_sent': total_sent,
        'total_failed': total_failed,
        'success_rate': success_rate,
        'chart_labels': chart_labels,
        'chart_sent': chart_sent,
        'chart_failed': chart_failed
    })

def settings_page(request):
    # Dummy logic: You can connect this to a Settings Model later
    context = {
        'current_host': settings.EMAIL_HOST,
        'current_port': settings.EMAIL_PORT,
        'current_user': settings.EMAIL_HOST_USER,
    }
    return render(request, 'settings_page.html', context)

def save_settings(request):
    # Settings save logic yahan aayega (e.g. Save to DB or .env)
    messages.success(request, "Settings updated successfully!")
    return redirect('settings_page')

from django.http import JsonResponse
def test_email_connection(request):
    try:
        connection = get_connection()
        connection.open()
        connection.close()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})
    
def settings_page(request):
    # Database se pehli setting uthao (Agar nahi hai toh blank object banega)
    mail_settings = MailSettings.objects.first()
    
    context = {
        'settings': mail_settings,
        'current_host': mail_settings.email_host if mail_settings else 'Not Set',
        'current_port': mail_settings.email_port if mail_settings else 'Not Set',
        'current_user': mail_settings.email_user if mail_settings else 'Not Set',
    }
    return render(request, 'settings_page.html', context)

def save_settings(request):
    if request.method == "POST":
        # Hamesha ek hi record rakhenge (id=1)
        settings_obj, created = MailSettings.objects.get_or_create(id=1)
        
        settings_obj.email_host = request.POST.get('email_host', 'smtp.gmail.com')
        settings_obj.email_port = request.POST.get('email_port', 587)
        settings_obj.email_user = request.POST.get('email_user', '')
        settings_obj.email_password = request.POST.get('email_password', '')
        settings_obj.use_tls = request.POST.get('use_tls') == 'True'
        
        settings_obj.save()
        messages.success(request, "Email Configuration Saved Successfully!")
        
    return redirect('settings_page')

def test_email_connection(request):
    try:
        mail_settings = MailSettings.objects.first()
        if not mail_settings or not mail_settings.email_user:
            return JsonResponse({'success': False, 'error': 'Please save settings first!'})

        # Custom Backend Connection banayenge UI wali details se
        backend = EmailBackend(
            host=mail_settings.email_host,
            port=mail_settings.email_port,
            username=mail_settings.email_user,
            password=mail_settings.email_password,
            use_tls=mail_settings.use_tls,
            fail_silently=False,
            timeout=10
        )
        # Check connection
        backend.open()
        backend.close()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})