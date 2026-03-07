"""
Azure OpenAI Pricing Change Detector

Compares current Azure OpenAI pricing against the previous run to detect
price increases, decreases, new meters, and removed meters. Sends an email
alert when changes are found.

Keeps exactly 2 files in data/:
  - pricing_previous.json  (last run's data)
  - pricing_current.json   (this run's data)

On each run:
  1. Fetch fresh pricing for all regions
  2. Compare against pricing_previous.json (if it exists)
  3. Send email if changes detected
  4. Rotate: current -> previous, save new current

Run manually: python src/notifications/pricing_monitor.py
"""

import sys
import os
import json
from datetime import datetime, timezone

# Path setup — allow imports from src/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

from providers.azure import fetch_pricing_as_list, fetch_available_regions
from notifications.email_sender import send_html_email

# Paths to the two pricing files
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
PREVIOUS_PATH = os.path.join(DATA_DIR, "pricing_previous.json")
CURRENT_PATH = os.path.join(DATA_DIR, "pricing_current.json")


def load_json(path):
    """Load a pricing JSON file. Returns None if it doesn't exist."""
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        return json.load(f)


def save_json(path, prices):
    """Save pricing data to a JSON file with timestamp."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "prices": prices,
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Saved: {path}")


def fetch_all_pricing():
    """Fetch pricing for all available regions."""
    regions = fetch_available_regions()
    print(f"Fetching pricing for {len(regions)} regions...")

    all_prices = {}
    for region in regions:
        print(f"  Fetching: {region}...")
        items = fetch_pricing_as_list(region)
        all_prices[region] = items

    total = sum(len(v) for v in all_prices.values())
    print(f"Fetched {total} pricing entries across {len(regions)} regions.")
    return all_prices


def compare_pricing(previous_prices, current_prices):
    """
    Compare previous and current pricing to find changes.

    Returns a list of change dicts:
    {
        "region": str,
        "meter": str,
        "product": str,
        "change_type": "increased" | "decreased" | "new" | "removed",
        "old_price": float | None,
        "new_price": float | None,
        "change_pct": float | None,
    }
    """
    changes = []

    # Get all regions from both snapshots
    all_regions = set(list(previous_prices.keys()) + list(current_prices.keys()))

    for region in sorted(all_regions):
        prev_items = previous_prices.get(region, [])
        curr_items = current_prices.get(region, [])

        # Build lookup by Meter name
        prev_by_meter = {item["Meter"]: item for item in prev_items}
        curr_by_meter = {item["Meter"]: item for item in curr_items}

        # Check for price changes and new meters
        for meter, curr_item in curr_by_meter.items():
            if meter in prev_by_meter:
                prev_price = prev_by_meter[meter]["Price"]
                curr_price = curr_item["Price"]

                if prev_price != curr_price and prev_price != "N/A" and curr_price != "N/A":
                    # Calculate percentage change
                    if prev_price > 0:
                        change_pct = ((curr_price - prev_price) / prev_price) * 100
                    else:
                        change_pct = 100.0

                    changes.append({
                        "region": region,
                        "meter": meter,
                        "product": curr_item.get("Product", ""),
                        "change_type": "increased" if curr_price > prev_price else "decreased",
                        "old_price": prev_price,
                        "new_price": curr_price,
                        "change_pct": round(change_pct, 2),
                    })
            else:
                # New meter — didn't exist before
                changes.append({
                    "region": region,
                    "meter": meter,
                    "product": curr_item.get("Product", ""),
                    "change_type": "new",
                    "old_price": None,
                    "new_price": curr_item["Price"],
                    "change_pct": None,
                })

        # Check for removed meters
        for meter, prev_item in prev_by_meter.items():
            if meter not in curr_by_meter:
                changes.append({
                    "region": region,
                    "meter": meter,
                    "product": prev_item.get("Product", ""),
                    "change_type": "removed",
                    "old_price": prev_item["Price"],
                    "new_price": None,
                    "change_pct": None,
                })

    return changes


def build_pricing_email_html(changes, prev_timestamp):
    """Build an HTML email showing all pricing changes."""
    # Group changes by type for summary
    increased = [c for c in changes if c["change_type"] == "increased"]
    decreased = [c for c in changes if c["change_type"] == "decreased"]
    new_items = [c for c in changes if c["change_type"] == "new"]
    removed = [c for c in changes if c["change_type"] == "removed"]

    summary = []
    if increased:
        summary.append(f"{len(increased)} price increase(s)")
    if decreased:
        summary.append(f"{len(decreased)} price decrease(s)")
    if new_items:
        summary.append(f"{len(new_items)} new meter(s)")
    if removed:
        summary.append(f"{len(removed)} removed meter(s)")

    # Color map for change types
    colors = {
        "increased": "#dc3545",   # red
        "decreased": "#28a745",   # green
        "new": "#007bff",         # blue
        "removed": "#6c757d",     # gray
    }

    # Build table rows
    rows_html = ""
    for c in changes:
        color = colors.get(c["change_type"], "#333")
        change_label = c["change_type"].upper()

        old_str = f"${c['old_price']:.6f}" if c["old_price"] is not None else "—"
        new_str = f"${c['new_price']:.6f}" if c["new_price"] is not None else "—"
        pct_str = f"{c['change_pct']:+.2f}%" if c["change_pct"] is not None else "—"

        rows_html += f"""
        <tr>
            <td style="padding: 6px 8px; border: 1px solid #ddd;">{c['region']}</td>
            <td style="padding: 6px 8px; border: 1px solid #ddd;">{c['meter']}</td>
            <td style="padding: 6px 8px; border: 1px solid #ddd;">{old_str}</td>
            <td style="padding: 6px 8px; border: 1px solid #ddd;">{new_str}</td>
            <td style="padding: 6px 8px; border: 1px solid #ddd; color:{color}; font-weight:bold;">
                {pct_str}
            </td>
            <td style="padding: 6px 8px; border: 1px solid #ddd; color:{color}; font-weight:bold;">
                {change_label}
            </td>
            <td style="padding: 6px 8px; border: 1px solid #ddd; font-size:12px;">{c['product']}</td>
        </tr>
        """

    prev_time = prev_timestamp or "N/A (first run)"
    curr_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #333;">
        <h2>Azure OpenAI Pricing Change Alert</h2>
        <p><strong>Summary:</strong> {', '.join(summary)}</p>
        <p style="font-size: 12px; color: #666;">
            Previous snapshot: {prev_time}<br>
            Current check: {curr_time}
        </p>

        <table style="border-collapse: collapse; width: 100%; margin-top: 12px; font-size: 13px;">
            <thead>
                <tr style="background: #f8f9fa;">
                    <th style="padding: 8px; border: 1px solid #ddd; text-align: left;">Region</th>
                    <th style="padding: 8px; border: 1px solid #ddd; text-align: left;">Meter</th>
                    <th style="padding: 8px; border: 1px solid #ddd; text-align: left;">Old Price</th>
                    <th style="padding: 8px; border: 1px solid #ddd; text-align: left;">New Price</th>
                    <th style="padding: 8px; border: 1px solid #ddd; text-align: left;">Change</th>
                    <th style="padding: 8px; border: 1px solid #ddd; text-align: left;">Type</th>
                    <th style="padding: 8px; border: 1px solid #ddd; text-align: left;">Product</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>

        <p style="margin-top: 16px; color: #666; font-size: 12px;">
            Generated by Model Intelligence Dashboard — Pricing Monitor
        </p>
    </body>
    </html>
    """
    return html


