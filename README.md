# Model Intelligence MCP Server

An MCP server for Azure OpenAI model lifecycle management with automated email notifications for model retirements, pricing changes, and multi-cloud outage monitoring.

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
                    +---------+-----------+
                              |
                              | imports
                              v
+---------------------+    +-------------------------+
|   azure.py           |    |  Microsoft Learn        |
|   (Data Provider)    |--->|  MCP Server             |
|   - MCP-to-MCP calls |    |  learn.microsoft.com/   |
|   - REST API calls   |    |  api/mcp                |
+---------------------+    +-------------------------+
          |
          |                 +-------------------------+
          +---------------->|  Azure Retail Prices    |
                            |  API (REST)             |
                            |  prices.azure.com      |
                            +-------------------------+

+------------------+    +-------------------------+
| status.py        |--->| Status Page APIs:       |
| (Status Provider)|    | - status.openai.com     |
| - 5 providers    |    | - status.anthropic.com  |
+------------------+    | - status.aws.amazon.com |
                        | - azure.status.microsoft|
                        | - status.cloud.google   |
                        +-------------------------+

+------------------+
| notifications/   |
| - reminder.py    |---> Gmail SMTP (weekly retirement alerts)
| - alerts.py      |---> Gmail SMTP (outage alerts every 30 min)
| - pricing_monitor|---> Gmail SMTP (pricing change alerts)
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
- **Multi-cloud Status Monitoring**: Uses statuspage.io JSON APIs (OpenAI, Anthropic), RSS feeds (AWS, Azure), and JSON endpoints (GCP) for unified outage tracking.
- **Automated Alerts**: GitHub Actions cron jobs trigger email notifications for retiring models and service outages.

## Folder Structure

```
model-intel-mcp/
├── .env                              # API keys and email config (not committed)
├── .gitignore
├── README.md
├── requirements.txt
├── src/
│   ├── __init__.py
│   ├── server.py                     # MCP Server — registers tools for Claude Desktop
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── azure.py                  # Azure data provider (MCP client + REST API)
│   │   └── status.py                 # Multi-cloud outage status fetcher (5 providers)
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── table_parser.py           # Retirement table markdown parser
│   │   └── date_parser.py            # Retirement date extractor (handles 5 date formats)
│   └── notifications/
│       ├── __init__.py
│       ├── email_sender.py           # Shared Gmail SMTP utility
│       ├── reminder.py               # Weekly retirement reminder script
│       ├── alerts.py                 # Outage alert script
│       └── pricing_monitor.py        # Pricing change detector
├── data/                             # Pricing snapshots (git-ignored)
│   ├── pricing_previous.json         # Last run's pricing data
│   └── pricing_current.json          # This run's pricing data
└── .github/workflows/
    ├── weekly-reminder.yml           # Cron: every Monday 9AM UTC
    └── outage-monitor.yml            # Cron: every 30 minutes
```

### Key Files

| File | Purpose |
|------|---------|
| `src/server.py` | MCP server with 3 tools, runs via `FastMCP("model-intel")` |
| `src/providers/azure.py` | Data fetching — MCP-to-MCP for docs, REST API for pricing |
| `src/providers/status.py` | Fetches outage status from OpenAI, Anthropic, AWS, Azure, GCP |
| `src/utils/date_parser.py` | Extracts dates from 5 different retirement text formats |
| `src/utils/table_parser.py` | Parses markdown retirement tables into DataFrames |
| `src/notifications/reminder.py` | Standalone script: finds models retiring in 60 days, emails alert |
| `src/notifications/alerts.py` | Standalone script: checks 5 providers, emails if outages found |
| `src/notifications/pricing_monitor.py` | Standalone script: compares pricing across all regions, emails if changes found |

## MCP Tools

| Tool | Type | Description |
|------|------|-------------|
| `hello_checker` | Sync | Health check — returns welcome message |
| `get_model_summary` | Async | Model retirement dates and lifecycle info |
| `get_model_pricing` | Sync | Pricing via Azure Retail Prices REST API |

