# Model Intelligence Dashboard

A unified dashboard for Azure OpenAI model lifecycle management — retirements, pricing, availability, and announcements — powered by MCP (Model Context Protocol) with an AI chatbot assistant, automated retirement reminders, and multi-cloud outage monitoring.

## Architecture

```
                    +---------------------+
                    |   Claude Desktop /   |
                    |   Any MCP Client     |
                    +---------+-----------+
                              |
                              | MCP Protocol (stdio)
                              v
                    +---------------------+
                    |   server.py          |
                    |   (MCP Server)       |
                    |   FastMCP tools:     |
                    |   - hello_checker    |
                    |   - get_model_summary|
                    |   - get_model_pricing|
                    |   - get_model_avail  |
                    |   - get_model_info   |
                    |   - get_whats_new    |
                    +---------+-----------+
                              |
                              | imports
                              v
+------------------+    +---------------------+    +-------------------------+
| dashboard.py     |    |   azure.py           |    |  Microsoft Learn        |
| (Streamlit UI)   |--->|   (Data Provider)    |--->|  MCP Server             |
| - Retirement tab |    |   - MCP-to-MCP calls |    |  learn.microsoft.com/   |
| - Availability   |    |   - REST API calls   |    |  api/mcp                |
| - Pricing tab    |    +---------------------+    +-------------------------+
| - What's New tab |              |
| - Service Status |              |                 +-------------------------+
| - AI Chatbot     |              +---------------->|  Azure Retail Prices    |
+------------------+                                |  API (REST)             |
        |                                           |  prices.azure.com      |
        v                                           +-------------------------+
+------------------+    +-------------------------+
| status.py        |--->| Status Page APIs:       |
| (Status Provider)|    | - status.openai.com     |
| - 5 providers    |    | - status.anthropic.com  |
+------------------+    | - status.aws.amazon.com |
        |               | - azure.status.microsoft|
        v               | - status.cloud.google   |
+------------------+    +-------------------------+
| notifications/   |
| - reminder.py    |---> Gmail SMTP (weekly retirement alerts)
| - alerts.py      |---> Gmail SMTP (outage alerts every 30 min)
| - email_sender.py|
+------------------+
        ^
        |
+------------------+
| GitHub Actions   |
| - weekly-reminder|
| - outage-monitor |
+------------------+
```

### Design Patterns

- **MCP-to-MCP**: The server acts as both an MCP server (for Claude Desktop) and an MCP client (calling Microsoft Learn MCP Server). This eliminates web scraping for documentation pages.
- **REST API for Pricing**: Azure Retail Prices API provides structured JSON for pricing data — no scraping needed.
- **AI Chatbot**: Instead of parsing complex markdown tables from MCP responses, the raw data is sent as context to OpenAI GPT-4o-mini which interprets it naturally.
- **Multi-cloud Status Monitoring**: Uses statuspage.io JSON APIs (OpenAI, Anthropic), RSS feeds (AWS, Azure), and JSON endpoints (GCP) for unified outage tracking.
- **Automated Alerts**: GitHub Actions cron jobs trigger email notifications for retiring models and service outages.
- **Caching**: Streamlit `@st.cache_data` caches data — 1 hour for MCP/API data, 5 minutes for service status.

## Folder Structure

```
model-intel-mcp/
├── .env                              # API keys and email config (not committed)
├── .gitignore                        # Ignores .env, .venv, __pycache__, *.txt
├── README.md                         # This file
├── requirements.txt                  # All Python dependencies
├── bkp/                              # Backup of Phase 1 (httpx + BeautifulSoup)
│   ├── bkpazure.py
│   └── bkpserver.py
├── src/
│   ├── __init__.py
│   ├── server.py                     # MCP Server — registers tools for Claude Desktop
│   ├── dashboard.py                  # Streamlit dashboard + AI chatbot
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── azure.py                  # Azure data provider (MCP client + REST API)
│   │   └── status.py                 # Multi-cloud outage status fetcher (5 providers)
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── table_parser.py           # Retirement table markdown parser (shared)
│   │   └── date_parser.py            # Retirement date extractor (handles 5 date formats)
│   └── notifications/
│       ├── __init__.py
│       ├── email_sender.py           # Shared Gmail SMTP utility
│       ├── reminder.py               # Weekly retirement reminder script
│       ├── alerts.py                 # Outage alert script
│       └── pricing_monitor.py        # Pricing change detector (manual run)
├── data/                             # Pricing snapshots (git-ignored)
│   ├── pricing_previous.json         # Last run's pricing data
│   └── pricing_current.json          # This run's pricing data
├── .github/workflows/
│   ├── weekly-reminder.yml           # Cron: every Monday 9AM UTC
│   └── outage-monitor.yml            # Cron: every 30 minutes
└── tests/                            # Test directory
```

