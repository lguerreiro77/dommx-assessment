# EMAIL SERVICE
# 100% local mode by default
# To enable SMTP, configure below and uncomment send_email implementation

import smtplib
from email.mime.text import MIMEText

import os
from dotenv import load_dotenv

load_dotenv()

SMTP_ENABLED = True  # <- mudar para True quando configurar

SMTP_CONFIG = {
    "server": "smtp.gmail.com",
    "port": 587,
    "username": os.getenv("SMTP_USER"),
    "password": os.getenv("SMTP_PASS")
}

def send_email(to_email: str, subject: str, body: str):
    if not SMTP_ENABLED:
        print("SMTP disabled. Email not sent.")
        return True

    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = SMTP_CONFIG["username"]
        msg["To"] = to_email

        server = smtplib.SMTP(SMTP_CONFIG["server"], SMTP_CONFIG["port"])
        server.starttls()
        server.login(SMTP_CONFIG["username"], SMTP_CONFIG["password"])
        server.sendmail(
            SMTP_CONFIG["username"],
            [to_email],
            msg.as_string()
        )
        server.quit()

        return True

    except Exception as e:
        print("Email error:", e)
        return False