## Data Sources

| Data | Source | Method |
|------|--------|--------|
| Model Retirements | Microsoft Learn docs | MCP-to-MCP (`learn.microsoft.com/api/mcp`) |
| Pricing | Azure Retail Prices API | REST (`prices.azure.com/api/retail/prices`) |
| OpenAI Status | status.openai.com | JSON API (statuspage.io) |
| Anthropic Status | status.anthropic.com | JSON API (statuspage.io) |
| AWS Bedrock Status | status.aws.amazon.com | RSS feed |
| Azure AI Status | azure.status.microsoft | RSS feed |
| GCP Vertex AI Status | status.cloud.google.com | JSON endpoint |

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

## Setup

### Prerequisites

- Python 3.11+
- Git
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
GMAIL_USER=your-gmail@gmail.com
GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
REMINDER_RECIPIENTS=alice@example.com,bob@example.com
```

**How to get a Gmail App Password:**
1. Go to https://myaccount.google.com/apppasswords
2. Select "Mail" and your device
3. Copy the 16-character password

### 5. Test Notifications Locally

```bash
# Test retirement reminder
python src/notifications/reminder.py

# Test outage alerts
python src/notifications/alerts.py

# Test pricing change detector (run twice to see comparison)
python src/notifications/pricing_monitor.py
```

### 6. Connect to Claude Desktop

Add this to your Claude Desktop config (`%APPDATA%\Claude\claude_desktop_config.json` on Windows):

```json
{
  "mcpServers": {
    "model-intel": {
      "command": "C:\\path\\to\\model-intel-mcp\\.venv\\Scripts\\python.exe",
      "args": ["C:\\path\\to\\model-intel-mcp\\src\\server.py"]
    }
  }
}
```

Restart Claude Desktop. You should see the hammer icon with 3 tools available.

### 7. Configure GitHub Actions Secrets

Go to your repo > Settings > Secrets and Variables > Actions, and add:

| Secret | Value |
|--------|-------|
| `GMAIL_USER` | Your Gmail address |
| `GMAIL_APP_PASSWORD` | Your Gmail app password |
| `REMINDER_RECIPIENTS` | Comma-separated email addresses |

The workflows will start running automatically on their schedules.

## Debugging

### Run the MCP Server Standalone

```bash
python src/server.py
```

### Debug in VS Code

Create `.vscode/launch.json`:

```json
{
  "version": "0.2.0",
  "configurations": [
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
    },
    {
      "name": "Pricing Monitor",
      "type": "debugpy",
      "request": "launch",
      "program": "src/notifications/pricing_monitor.py",
      "cwd": "${workspaceFolder}",
      "envFile": "${workspaceFolder}/.env"
    }
  ]
}
```

### Common Issues

| Issue | Fix |
|-------|-----|
| `ModuleNotFoundError: No module named 'providers'` | Run from `src/` directory or ensure `sys.path` is set |
| `httpx` double-encoding `$filter` | Use `httpx.Request("GET", url)` + `client.send()` instead of `httpx.get()` |
| MCP server disconnects in Claude | Check `claude_desktop_config.json` paths are correct |
| Email sending fails | Verify Gmail App Password (not regular password) and check SMTP access |
| Service Status shows "Unknown" | Provider's status page may be temporarily unreachable |

## Requirements

| Package | Purpose |
|---------|---------|
| `mcp` | Model Context Protocol SDK — server and client |
| `httpx` | HTTP client for Azure Retail Prices REST API and status page APIs |
| `python-dotenv` | Loads `.env` file for API keys and email config |
| `pandas` | DataFrames for retirement table parsing |
| `feedparser` | RSS feed parser for AWS and Azure status feeds |

## Future Plans

- Add AWS Bedrock model information
- Add GCP Vertex AI model information
- Cost comparison across cloud providers
- Slack integration for alerts
