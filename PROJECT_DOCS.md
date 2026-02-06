📘 Project: Dynamic Bulk Email Sender System
Status: Production Ready (v1.0) Last Updated: Feb 2026

1. Project Overview
    A web-based application to send personalized bulk emails using SMTP (Gmail). It supports Excel uploads, dynamic placeholders (e.g., @Name), background processing, live status tracking, and failure logging.



2. Tech Stack
    Backend: Django 5.x (Python)
    Database: PostgreSQL
    Frontend: HTML5, Bootstrap 5, JavaScript (Vanilla)
    Rich Text Editor: QuillJS
    Data Processing: Pandas (for Excel)
    Concurrency: Python threading (for background email sending)



3. Folder Structure

email_sender/
│
├── .env                  # Secrets (DB Creds, Email App Password) - DO NOT COMMIT
├── manage.py
├── email_sender/         # Main Config
│   ├── settings.py       # Timezone: Asia/Kolkata, Email Backend Config
│   └── urls.py
│
├── core/                 # Main Application
│   ├── models.py         # DB Schema
│   ├── views.py          # Logic (Batching, Sending, HTML Cleanup)
│   ├── urls.py           # Routes
│   ├── templates/
│   │   ├── base.html             # Sidebar & Layout
│   │   ├── dashboard.html        # Stats, Recent Campaigns, Modals
│   │   ├── compose.html          # Editor with @Tags & Recipient Selector
│   │   ├── manage_contacts.html  # CRUD Operations
│   │   └── partials/
│   │       └── failed_list.html  # HTML Fragment for Failure Popup



4. Database Schema (core/models.py)
    Recipient: Stores individual student data.
    Fields: name, college, year, email, mobile, event_name.
    EmailCampaign: Tracks a specific email blast.
    Fields: subject, body, total_recipients, success_count, failed_count, sent_at.
    EmailLog: Stores status of each email sent.
    Fields: campaign (FK), recipient_email, status (Sent/Failed), error_message.



5. Key Features & Logic Implementation

A. Smart Batch Sending (Anti-Blocking)
    Logic: Emails are sent in batches of 50.
    Delay: System sleeps for 2 seconds after every batch to avoid Gmail blocking.
    Connection: get_connection() is opened/closed per batch to prevent timeouts.

B. "Zero-Gap" & "Anti-Clipping" Formatting
    To prevent Gmail from hiding text ("Show Quoted Text") and removing ugly gaps:
    Spacing Fix: All <p> tags are converted to <div style='margin:0'>.
    Footer Ref ID: A unique Reference ID (UUID) is added to the footer of every email. This makes every email unique, preventing Gmail from collapsing them.


C. Frontend "WhatsApp Style" Tags
    UI: User sees a blue chip @Name in the editor.
    Backend: Python logic converts both @Name and {{name}} to the actual recipient's name.


D. Selective Sending
    Compose Page: Features a sidebar with checkboxes.
    Logic: User can select/deselect specific students. Backend filters recipients using id__in=selected_ids.


E. Auto-Save Drafts
    Mechanism: Uses Browser localStorage to save Subject and Body on every keystroke. Draft is cleared only after successful submission.


6. How to Run Locally

Activate Virtual Env: source venv/bin/activate (Mac/Linux) or venv\Scripts\activate (Windows)
Install Requirements: pip install django psycopg2-binary pandas openpyxl

Setup .env:
DB_NAME=email_db
DB_USER=postgres
DB_PASSWORD=your_password
EMAIL_USER=your_email@gmail.com
EMAIL_PASSWORD=your_app_password
Run Server: python manage.py runserver