def main():
    print("=== Azure OpenAI Pricing Change Detector ===\n")

    # Step 1: Load previous data (from pricing_previous.json)
    previous = load_json(PREVIOUS_PATH)
    is_first_run = previous is None

    if is_first_run:
        print("First run — no previous pricing file found.")
    else:
        print(f"Previous pricing from: {previous.get('timestamp', 'unknown')}")

    # Step 2: Fetch current pricing for all regions
    current_prices = fetch_all_pricing()

    # Step 3: Compare (skip on first run)
    if not is_first_run:
        prev_prices = previous.get("prices", {})
        changes = compare_pricing(prev_prices, current_prices)

        if changes:
            increased = sum(1 for c in changes if c["change_type"] == "increased")
            decreased = sum(1 for c in changes if c["change_type"] == "decreased")
            new_count = sum(1 for c in changes if c["change_type"] == "new")
            removed = sum(1 for c in changes if c["change_type"] == "removed")

            print(f"\nChanges detected: {len(changes)} total")
            print(f"  Increases: {increased}, Decreases: {decreased}, New: {new_count}, Removed: {removed}")

            subject = f"[Pricing Alert] {len(changes)} Azure OpenAI pricing changes detected"
            html_body = build_pricing_email_html(changes, previous.get("timestamp", ""))
            send_html_email(subject, html_body)
        else:
            print("\nNo pricing changes detected.")
    else:
        print("\nSkipping comparison (first run).")

    # Step 4: Rotate files — current becomes previous, save new current
    if os.path.exists(CURRENT_PATH):
        # Move current -> previous (overwrite previous)
        os.replace(CURRENT_PATH, PREVIOUS_PATH)
        print(f"Rotated: pricing_current.json -> pricing_previous.json")

    save_json(CURRENT_PATH, current_prices)
    print("\nDone.")


if __name__ == "__main__":
    main()
