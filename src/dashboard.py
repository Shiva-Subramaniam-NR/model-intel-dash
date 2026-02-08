import streamlit as st
import asyncio
import sys
import os
import pandas as pd
import re

# Add the src directory to Python path so we can import providers
sys.path.insert(0, os.path.dirname(__file__))

from providers.azure import (
    fetch_model_retirements,
    fetch_model_pricing,
    fetch_model_availability,
    fetch_whats_new,
    fetch_available_regions,
    fetch_pricing_as_list
)

# --- Helper ---
def run_async(coro):
    """Run an async coroutine from sync Streamlit context."""
    return asyncio.run(coro)


# --- Page Config ---
st.set_page_config(
    page_title="Model Intelligence Dashboard",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)


# --- Caching: fetch data once, reuse across interactions ---
@st.cache_data(ttl=3600, show_spinner="Fetching retirement data...")
def get_retirement_data():
    return run_async(fetch_model_retirements())

@st.cache_data(ttl=3600, show_spinner="Fetching availability data...")
def get_availability_data():
    return run_async(fetch_model_availability())

@st.cache_data(ttl=3600, show_spinner="Fetching latest announcements...")
def get_whats_new_data():
    return run_async(fetch_whats_new())

@st.cache_data(ttl=3600, show_spinner="Fetching available regions...")
def get_regions():
    return fetch_available_regions()

@st.cache_data(ttl=3600, show_spinner="Fetching pricing data...")
def get_pricing_data(region):
    return fetch_pricing_as_list(region)


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


def parse_single_availability_table(text, marker):
    """Parse a single availability table starting from a marker heading."""
    start = text.find(marker)
    if start == -1:
        return pd.DataFrame(), []

    section = text[start:]
    lines = section.split("\n")

    header_line = None
    data_rows = []

    for line in lines:
        line = line.strip()
        if not line.startswith("|"):
            if header_line is not None and data_rows:
                break
            continue

        if line.startswith("| ---") or set(line.replace("|", "").replace("-", "").replace(" ", "")) <= set(":"):
            continue

        if header_line is None and "Region" in line:
            header_line = line
        elif header_line is not None:
            data_rows.append(line)

    if not header_line or not data_rows:
        return pd.DataFrame(), []

    header_parts = [p.strip().strip("*").strip() for p in header_line.split("|") if p.strip()]
    model_columns = []
    for h in header_parts[1:]:
        parts_h = h.strip().strip("*").split(",")
        name = parts_h[0].strip().strip("*")
        version = parts_h[1].strip().strip("*") if len(parts_h) > 1 else ""
        col_name = f"{name} ({version})" if version else name
        model_columns.append(col_name)

    rows = []
    for row_line in data_rows:
        parts = [p.strip() for p in row_line.split("|") if p.strip() != ""]
        if len(parts) >= 2:
            region = parts[0].strip()
            values = []
            for v in parts[1:]:
                values.append("✅" if "✅" in v.strip() else "-")
            while len(values) < len(model_columns):
                values.append("-")
            rows.append([region] + values[:len(model_columns)])

    if rows:
        columns = ["Region"] + model_columns
        return pd.DataFrame(rows, columns=columns), model_columns
    return pd.DataFrame(), []


def parse_all_availability_tables(text):
    """Parse all deployment type availability tables into a dict of DataFrames."""
    deployment_types = {
        "Global Standard": "### Global Standard model availability",
        "Global Provisioned": "### Global Provisioned managed model availability",
        "Global Batch": "### Global Batch model availability",
        "Data Zone Standard": "### Data Zone Standard model availability",
        "Data Zone Provisioned": "### Data Zone Provisioned managed model availability",
        "Data Zone Batch": "### Data Zone Batch model availability",
        "Standard": "### Standard deployment model availability",
        "Provisioned": "### Provisioned deployment model availability",
    }

    results = {}
    for dep_type, marker in deployment_types.items():
        df, models = parse_single_availability_table(text, marker)
        if not df.empty:
            results[dep_type] = (df, models)
    return results


def extract_models_from_df(df):
    """Extract unique model names from retirement DataFrame."""
    if df.empty:
        return ["All Models"]
    models = sorted(df["Model"].unique().tolist())
    return ["All Models"] + models


# --- Load Data ---
retirement_data = get_retirement_data()
retirement_df = parse_retirement_tables(retirement_data)
regions = get_regions()
models_list = extract_models_from_df(retirement_df)


# --- Sidebar ---
with st.sidebar:
    st.header("Filters")
    st.markdown("---")

    selected_model = st.selectbox(
        "Select Model",
        options=models_list,
        help="Filter retirement, availability, and pricing by model"
    )

    selected_region = st.selectbox(
        "Select Region",
        options=regions if regions else ["swedencentral"],
        help="Choose an Azure region to view pricing"
    )

    st.markdown("---")
    st.caption("Data: Microsoft Learn MCP + Azure Retail Prices API")

    if st.button("Refresh All Data"):
        st.cache_data.clear()
        st.rerun()


# --- Header ---
st.title("Model Intelligence Dashboard")
st.caption("Azure OpenAI model lifecycle, pricing & availability")
st.divider()


