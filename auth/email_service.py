# EMAIL SERVICE
# Production email via Resend API

import streamlit as st
import os
import resend
from dotenv import load_dotenv

load_dotenv()

RESEND_API_KEY = os.getenv("RESEND_API_KEY")

resend.api_key = RESEND_API_KEY


def send_email(to_email: str, subject: str, body: str, attachments=None):
    """
    Backward compatible:
      send_email(to, subject, body)

    attachments:
      [{"filename": "...", "content": b"...", "mime": "application/pdf"}]
    """

    try:
        subject = st._tr(subject)
        body = st._tr(body)
    except Exception:
        pass

    if not RESEND_API_KEY:
        print("RESEND_API_KEY not configured")
        return False

    try:

        email_payload = {
            "from": "DOMMx <onboarding@resend.dev>",
            "to": [to_email],
            "subject": subject,
            "text": body
        }

        if attachments:

            resend_attachments = []

            for a in attachments:

                resend_attachments.append({
                    "filename": a.get("filename"),
                    "content": a.get("content"),
                })

            email_payload["attachments"] = resend_attachments

        print("Sending email via Resend to:", to_email)

        resend.Emails.send(email_payload)

        return True

    except Exception as e:
        print("Email error:", e)
        return False