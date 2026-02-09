# Model Intelligence Dashboard

A unified dashboard for Azure OpenAI model lifecycle management — retirements, pricing, availability, and announcements — powered by MCP (Model Context Protocol) with an AI chatbot assistant.

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
| - AI Chatbot     |              |                 +-------------------------+
+------------------+              +---------------->|  Azure Retail Prices    |
                                                    |  API (REST)             |
                                                    |  prices.azure.com      |
                                                    +-------------------------+
```

### Design Patterns

- **MCP-to-MCP**: The server acts as both an MCP server (for Claude Desktop) and an MCP client (calling Microsoft Learn MCP Server). This eliminates web scraping for documentation pages.
- **REST API for Pricing**: Azure Retail Prices API provides structured JSON for pricing data — no scraping needed.
- **AI Chatbot**: Instead of parsing complex markdown tables from MCP responses, the raw data is sent as context to OpenAI GPT-4o-mini which interprets it naturally.
- **Caching**: Streamlit `@st.cache_data(ttl=3600)` caches all MCP/API responses for 1 hour to avoid repeated calls.

## Folder Structure

```
model-intel-mcp/
├── .env                        # OpenAI API key (not committed)
├── .gitignore                  # Ignores .env, .venv, __pycache__, *.txt
├── README.md                   # This file
├── bkp/                        # Backup of Phase 1 (httpx + BeautifulSoup)
│   ├── bkpazure.py
│   └── bkpserver.py
├── src/
│   ├── __init__.py
│   ├── server.py               # MCP Server — registers tools for Claude Desktop
│   ├── dashboard.py            # Streamlit dashboard + AI chatbot
│   └── providers/
│       ├── __init__.py
│       └── azure.py            # Azure data provider (MCP client + REST API)
└── tests/                      # Test directory (future)
```

### Key Files

| File | Purpose |
|------|---------|
| `src/server.py` | MCP server with 6 tools, runs via `FastMCP("model-intel")` |
| `src/providers/azure.py` | Data fetching layer — MCP-to-MCP for docs, REST API for pricing |
| `src/dashboard.py` | Streamlit UI with filters, tabs, and OpenAI-powered chatbot |
| `.env` | Stores `OPENAI_API_KEY` for the chatbot (never committed) |

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

## Dashboard Features

- **Retirement Alerts**: Filterable table with confirmed vs tentative retirement dates
- **Availability Tab**: Region-by-model grid with deployment type selector (Global Standard, Provisioned, Data Zone, etc.)
- **Pricing Tab**: Searchable pricing table auto-filtered by sidebar model selection
- **What's New Tab**: Latest Azure OpenAI announcements rendered as markdown
- **AI Chatbot**: Right-side panel powered by OpenAI GPT-4o-mini — ask natural language questions about any Azure OpenAI model
- **Sidebar Filters**: Dynamic model and region dropdowns, refresh button

## Setup Instructions

### Prerequisites

- Python 3.11+
- Git
- An OpenAI API key (for the chatbot feature)

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
pip install mcp httpx python-dotenv beautifulsoup4 streamlit pandas openai
```

### 4. Configure Environment Variables

Create a `.env` file in the project root:

```
OPENAI_API_KEY=sk-your-openai-api-key-here
```

### 5. Run the Streamlit Dashboard

```bash
streamlit run src/dashboard.py
```

The dashboard will open at `http://localhost:8501`.

### 6. Connect to Claude Desktop (Optional)

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
    }
  ]
}
```

4. Press **F5** to start debugging with breakpoints

### Test Individual Functions

```python
# Quick test for pricing API
import asyncio
from src.providers.azure import fetch_model_pricing, fetch_model_retirements

# Sync function — call directly
print(fetch_model_pricing("swedencentral"))

# Async function — use asyncio.run()
print(asyncio.run(fetch_model_retirements()))
```

### Common Issues

| Issue | Fix |
|-------|-----|
| `ModuleNotFoundError: No module named 'providers'` | Run from `src/` directory or ensure `sys.path` is set |
| `httpx` double-encoding `$filter` | Use `httpx.Request("GET", url)` + `client.send()` instead of `httpx.get()` |
| Chatbot says "set OPENAI_API_KEY" | Create `.env` file in project root with your key |
| MCP server disconnects in Claude | Check `claude_desktop_config.json` paths are correct |
| Streamlit caching stale data | Click "Refresh All Data" button in sidebar |

## Requirements

| Package | Purpose |
|---------|---------|
| `mcp` | Model Context Protocol SDK — server and client |
| `httpx` | HTTP client for Azure Retail Prices REST API |
| `python-dotenv` | Loads `.env` file for API keys |
| `streamlit` | Dashboard UI framework |
| `pandas` | DataFrames for structured table display |
| `openai` | OpenAI SDK for the AI chatbot |
| `beautifulsoup4` | HTML parsing (retained for backup compatibility) |

## Future Plans

- Add AWS Bedrock model information
- Add GCP Vertex AI model information
- Cost comparison across cloud providers
- Model recommendation engine
- Automated retirement alerting via email/Slack
