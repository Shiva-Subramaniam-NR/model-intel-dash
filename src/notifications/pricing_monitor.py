"""
Azure OpenAI Pricing Change Detector

Compares current Azure OpenAI pricing against a stored snapshot to detect
price increases, decreases, new meters, and removed meters. Sends an email
alert when changes are found.

The snapshot is stored as data/pricing_snapshot.json and committed back to
the repo by GitHub Actions after each run — giving us a git history of
all price changes over time.

Run: python src/notifications/pricing_monitor.py
Scheduled via: .github/workflows/pricing-monitor.yml (every 12 hours)
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

# Path to the snapshot file
SNAPSHOT_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "pricing_snapshot.json")


def load_previous_snapshot():
    """Load the previous pricing snapshot from disk."""
    if not os.path.exists(SNAPSHOT_PATH):
        return {"timestamp": "", "prices": {}}

    with open(SNAPSHOT_PATH, "r") as f:
        return json.load(f)


def save_snapshot(current_prices):
    """Save the current pricing data as the new snapshot."""
    os.makedirs(os.path.dirname(SNAPSHOT_PATH), exist_ok=True)

    snapshot = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "prices": current_prices,
    }

    with open(SNAPSHOT_PATH, "w") as f:
        json.dump(snapshot, f, indent=2)

    print(f"Snapshot saved to {SNAPSHOT_PATH}")


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

    # Step 1: Load previous snapshot
    previous = load_previous_snapshot()
    prev_timestamp = previous.get("timestamp", "")
    prev_prices = previous.get("prices", {})

    is_first_run = not prev_timestamp
    if is_first_run:
        print("First run detected — no previous snapshot to compare against.")
    else:
        print(f"Previous snapshot from: {prev_timestamp}")

    # Step 2: Fetch current pricing for all regions
    current_prices = fetch_all_pricing()

    # Step 3: Compare (skip on first run)
    if not is_first_run:
        changes = compare_pricing(prev_prices, current_prices)

        if changes:
            # Summarize
            increased = sum(1 for c in changes if c["change_type"] == "increased")
            decreased = sum(1 for c in changes if c["change_type"] == "decreased")
            new_count = sum(1 for c in changes if c["change_type"] == "new")
            removed = sum(1 for c in changes if c["change_type"] == "removed")

            print(f"\nChanges detected: {len(changes)} total")
            print(f"  Increases: {increased}, Decreases: {decreased}, New: {new_count}, Removed: {removed}")

            # Step 4: Send email alert
            subject = f"[Pricing Alert] {len(changes)} Azure OpenAI pricing changes detected"
            html_body = build_pricing_email_html(changes, prev_timestamp)
            send_html_email(subject, html_body)
        else:
            print("\nNo pricing changes detected.")
    else:
        print("\nSkipping comparison (first run).")

    # Step 5: Save current snapshot
    save_snapshot(current_prices)
    print("\nDone.")


if __name__ == "__main__":
    main()
