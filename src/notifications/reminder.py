"""
Weekly Retirement Reminder Script

Fetches Azure OpenAI model retirement data, identifies models retiring
within 60 days, and sends an HTML email summary.

Run: python src/notifications/reminder.py
Scheduled via: .github/workflows/weekly-reminder.yml
"""

import sys
import os
import asyncio
from datetime import date, timedelta

# Path setup — allow imports from src/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

from providers.azure import fetch_model_retirements
from utils.table_parser import parse_retirement_tables
from utils.date_parser import extract_retirement_date
from notifications.email_sender import send_html_email

DAYS_THRESHOLD = 60


def get_upcoming_retirements():
    """Fetch retirement data and filter to models retiring within threshold."""
    raw_data = asyncio.run(fetch_model_retirements())
    df = parse_retirement_tables(raw_data)

    if df.empty:
        return []

    today = date.today()
    cutoff = today + timedelta(days=DAYS_THRESHOLD)
    upcoming = []

    for _, row in df.iterrows():
        raw = row.get("Retirement", "")
        retirement_date = extract_retirement_date(raw)
        if retirement_date and today <= retirement_date <= cutoff:
            is_tentative = any(x in raw.lower() for x in [
                "no earlier", "not retire before", "as early as"
            ])
            upcoming.append({
                "model": row.get("Model", ""),
                "version": row.get("Version", ""),
                "category": row.get("Category", ""),
                "status": row.get("Status", ""),
                "retirement_date": retirement_date,
                "retirement_raw": raw,
                "replacement": row.get("Replacement", ""),
                "days_until": (retirement_date - today).days,
                "tentative": is_tentative,
            })

    upcoming.sort(key=lambda x: x["days_until"])
    return upcoming


def build_email_html(upcoming):
    """Build an HTML email body with a table of upcoming retirements."""
    confirmed = [m for m in upcoming if not m["tentative"]]
    tentative = [m for m in upcoming if m["tentative"]]

    def _build_rows(items):
        rows_html = ""
        for item in items:
            days = item["days_until"]
            if days <= 14:
                color = "#dc3545"   # red — urgent
            elif days <= 30:
                color = "#fd7e14"   # orange — warning
            else:
                color = "#ffc107"   # yellow — attention

            rows_html += f"""
            <tr>
                <td style="padding: 8px; border: 1px solid #ddd;">
                    <span style="display:inline-block; width:10px; height:10px;
                          background:{color}; border-radius:50%; margin-right:6px;"></span>
                    {item['days_until']} days
                </td>
                <td style="padding: 8px; border: 1px solid #ddd;"><strong>{item['model']}</strong></td>
                <td style="padding: 8px; border: 1px solid #ddd;">{item['version']}</td>
                <td style="padding: 8px; border: 1px solid #ddd;">{item['category']}</td>
                <td style="padding: 8px; border: 1px solid #ddd;">{item['retirement_date']}</td>
                <td style="padding: 8px; border: 1px solid #ddd;">{item['replacement'] or 'N/A'}</td>
            </tr>
            """
        return rows_html

    def _build_table(rows_html):
        return f"""
        <table style="border-collapse: collapse; width: 100%; margin-top: 8px;">
            <thead>
                <tr style="background: #f8f9fa;">
                    <th style="padding: 8px; border: 1px solid #ddd; text-align: left;">Urgency</th>
                    <th style="padding: 8px; border: 1px solid #ddd; text-align: left;">Model</th>
                    <th style="padding: 8px; border: 1px solid #ddd; text-align: left;">Version</th>
                    <th style="padding: 8px; border: 1px solid #ddd; text-align: left;">Category</th>
                    <th style="padding: 8px; border: 1px solid #ddd; text-align: left;">Retirement Date</th>
                    <th style="padding: 8px; border: 1px solid #ddd; text-align: left;">Replacement</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>
        """

    sections = ""

    if confirmed:
        sections += f"""
        <h3 style="margin-top: 24px; color: #dc3545;">Confirmed Retirements ({len(confirmed)})</h3>
        <p>These models have a confirmed retirement date.</p>
        {_build_table(_build_rows(confirmed))}
        """

    if tentative:
        sections += f"""
        <h3 style="margin-top: 24px; color: #fd7e14;">Tentative Retirements ({len(tentative)})</h3>
        <p>These models have a &quot;No earlier than&quot; date — retirement is not yet confirmed
           but could happen on or after this date.</p>
        {_build_table(_build_rows(tentative))}
        """

    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #333;">
        <h2>Azure OpenAI Model Retirement Reminder</h2>
        <p>The following <strong>{len(upcoming)}</strong> model(s) are retiring within
           the next <strong>{DAYS_THRESHOLD} days</strong>
           ({len(confirmed)} confirmed, {len(tentative)} tentative):</p>
        {sections}
        <p style="margin-top: 16px; color: #666; font-size: 12px;">
            Source: Microsoft Learn Documentation via MCP Server<br>
            Generated by Model Intelligence MCP Server
        </p>
    </body>
    </html>
    """
    return html


def main():
    print(f"Checking for models retiring within {DAYS_THRESHOLD} days...")
    upcoming = get_upcoming_retirements()

    if not upcoming:
        print("No models retiring within the next 60 days. No email sent.")
        return

    confirmed = [m for m in upcoming if not m["tentative"]]
    tentative = [m for m in upcoming if m["tentative"]]
    print(f"Found {len(upcoming)} model(s) retiring soon ({len(confirmed)} confirmed, {len(tentative)} tentative):")
    for item in upcoming:
        tag = "TENTATIVE" if item["tentative"] else "CONFIRMED"
        print(f"  - [{tag}] {item['model']} v{item['version']} — {item['days_until']} days ({item['retirement_date']})")

    subject = f"[Model Intel] {len(upcoming)} Azure OpenAI model(s) retiring within {DAYS_THRESHOLD} days"
    html_body = build_email_html(upcoming)
    send_html_email(subject, html_body)


if __name__ == "__main__":
    main()