### Key Files

| File | Purpose |
|------|---------|
| `src/server.py` | MCP server with 6 tools, runs via `FastMCP("model-intel")` |
| `src/providers/azure.py` | Data fetching — MCP-to-MCP for docs, REST API for pricing |
| `src/providers/status.py` | Fetches outage status from OpenAI, Anthropic, AWS, Azure, GCP |
| `src/dashboard.py` | Streamlit UI with filters, tabs, service status, and AI chatbot |
| `src/utils/date_parser.py` | Extracts dates from 5 different retirement text formats |
| `src/utils/table_parser.py` | Parses markdown retirement tables into DataFrames |
| `src/notifications/reminder.py` | Standalone script: finds models retiring in 60 days, emails alert |
| `src/notifications/alerts.py` | Standalone script: checks 5 providers, emails if outages found |
| `src/notifications/pricing_monitor.py` | Manual script: compares pricing across all regions, emails if changes found |
| `.env` | Stores API keys and email config (never committed) |

## MCP Tools

| Tool | Type | Description |
|------|------|-------------|
| `hello_checker` | Sync | Health check — returns welcome message |
| `get_model_summary` | Async | Model retirement dates and lifecycle info |
| `get_model_pricing` | Sync | Pricing via Azure Retail Prices REST API |
| `get_model_availability` | Async | Region availability by deployment type |
| `get_model_info` | Async | Model specifications (context window, capabilities) |
| `get_whats_new` | Async | Latest Azure OpenAI announcements |

## Data Sources

| Data | Source | Method |
|------|--------|--------|
| Model Retirements | Microsoft Learn docs | MCP-to-MCP (`learn.microsoft.com/api/mcp`) |
| Model Availability | Microsoft Learn docs | MCP-to-MCP |
| Model Info | Microsoft Learn docs | MCP-to-MCP |
| What's New | Microsoft Learn docs | MCP-to-MCP |
| Pricing | Azure Retail Prices API | REST (`prices.azure.com/api/retail/prices`) |
| Available Regions | Azure Retail Prices API | REST |
| OpenAI Status | status.openai.com | JSON API (statuspage.io) |
| Anthropic Status | status.anthropic.com | JSON API (statuspage.io) |
| AWS Bedrock Status | status.aws.amazon.com | RSS feed |
| Azure AI Status | azure.status.microsoft | RSS feed |
| GCP Vertex AI Status | status.cloud.google.com | JSON endpoint |

## Dashboard Features

- **Retirement Alerts**: Filterable table with confirmed vs tentative retirement dates
- **Availability Tab**: Region-by-model grid with deployment type selector (Global Standard, Provisioned, Data Zone, etc.)
- **Pricing Tab**: Searchable pricing table auto-filtered by sidebar model selection
- **What's New Tab**: Latest Azure OpenAI announcements rendered as markdown
- **Service Status Tab**: Real-time outage monitoring for 5 AI cloud providers with colored indicators
- **AI Chatbot**: Right-side panel powered by OpenAI GPT-4o-mini — ask natural language questions about any Azure OpenAI model
- **Sidebar Filters**: Dynamic model and region dropdowns, refresh button

## Automated Notifications

### Weekly Retirement Reminders
- Runs every Monday at 9AM UTC via GitHub Actions
- Scans retirement data for models retiring within 60 days
- Sends HTML email with urgency color-coding (red/orange/yellow)
- Can also be triggered manually from GitHub Actions UI

### Outage Alerts
- Runs every 30 minutes via GitHub Actions
- Checks all 5 AI cloud providers for active incidents
- Sends email only when outages are detected (no spam when all operational)
- Can also be triggered manually from GitHub Actions UI

### Pricing Change Monitor
- Run manually: `python src/notifications/pricing_monitor.py`
- Fetches pricing for all Azure regions via the Retail Prices API
- Compares against the previous run to detect: price increases, decreases, new meters, removed meters
- Sends color-coded HTML email: red for increases, green for decreases, blue for new entries
- Keeps exactly 2 files in `data/`: `pricing_previous.json` and `pricing_current.json` (rotated on each run)
- First run creates the baseline; changes are detected from the second run onward

## Setup Instructions

### Prerequisites

- Python 3.11+
- Git
- An OpenAI API key (for the chatbot feature)
- A Gmail account with App Password (for email notifications)

### 1. Clone the Repository

```bash
git clone https://github.com/Shiva-Subramaniam-NR/model-intel-dash.git
cd model-intel-dash
```

