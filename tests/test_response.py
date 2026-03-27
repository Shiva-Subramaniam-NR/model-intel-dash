"""
Test the retirement and outage notification pipelines end-to-end.
Run from project root: python tests/test_response.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from providers.azure import fetch_model_retirements
from providers.status import fetch_all_statuses
from utils.table_parser import parse_retirement_tables
from utils.date_parser import extract_retirement_date
from datetime import date, timedelta


async def test_retirements_parsed():
    print("=== Retirement data (parsed) ===")
    raw = await fetch_model_retirements()
    df = parse_retirement_tables(raw)
    print(f"Total rows in retirement table: {len(df)}")

    today = date.today()
    cutoff = today + timedelta(days=60)
    upcoming = []
    for _, row in df.iterrows():
        raw_date = row.get("Retirement", "")
        retirement_date = extract_retirement_date(raw_date)
        if retirement_date and today <= retirement_date <= cutoff:
            is_tentative = any(x in raw_date.lower() for x in [
                "no earlier", "not retire before", "as early as"
            ])
            upcoming.append({
                "model": row.get("Model", ""),
                "retirement_date": retirement_date,
                "tentative": is_tentative,
                "days_until": (retirement_date - today).days,
            })

    upcoming.sort(key=lambda x: x["days_until"])
    print(f"Retiring within 60 days: {len(upcoming)}")
    for m in upcoming:
        label = "[TENTATIVE]" if m["tentative"] else "[CONFIRMED]"
        print(f"  {label} {m['model']:45s}  {m['retirement_date']}  ({m['days_until']} days)")


def test_outage_status():
    print("\n=== Outage / service status ===")
    statuses = fetch_all_statuses()
    for ps in statuses:
        incidents = ps.incidents or []
        print(f"  {ps.provider:20s}  {ps.status.value}  ({len(incidents)} incident(s))")
        for inc in incidents[:2]:
            print(f"    - {inc}")


async def main():
    await test_retirements_parsed()
    test_outage_status()


if __name__ == "__main__":
    asyncio.run(main())
