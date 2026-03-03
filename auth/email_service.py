# EMAIL SERVICE
# 100% local mode by default
# To enable SMTP, configure below and uncomment send_email implementation

import streamlit as st

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

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

def send_email(to_email: str, subject: str, body: str, attachments=None):
    """
    Backward compatible:
      send_email(to, subject, body) continua funcionando.
    attachments: lista de dicts:
      [{"filename": "...", "content": b"...", "mime": "application/pdf"}]
    """
    
    try:
        subject = st._tr(subject)
        body = st._tr(body)
    except Exception:
        pass
    
    if not SMTP_ENABLED:
        print("SMTP disabled. Email not sent.")
        return True

    try:
        if attachments:
            msg = MIMEMultipart()
            msg.attach(MIMEText(body, "plain"))

            for a in attachments:
                filename = a.get("filename", "attachment.bin")
                content = a.get("content", b"") or b""
                mime = a.get("mime", "application/octet-stream")

                if "/" in mime:
                    main, sub = mime.split("/", 1)
                else:
                    main, sub = "application", "octet-stream"

                part = MIMEBase(main, sub)
                part.set_payload(content)
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
                msg.attach(part)
        else:
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