### 2. Create Virtual Environment

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a `.env` file in the project root:

```
OPENAI_API_KEY=sk-your-openai-api-key-here
GMAIL_USER=your-gmail@gmail.com
GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
REMINDER_RECIPIENTS=alice@example.com,bob@example.com
```

**How to get a Gmail App Password:**
1. Go to https://myaccount.google.com/apppasswords
2. Select "Mail" and your device
3. Copy the 16-character password

### 5. Run the Streamlit Dashboard

```bash
streamlit run src/dashboard.py
```

The dashboard will open at `http://localhost:8501`.

### 6. Test Email Notifications Locally

```bash
# Test retirement reminder
python src/notifications/reminder.py

# Test outage alerts
python src/notifications/alerts.py

# Test pricing change detector (run twice to see comparison)
python src/notifications/pricing_monitor.py
```

### 7. Connect to Claude Desktop (Optional)

Add this to your Claude Desktop config (`%APPDATA%\Claude\claude_desktop_config.json` on Windows):

```json
{
  "mcpServers": {
    "model-intel": {
      "command": "C:\\path\\to\\model-intel-dash\\.venv\\Scripts\\python.exe",
      "args": ["C:\\path\\to\\model-intel-dash\\src\\server.py"]
    }
  }
}
```

Restart Claude Desktop. You should see the hammer icon with 6 tools available.

### 8. Configure GitHub Actions Secrets

Go to your repo > Settings > Secrets and Variables > Actions, and add:

| Secret | Value |
|--------|-------|
| `GMAIL_USER` | Your Gmail address |
| `GMAIL_APP_PASSWORD` | Your Gmail app password |
| `REMINDER_RECIPIENTS` | Comma-separated email addresses |

The workflows will start running automatically on their schedules.

## Running & Debugging

### Run the MCP Server Standalone

```bash
python src/server.py
```

### Run Streamlit with Debug Logging

```bash
streamlit run src/dashboard.py --logger.level=debug
```

### Debug in VS Code

1. Open the project folder in VS Code
2. Set breakpoints in any `.py` file
3. Create a launch configuration (`.vscode/launch.json`):

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Streamlit Dashboard",
      "type": "debugpy",
      "request": "launch",
      "module": "streamlit",
      "args": ["run", "src/dashboard.py"],
      "cwd": "${workspaceFolder}",
      "envFile": "${workspaceFolder}/.env"
    },
    {
      "name": "MCP Server",
      "type": "debugpy",
      "request": "launch",
      "program": "src/server.py",
      "cwd": "${workspaceFolder}"
    },
    {
      "name": "Retirement Reminder",
      "type": "debugpy",
      "request": "launch",
      "program": "src/notifications/reminder.py",
      "cwd": "${workspaceFolder}",
      "envFile": "${workspaceFolder}/.env"
    },
    {
      "name": "Outage Alerts",
      "type": "debugpy",
      "request": "launch",
      "program": "src/notifications/alerts.py",
      "cwd": "${workspaceFolder}",
      "envFile": "${workspaceFolder}/.env"
    }
  ]
}
```

4. Press **F5** to start debugging with breakpoints

### Common Issues

| Issue | Fix |
|-------|-----|
| `ModuleNotFoundError: No module named 'providers'` | Run from `src/` directory or ensure `sys.path` is set |
| `httpx` double-encoding `$filter` | Use `httpx.Request("GET", url)` + `client.send()` instead of `httpx.get()` |
| Chatbot says "set OPENAI_API_KEY" | Create `.env` file in project root with your key |
| MCP server disconnects in Claude | Check `claude_desktop_config.json` paths are correct |
| Streamlit caching stale data | Click "Refresh All Data" button in sidebar |
| Email sending fails | Verify Gmail App Password (not regular password) and check SMTP access |
| Service Status shows "Unknown" | Provider's status page may be temporarily unreachable |

## Requirements

| Package | Purpose |
|---------|---------|
| `mcp` | Model Context Protocol SDK — server and client |
| `httpx` | HTTP client for Azure Retail Prices REST API and status page APIs |
| `python-dotenv` | Loads `.env` file for API keys and email config |
| `streamlit` | Dashboard UI framework |
| `pandas` | DataFrames for structured table display |
| `openai` | OpenAI SDK for the AI chatbot |
| `feedparser` | RSS feed parser for AWS and Azure status feeds |
| `beautifulsoup4` | HTML parsing (retained for backup compatibility) |

## Future Plans

- Add AWS Bedrock model information
- Add GCP Vertex AI model information
- Cost comparison across cloud providers
- Model recommendation engine
- Slack integration for alerts
