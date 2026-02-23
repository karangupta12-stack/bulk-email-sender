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


# --- BACKGROUND WORKER ---
def send_bulk_emails_task(subject, body, recipients, campaign_id, attachments=[], cert_data=None):
    try:
        campaign = EmailCampaign.objects.get(id=campaign_id)
        BATCH_SIZE = 50
        SLEEP_TIME = 2
        
        unique_id = str(uuid.uuid4()).split('-')[0]
        clean_body = body.replace("<p>", "<div style='margin:0; padding:0; line-height:1.2;'>").replace("</p>", "</div>")
        clean_body = clean_body.replace("<p><br></p>", "<br>")
        
        email_footer = f"<br><br><div style='border-top:1px solid #ddd; color:#999; font-size:11px;'>Ref ID: {unique_id}</div>"
        final_content = clean_body + email_footer

        total_sent = 0
        total_failed = 0
        
        chunks = [recipients[i:i + BATCH_SIZE] for i in range(0, len(recipients), BATCH_SIZE)]

        for chunk in chunks:
            connection = get_connection()
            connection.open()
            
            for recipient in chunk:
                content = final_content
                status = 'Failed'
                error_msg = ''
                
                try:
                    # ✅ SABHI VARIABLES KO REPLACE KARO
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

                    msg = EmailMultiAlternatives(
                        subject, content, settings.EMAIL_HOST_USER, [recipient.email], connection=connection
                    )
                    msg.attach_alternative(content, "text/html")

                    for att in attachments:
                        msg.attach(att['name'], att['content'], att['content_type'])

                    if cert_data:
                        cert_pdf_bytes = generate_certificate(
                            cert_data['template_bytes'],
                            r_name,
                            cert_data['x'],
                            cert_data['y'],
                            cert_data['font_size'],
                            cert_data['color']
                        )
                        if cert_pdf_bytes:
                            filename = f"Certificate_{r_name.replace(' ', '_')}.pdf"
                            msg.attach(filename, cert_pdf_bytes, 'application/pdf')

                    msg.send()
                    status = 'Sent'
                    total_sent += 1
                
                except Exception as e:
                    error_msg = str(e)
                    total_failed += 1
                    print(f"Failed: {recipient.email} - {e}")

                EmailLog.objects.create(
                    campaign=campaign, 
                    recipient_name=recipient.name, 
                    recipient_email=recipient.email, 
                    status=status, 
                    error_message=error_msg
                )

            connection.close()
            campaign.success_count = total_sent
            campaign.failed_count = total_failed
            campaign.save()
            time.sleep(SLEEP_TIME)

    except Exception as e:
        print(f"CRITICAL ERROR: {e}")


# --- MAIN VIEWS ---
def dashboard(request):
    total_contacts = Recipient.objects.count()
    campaigns = EmailCampaign.objects.all().order_by('-sent_at')
    return render(request, 'dashboard.html', {
        'total_contacts': total_contacts, 
        'campaigns': campaigns
    })


def compose_email(request):
    all_recipients = Recipient.objects.all().order_by('-id')

    if request.method == "POST":
        subject = request.POST.get('subject')
        body = request.POST.get('body')
        selected_ids = request.POST.getlist('selected_ids')
        
        attachments = request.FILES.getlist('attachments')
        attachment_data = []
        for f in attachments:
            attachment_data.append({
                'name': f.name, 
                'content': f.read(), 
                'content_type': f.content_type
            })
        
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
            msg += f" and {len(attachment_data)} attachment(s)"
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
    if request.method == "POST":
        try:
            # 1. Get Data from AJAX
            image_file = request.FILES.get('template_file')
            x = request.POST.get('x')
            y = request.POST.get('y')
            font_size = request.POST.get('font_size')
            color = request.POST.get('color')
            dummy_name = "Amit Kumar Sharma" # Preview ke liye sample naam

            if not image_file:
                return JsonResponse({'error': 'No image uploaded'}, status=400)

            # 2. Generate Image (PNG format)
            img_bytes = generate_certificate(
                image_file.read(), 
                dummy_name, 
                x, y, font_size, color, 
                output_format='PNG' # Important
            )

            # 3. Convert to Base64 to send back to HTML
            img_b64 = base64.b64encode(img_bytes).decode('utf-8')
            
            return JsonResponse({'image': img_b64})
        
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
            
    return JsonResponse({'error': 'Invalid Request'}, status=400)