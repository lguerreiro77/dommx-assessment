import os
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
from storage.google_sheets import get_sheet
from auth.crypto_service import decrypt_text


def send_assessment_completed_email(user_hash, project_id):

    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")

    # -------------------------------------------------
    # USERS
    # -------------------------------------------------
    user_sheet = get_sheet("users")
    user_rows = user_sheet.get_all_records()

    user_name = None
    user_email = None

    for row in user_rows:
        if str(row.get("email_hash")).strip() == str(user_hash).strip():

            try:
                user_name = decrypt_text(row.get("full_name_encrypted"))
                user_email = decrypt_text(row.get("email_encrypted"))
            except Exception:
                user_name = None
                user_email = None

            break

    # -------------------------------------------------
    # PROJECTS
    # -------------------------------------------------
    project_sheet = get_sheet("projects")
    project_rows = project_sheet.get_all_records()

    project_name = None

    for row in project_rows:
        if str(row.get("project_id")).strip() == str(project_id).strip():
            project_name = row.get("name")
            break

    user_name = user_name or "Unknown User"
    user_email = user_email or "Unknown Email"
    project_name = project_name or "Unknown Project"

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    subject = "DOMMx Assessment Completed"

    body = f"""
{user_name} ({user_email}) completou o projeto: {project_name}

Data/Hora: {now}
"""

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = smtp_user

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, [smtp_user], msg.as_string())
