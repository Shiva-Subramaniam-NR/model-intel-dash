import pandas as pd


def parse_retirement_tables(text):
    """Parse markdown tables from retirement data into a DataFrame."""
    all_rows = []
    current_category = ""
    in_table = False

    for line in text.split("\n"):
        line = line.strip()

        # Detect category headers
        if line.startswith("### "):
            candidate = line.replace("### ", "").strip()
            if candidate in ["Text generation", "Audio", "Image and video", "Embedding", "Fine-tuned models"]:
                current_category = candidate
                in_table = False
            continue

        # Detect table header row
        if "Model Name" in line and "|" in line:
            in_table = True
            continue

        # Skip separator rows
        if in_table and line.startswith("|") and set(line.replace("|", "").replace("-", "").replace(" ", "")) <= set(":"):
            continue

        # Parse data rows
        if in_table and line.startswith("|") and line.endswith("|"):
            parts = line.split("|")
            parts = [p.strip().strip("`").strip("*") for p in parts if p.strip()]

            if len(parts) >= 4:
                model = parts[0].strip()
                if model in ["Model Name", "Model", "---", ""] or all(c in "-: " for c in model):
                    continue

                all_rows.append({
                    "Category": current_category,
                    "Model": model,
                    "Version": parts[1].strip() if len(parts) > 1 else "",
                    "Status": parts[2].strip().strip("`") if len(parts) > 2 else "",
                    "Deprecation": parts[3].strip() if len(parts) > 3 else "N/A",
                    "Retirement": parts[4].strip() if len(parts) > 4 else "N/A",
                    "Replacement": parts[5].strip().strip("`") if len(parts) > 5 else ""
                })
        elif in_table and not line.startswith("|") and line != "":
            in_table = False

    return pd.DataFrame(all_rows) if all_rows else pd.DataFrame()
