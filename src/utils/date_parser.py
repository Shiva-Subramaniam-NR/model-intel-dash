import re
from datetime import datetime, date


def extract_retirement_date(text):
    """
    Extract the earliest actionable retirement date from a retirement cell value.

    Handles all observed formats:
    1. Simple ISO: "2026-03-01"
    2. "No earlier than" + ISO: "No earlier than 2026-04-14"
    3. "No earlier than" + written: "No earlier than February 28, 2026"
    4. Bold embedded dates: "...retires on **2026-03-31**..." (takes earliest)
    5. "Will not retire before": "Will not retire before April 15, 2027"

    Returns None if no date can be parsed.
    """
    if not text or text.strip().lower() in ("n/a", "", "-"):
        return None

    text = text.strip()

    # Format 1: Simple ISO date (exact match)
    iso_match = re.fullmatch(r"\d{4}-\d{2}-\d{2}", text)
    if iso_match:
        return datetime.strptime(text, "%Y-%m-%d").date()

    # Format 4: Bold embedded dates **YYYY-MM-DD** (check early — complex text may also
    # contain "No earlier than")
    bold_dates = re.findall(r"\*\*(\d{4}-\d{2}-\d{2})\*\*", text)
    if bold_dates:
        parsed = [datetime.strptime(d, "%Y-%m-%d").date() for d in bold_dates]
        return min(parsed)

    # Format 2: "No earlier than YYYY-MM-DD"
    net_iso = re.search(r"[Nn]o earlier than\s+(\d{4}-\d{2}-\d{2})", text)
    if net_iso:
        return datetime.strptime(net_iso.group(1), "%Y-%m-%d").date()

    # Format 3: "No earlier than Month DD, YYYY"
    net_written = re.search(r"[Nn]o earlier than\s+([A-Z][a-z]+ \d{1,2},?\s*\d{4})", text)
    if net_written:
        return _parse_written_date(net_written.group(1))

    # Format 5: "Will not retire before Month DD, YYYY"
    wnrb = re.search(r"[Nn]ot retire before\s+([A-Z][a-z]+ \d{1,2},?\s*\d{4})", text)
    if wnrb:
        return _parse_written_date(wnrb.group(1))

    # Fallback: find any YYYY-MM-DD anywhere in the text
    fallback = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if fallback:
        return datetime.strptime(fallback.group(1), "%Y-%m-%d").date()

    return None


def _parse_written_date(date_str):
    """Parse a written date like 'February 28, 2026' or 'February 28 2026'."""
    date_str = date_str.strip()
    # Normalize: ensure comma between day and year
    if "," not in date_str:
        parts = date_str.rsplit(" ", 1)
        date_str = parts[0] + ", " + parts[1]
    return datetime.strptime(date_str.strip(), "%B %d, %Y").date()
