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

from collections import defaultdict
from providers.azure import fetch_pricing_as_list, fetch_available_regions
from notifications.email_sender import send_html_email
from utils.meter_parser import parse_meter

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
            parsed = _enrich_item(curr_item)

            if meter in prev_by_meter:
                prev_price = prev_by_meter[meter]["Price"]
                curr_price = curr_item["Price"]

                if prev_price != curr_price and prev_price != "N/A" and curr_price != "N/A":
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
                        **parsed,
                    })
            else:
                changes.append({
                    "region": region,
                    "meter": meter,
                    "product": curr_item.get("Product", ""),
                    "change_type": "new",
                    "old_price": None,
                    "new_price": curr_item["Price"],
                    "change_pct": None,
                    **parsed,
                })

        # Check for removed meters
        for meter, prev_item in prev_by_meter.items():
            if meter not in curr_by_meter:
                parsed = _enrich_item(prev_item)
                changes.append({
                    "region": region,
                    "meter": meter,
                    "product": prev_item.get("Product", ""),
                    "change_type": "removed",
                    "old_price": prev_item["Price"],
                    "new_price": None,
                    "change_pct": None,
                    **parsed,
                })

    return changes


def _enrich_item(item):
    """Parse meter name into structured fields for grouping."""
    parsed = parse_meter(
        item.get("Meter", ""),
        item.get("SkuName", ""),
        item.get("Product", ""),
    )
    return {
        "group_key": parsed.get("group_key", item.get("Meter", "")),
        "deployment": parsed.get("deployment", ""),
        "tier": parsed.get("tier", "Standard"),
        "direction": parsed.get("direction", ""),
        "display_name": parsed.get("display_name", item.get("Meter", "")),
    }


def build_pricing_email_html(changes, prev_timestamp):
    """Build an HTML email showing pricing changes grouped by model."""
    colors = {
        "increased": "#dc3545",
        "decreased": "#28a745",
        "new": "#007bff",
        "removed": "#6c757d",
    }

    # Summary counts
    type_counts = defaultdict(int)
    for c in changes:
        type_counts[c["change_type"]] += 1

    summary_parts = []
    for ctype, label in [("increased", "increase"), ("decreased", "decrease"),
                         ("new", "new meter"), ("removed", "removed meter")]:
        count = type_counts.get(ctype, 0)
        if count:
            summary_parts.append(f"{count} {label}{'s' if count != 1 else ''}")

    # Group changes: model -> region -> (deployment, tier) -> [changes]
    by_model = defaultdict(list)
    for c in changes:
        by_model[c.get("group_key", c["meter"])].append(c)

    # Build HTML sections per model
    sections_html = ""
    for model_name in sorted(by_model.keys()):
        model_changes = by_model[model_name]
        change_count = len(model_changes)

        # Sub-group by (region, deployment, tier)
        by_context = defaultdict(list)
        for c in model_changes:
            key = (c["region"], c.get("deployment", ""), c.get("tier", "Standard"))
            by_context[key].append(c)

        rows_html = ""
        for (region, deployment, tier), ctx_changes in sorted(by_context.items()):
            context_label = region
            if deployment:
                context_label += f" / {deployment}"
            if tier and tier != "Standard":
                context_label += f" / {tier}"

            rows_html += f"""
            <tr style="background: #f0f0f0;">
                <td colspan="4" style="padding: 6px 10px; font-weight: bold; font-size: 12px; color: #555;">
                    {context_label}
                </td>
            </tr>"""

            for c in ctx_changes:
                color = colors.get(c["change_type"], "#333")
                direction = c.get("direction", "")
                change_type = c["change_type"].upper()

                if c["change_type"] == "new":
                    price_str = f'<span style="color:{color};font-weight:bold;">NEW</span> ${c["new_price"]:.6f}'
                elif c["change_type"] == "removed":
                    price_str = f'<span style="color:{color};font-weight:bold;">REMOVED</span> (was ${c["old_price"]:.6f})'
                else:
                    arrow = "&#9650;" if c["change_type"] == "increased" else "&#9660;"
                    pct = f'{c["change_pct"]:+.1f}%' if c["change_pct"] is not None else ""
                    price_str = (
                        f'${c["old_price"]:.6f} &rarr; ${c["new_price"]:.6f} '
                        f'<span style="color:{color};font-weight:bold;">{pct} {arrow}</span>'
                    )

                rows_html += f"""
            <tr>
                <td style="padding: 4px 10px 4px 24px; font-size: 13px;">{direction or c["meter"]}</td>
                <td style="padding: 4px 8px; font-size: 13px;">{price_str}</td>
                <td style="padding: 4px 8px; font-size: 12px; color:{color}; font-weight:bold;">{change_type}</td>
                <td style="padding: 4px 8px; font-size: 11px; color: #888;">{c["meter"]}</td>
            </tr>"""

        sections_html += f"""
        <div style="margin-bottom: 16px; border: 1px solid #ddd; border-radius: 6px; overflow: hidden;">
            <div style="background: #2c3e50; color: white; padding: 8px 12px; font-size: 14px; font-weight: bold;">
                {model_name}
                <span style="font-weight: normal; font-size: 12px; opacity: 0.8;">
                    ({change_count} change{'s' if change_count != 1 else ''})
                </span>
            </div>
            <table style="border-collapse: collapse; width: 100%;">
                {rows_html}
            </table>
        </div>"""

    prev_time = prev_timestamp or "N/A (first run)"
    curr_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #333; max-width: 900px;">
        <h2>Azure OpenAI Pricing Change Alert</h2>
        <p><strong>Summary:</strong> {', '.join(summary_parts)}</p>
        <p style="font-size: 12px; color: #666;">
            Previous snapshot: {prev_time}<br>
            Current check: {curr_time}
        </p>

        {sections_html}

        <p style="margin-top: 16px; color: #666; font-size: 12px;">
            Generated by Model Intelligence MCP Server — Pricing Monitor
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
            print("\nNo pricing changes detected. Sending confirmation email.")
            prev_time = previous.get("timestamp", "N/A")
            curr_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            total_meters = sum(len(v) for v in current_prices.values())
            html_body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; color: #333;">
                <h2>Azure OpenAI Pricing Monitor — No Changes Detected</h2>
                <p>The pricing monitor ran successfully and found
                   <strong>no pricing changes</strong> across all regions.</p>
                <p style="font-size: 13px; color: #555;">
                    Regions scanned: <strong>{len(current_prices)}</strong><br>
                    Total meters checked: <strong>{total_meters}</strong><br>
                    Previous snapshot: {prev_time}<br>
                    Current check: {curr_time}
                </p>
                <p style="margin-top: 16px; color: #666; font-size: 12px;">
                    Generated by Model Intelligence MCP Server — Pricing Monitor
                </p>
            </body>
            </html>
            """
            send_html_email("[Pricing Monitor] No Azure OpenAI pricing changes detected", html_body)
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
