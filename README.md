# Dynamic Bulk Email Sender

A Django-based bulk email management system for sending personalized email campaigns to imported contact lists. It supports Excel uploads, recipient selection, SMTP configuration, HTML email composition, attachments, certificate generation, campaign analytics, and delivery logs.

## Features

- Import contacts from Excel files using common columns such as `name`, `email`, `college`, `year`, `mobile`, and `event`
- Compose rich HTML emails with dynamic placeholders like `@Name`, `@College`, `@Year`, `@Mobile`, and `{{name}}`
- Select specific recipients before starting a campaign
- Send emails in background threads so the dashboard stays responsive
- Attach single files or automatically zip multiple attachments
- Generate personalized certificate PDFs from an uploaded certificate template
- Track each campaign with total, sent, and failed email counts
- View failed email details and export campaign reports as CSV
- Manage contacts with add, edit, delete, and bulk delete actions
- Configure and test SMTP settings from the app UI
- View campaign analytics and recent sending performance

## Tech Stack

- **Backend:** Django
- **Database:** PostgreSQL
- **Frontend:** HTML, Bootstrap, JavaScript
- **Email:** SMTP, Gmail-compatible configuration
- **Data Import:** Pandas, OpenPyXL
- **Image/Certificate Processing:** Pillow
- **Deployment:** Gunicorn, WhiteNoise-ready dependencies

## Project Structure

```text
email_sender/
+-- core/
|   +-- migrations/
|   +-- templates/
|   |   +-- analytics.html
|   |   +-- base.html
|   |   +-- compose.html
|   |   +-- dashboard.html
|   |   +-- manage_contacts.html
|   |   +-- sent_mails.html
|   |   +-- settings_page.html
|   +-- admin.py
|   +-- models.py
|   +-- urls.py
|   +-- views.py
+-- email_sender/
|   +-- settings.py
|   +-- urls.py
|   +-- asgi.py
|   +-- wsgi.py
+-- manage.py
+-- requirements.txt
+-- PROJECT_DOCS.md
+-- README.md
```

## Getting Started

### 1. Clone the Repository

```bash
git clone <your-repository-url>
cd email_sender
```

### 2. Create a Virtual Environment

```bash
python -m venv venv
```

Activate it:

```bash
# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a `.env` file in the project root:

```env
SECRET_KEY=your-django-secret-key
DEBUG=True

DB_NAME=email_db
DB_USER=postgres
DB_PASSWORD=your_postgres_password
DB_HOST=localhost

EMAIL_USER=your_email@gmail.com
EMAIL_PASSWORD=your_gmail_app_password
```

For Gmail, use an app password instead of your normal account password.

### 5. Prepare the Database

Create a PostgreSQL database matching `DB_NAME`, then run:

```bash
python manage.py migrate
```

Optional admin user:

```bash
python manage.py createsuperuser
```

### 6. Run the Development Server

```bash
python manage.py runserver
```

Open the app at:

```text
http://127.0.0.1:8000/
```

## Main Pages

| Page | URL | Purpose |
| --- | --- | --- |
| Dashboard | `/` | Campaign summary and recent activity |
| Compose | `/compose/` | Create and send email campaigns |
| Contacts | `/contacts/` | Import, add, edit, and delete recipients |
| Sent Mails | `/sent-mails/` | Review campaign history |
| Analytics | `/analytics/` | View sending performance charts |
| Settings | `/settings/` | Save and test SMTP configuration |
| Admin | `/admin/` | Django admin panel |

## Excel Import Format

The importer accepts flexible column names and maps them into the contact model.

| Contact Field | Accepted Excel Columns |
| --- | --- |
| Name | `name` |
| Email | `email`, `email id`, `e-mail id` |
| College | `college`, `course` |
| Year | `year` |
| Mobile | `mobile`, `mobile no`, `mobile number` |
| Event | `event`, `event name` |

## Email Placeholders

Use placeholders in email content to personalize each message:

```text
Hello @Name,

Thank you for registering for @Event.
Your college is @College and your year is @Year.
```

Supported placeholders include:

- `@Name` or `{{name}}`
- `@College` or `{{college}}`
- `@Year` or `{{year}}`
- `@Mobile` or `{{mobile}}`
- `@Event` or `{{event_name}}`

## Campaign Reports

Each campaign stores individual email logs with:

- Recipient name
- Recipient email
- Status: `Sent` or `Failed`
- Timestamp
- Error details, if delivery failed

Reports can be exported as CSV from:

```text
/export/<campaign_id>/
```

## GitHub README Visibility

GitHub automatically displays this file on the repository homepage because it is named `README.md` and placed in the repository root. After committing and pushing it, it will be visible on GitHub.

```bash
git add README.md
git commit -m "Add professional project README"
git push
```

## Security Notes

- Do not commit `.env` or real credentials.
- Use a strong `SECRET_KEY` in production.
- Keep `DEBUG=False` in production.
- Add your production domain to `ALLOWED_HOSTS`.
- Use Gmail app passwords or a dedicated SMTP provider.

## License

Add your preferred license before publishing this project publicly.
