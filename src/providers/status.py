"""
Cloud AI Service Status Fetcher

Monitors outage status for 5 AI cloud providers:
- OpenAI (statuspage.io JSON API)
- Anthropic/Claude (statuspage.io JSON API)
- AWS Bedrock (RSS feed)
- Azure AI (RSS feed)
- GCP Vertex AI (JSON endpoint)
"""

import httpx
import feedparser
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class ServiceHealth(Enum):
    OPERATIONAL = "operational"
    DEGRADED = "degraded"
    PARTIAL_OUTAGE = "partial_outage"
    MAJOR_OUTAGE = "major_outage"
    UNKNOWN = "unknown"


@dataclass
class ProviderStatus:
    provider: str
    status: ServiceHealth
    description: str
    last_checked: datetime
    incidents: list = field(default_factory=list)
    status_page_url: str = ""
    error: str = None


client = httpx.Client(timeout=15.0, follow_redirects=True)


# --- statuspage.io providers (OpenAI, Anthropic) ---

def _fetch_statuspage(api_url, provider_name, status_page_url):
    """Generic handler for statuspage.io providers."""
    try:
        resp = client.get(api_url)
        data = resp.json()
        indicator = data.get("status", {}).get("indicator", "none")
        description = data.get("status", {}).get("description", "Unknown")

        status_map = {
            "none": ServiceHealth.OPERATIONAL,
            "minor": ServiceHealth.DEGRADED,
            "major": ServiceHealth.PARTIAL_OUTAGE,
            "critical": ServiceHealth.MAJOR_OUTAGE,
        }
        health = status_map.get(indicator, ServiceHealth.UNKNOWN)

        # Fetch unresolved incidents
        incidents = []
        try:
            inc_url = api_url.replace("status.json", "incidents/unresolved.json")
            inc_resp = client.get(inc_url)
            inc_data = inc_resp.json()
            for inc in inc_data.get("incidents", []):
                incidents.append({
                    "title": inc.get("name", ""),
                    "status": inc.get("status", ""),
                    "created_at": inc.get("created_at", ""),
                    "url": inc.get("shortlink", ""),
                })
        except Exception:
            pass

        return ProviderStatus(
            provider=provider_name,
            status=health,
            description=description,
            last_checked=datetime.utcnow(),
            incidents=incidents,
            status_page_url=status_page_url,
        )
    except Exception as e:
        return ProviderStatus(
            provider=provider_name,
            status=ServiceHealth.UNKNOWN,
            description="Failed to fetch status",
            last_checked=datetime.utcnow(),
            status_page_url=status_page_url,
            error=str(e),
        )


def fetch_openai_status():
    return _fetch_statuspage(
        "https://status.openai.com/api/v2/status.json",
        "OpenAI",
        "https://status.openai.com",
    )


def fetch_anthropic_status():
    return _fetch_statuspage(
        "https://status.anthropic.com/api/v2/status.json",
        "Anthropic (Claude)",
        "https://status.anthropic.com",
    )


# --- AWS Bedrock (RSS feed) ---

def fetch_aws_bedrock_status():
    """Parse AWS Bedrock RSS feed for outage info."""
    try:
        feed = feedparser.parse(
            "https://status.aws.amazon.com/rss/bedrock-us-east-1.rss"
        )
        incidents = []
        has_active_issue = False

        for entry in feed.entries[:10]:
            title = entry.get("title", "")
            summary = entry.get("summary", "")
            published = entry.get("published", "")
            link = entry.get("link", "")

            incidents.append({
                "title": title,
                "status": "reported",
                "created_at": published,
                "url": link,
            })

            if "operating normally" not in summary.lower():
                has_active_issue = True

        status = ServiceHealth.DEGRADED if has_active_issue else ServiceHealth.OPERATIONAL
        description = "Active incidents detected" if has_active_issue else "All Systems Operational"

        return ProviderStatus(
            provider="AWS Bedrock",
            status=status,
            description=description,
            last_checked=datetime.utcnow(),
            incidents=incidents,
            status_page_url="https://health.aws.amazon.com/health/status",
        )
    except Exception as e:
        return ProviderStatus(
            provider="AWS Bedrock",
            status=ServiceHealth.UNKNOWN,
            description="Failed to fetch status",
            last_checked=datetime.utcnow(),
            status_page_url="https://health.aws.amazon.com/health/status",
            error=str(e),
        )


# --- Azure AI (RSS feed) ---

def fetch_azure_ai_status():
    """Fetch Azure AI status from Azure status RSS feed."""
    try:
        resp = client.get("https://azure.status.microsoft/en-us/status/feed")
        feed = feedparser.parse(resp.text)
        incidents = []
        has_active = False

        for entry in feed.entries[:10]:
            title = entry.get("title", "")
            summary = entry.get("summary", "")
            incidents.append({
                "title": title,
                "status": "reported",
                "created_at": entry.get("published", ""),
                "url": entry.get("link", ""),
            })
            if "resolved" not in summary.lower():
                has_active = True

        status = ServiceHealth.DEGRADED if has_active else ServiceHealth.OPERATIONAL
        description = "Active incidents detected" if has_active else "All Systems Operational"

        return ProviderStatus(
            provider="Azure AI",
            status=status,
            description=description,
            last_checked=datetime.utcnow(),
            incidents=incidents,
            status_page_url="https://azure.status.microsoft/en-us/status",
        )
    except Exception as e:
        return ProviderStatus(
            provider="Azure AI",
            status=ServiceHealth.UNKNOWN,
            description="Failed to fetch status",
            last_checked=datetime.utcnow(),
            status_page_url="https://azure.status.microsoft/en-us/status",
            error=str(e),
        )


# --- GCP Vertex AI (JSON endpoint) ---

def fetch_gcp_vertex_status():
    """Fetch GCP Vertex AI status from Google Cloud incidents JSON."""
    try:
        resp = client.get("https://status.cloud.google.com/incidents.json")
        data = resp.json()

        ai_keywords = ["vertex", "ai platform", "machine learning", "ml", "gemini"]
        incidents = []
        has_active = False

        for inc in data[:20]:
            service = inc.get("service_name", "").lower()
            if any(kw in service for kw in ai_keywords):
                is_resolved = inc.get("end", "") != ""
                incidents.append({
                    "title": inc.get("external_desc", ""),
                    "status": "resolved" if is_resolved else "active",
                    "created_at": inc.get("begin", ""),
                    "url": f"https://status.cloud.google.com/incidents/{inc.get('number', '')}",
                })
                if not is_resolved:
                    has_active = True

        status = ServiceHealth.DEGRADED if has_active else ServiceHealth.OPERATIONAL
        description = "Active incidents detected" if has_active else "All Systems Operational"

        return ProviderStatus(
            provider="GCP Vertex AI",
            status=status,
            description=description,
            last_checked=datetime.utcnow(),
            incidents=incidents,
            status_page_url="https://status.cloud.google.com",
        )
    except Exception as e:
        return ProviderStatus(
            provider="GCP Vertex AI",
            status=ServiceHealth.UNKNOWN,
            description="Failed to fetch status",
            last_checked=datetime.utcnow(),
            status_page_url="https://status.cloud.google.com",
            error=str(e),
        )


# --- Unified fetcher ---

def fetch_all_statuses():
    """Fetch status from all 5 AI cloud providers."""
    return [
        fetch_openai_status(),
        fetch_anthropic_status(),
        fetch_aws_bedrock_status(),
        fetch_azure_ai_status(),
        fetch_gcp_vertex_status(),
    ]
