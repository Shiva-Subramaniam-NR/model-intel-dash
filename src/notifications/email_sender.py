import os
import sys
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def send_html_email(subject, html_body):
    """Send an HTML email via Gmail SMTP."""
    gmail_user = os.environ.get("GMAIL_USER")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD")
    recipients_raw = os.environ.get("REMINDER_RECIPIENTS", "")
    recipients = [r.strip() for r in recipients_raw.split(",") if r.strip()]

    if not gmail_user or not gmail_password or not recipients:
        print("ERROR: Missing GMAIL_USER, GMAIL_APP_PASSWORD, or REMINDER_RECIPIENTS.")
        print("Set these in your .env file or as environment variables.")
        sys.exit(1)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_user, gmail_password)
        server.sendmail(gmail_user, recipients, msg.as_string())

    print(f"Email sent to {len(recipients)} recipient(s): {', '.join(recipients)}")