# --- Retirement Alert Banner ---
st.subheader("Retirement Alerts")

if not retirement_df.empty:
    # Toggle for date type
    date_filter = st.radio(
        "Filter by retirement date type:",
        ["All", "Confirmed dates", "Tentative (No earlier than)"],
        horizontal=True
    )

    # Apply model filter
    if selected_model != "All Models":
        display_df = retirement_df[retirement_df["Model"] == selected_model].copy()
    else:
        display_df = retirement_df.copy()

    # Apply date type filter
    if date_filter == "Confirmed dates":
        display_df = display_df[
            ~display_df["Retirement"].str.contains("No earlier|no earlier|No retirement|not retire|n/a", case=False, na=False)
            & (display_df["Retirement"].str.strip() != "")
        ]
    elif date_filter == "Tentative (No earlier than)":
        display_df = display_df[
            display_df["Retirement"].str.contains("No earlier|no earlier|No retirement|not retire", case=False, na=False)
        ]

    if display_df.empty:
        st.info("No retirement entries match the current filters.")
    else:
        st.metric("Models shown", len(display_df))
        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Category": st.column_config.TextColumn("Category", width="small"),
                "Model": st.column_config.TextColumn("Model", width="medium"),
                "Version": st.column_config.TextColumn("Version", width="small"),
                "Status": st.column_config.TextColumn("Status", width="small"),
                "Deprecation": st.column_config.TextColumn("Deprecation", width="medium"),
                "Retirement": st.column_config.TextColumn("Retirement", width="large"),
                "Replacement": st.column_config.TextColumn("Replacement", width="small"),
            }
        )
else:
    with st.expander("Full Retirement Details", expanded=True):
        st.markdown(retirement_data)

st.divider()


# --- Tabs ---
tab1, tab2, tab3 = st.tabs(["Availability", "Pricing", "What's New"])


# --- Tab 1: Availability ---
with tab1:
    st.subheader("Model Availability by Region")
    availability_data = get_availability_data()
    all_tables = parse_all_availability_tables(availability_data)

    if all_tables:
        # Deployment type selector
        dep_types = list(all_tables.keys())
        selected_dep_type = st.radio(
            "Deployment Type:",
            dep_types,
            horizontal=True
        )

        avail_df, avail_models = all_tables[selected_dep_type]

        # Filter by selected model
        if selected_model != "All Models":
            matching_cols = ["Region"]
            model_search = selected_model.lower()
            for col in avail_models:
                if model_search in col.lower():
                    matching_cols.append(col)

            if len(matching_cols) > 1:
                filtered_avail = avail_df[matching_cols]
                data_cols = [c for c in matching_cols if c != "Region"]
                mask = filtered_avail[data_cols].apply(lambda row: any(v == "✅" for v in row), axis=1)
                available_regions = filtered_avail[mask]
                unavailable_regions = filtered_avail[~mask]

                st.info(f"**{selected_model}** on **{selected_dep_type}** deployment")

                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Available in", len(available_regions), "regions")
                with col2:
                    st.metric("Not available in", len(unavailable_regions), "regions")

                st.dataframe(available_regions, use_container_width=True, hide_index=True)

                with st.expander("Regions where model is NOT available"):
                    if not unavailable_regions.empty:
                        st.dataframe(unavailable_regions, use_container_width=True, hide_index=True)
                    else:
                        st.write("Available in all regions.")
            else:
                st.warning(f"**{selected_model}** is not available on **{selected_dep_type}** deployment type.")
        else:
            st.info(f"Showing all models for **{selected_dep_type}** deployment.")
            st.dataframe(avail_df, use_container_width=True, hide_index=True)
    else:
        st.warning("Could not parse availability data.")
        st.markdown(availability_data)


# --- Tab 2: Pricing ---
with tab2:
    st.subheader(f"Pricing — {selected_region}")
    pricing_items = get_pricing_data(selected_region)

    if pricing_items:
        pricing_df = pd.DataFrame(pricing_items)

        # Auto-populate search from sidebar model selection
        default_search = "" if selected_model == "All Models" else selected_model
        search_term = st.text_input(
            "Filter by model name",
            value=default_search,
            placeholder="e.g. gpt-4o, o3, embedding"
        )

        if search_term:
            mask = pricing_df['Meter'].str.contains(search_term, case=False, na=False) | \
                   pricing_df['Product'].str.contains(search_term, case=False, na=False)
            filtered_pricing = pricing_df[mask]
        else:
            filtered_pricing = pricing_df

        st.metric("Pricing entries", len(filtered_pricing))

        st.dataframe(
            filtered_pricing,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Meter": st.column_config.TextColumn("Meter Name", width="large"),
                "Price": st.column_config.NumberColumn("Price (USD)", format="$%.6f"),
                "Unit": st.column_config.TextColumn("Unit", width="small"),
                "Product": st.column_config.TextColumn("Product", width="medium"),
            }
        )
    else:
        st.warning(f"No pricing data found for region: {selected_region}")


# --- Tab 3: What's New ---
with tab3:
    st.subheader("What's New in Azure OpenAI")
    whats_new_data = get_whats_new_data()
    st.markdown(whats_new_data)
