# this program is to connect with Microsoft docs as MCP client and fetch relevant details

from mcp.client.streamable_http import streamable_http_client
from mcp import ClientSession
import httpx

client = httpx.Client()

MSFT_MCP_URL = "https://learn.microsoft.com/api/mcp"

async def fetch_model_retirements():
    """Fetch the Azure model retirements via Microsoft Learn MCP Server."""
    url = "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/model-retirements"
    return await fetch_from_msft_mcp(url)


def fetch_model_pricing(region: str):
    """Fetch Azure OpenAI model pricing for a region, grouped by model, deployment type, and tier."""
    from utils.meter_parser import parse_meter, group_pricing, format_grouped_pricing_text

    items = fetch_pricing_as_list(region)

    # Enrich with parsed fields
    for item in items:
        parsed = parse_meter(item['Meter'], item.get('SkuName', ''), item['Product'])
        item.update(parsed)

    grouped = group_pricing(items)
    return format_grouped_pricing_text(grouped)

def fetch_available_regions():
    """Fetch all Azure regions that have OpenAI pricing data."""
    url = "https://prices.azure.com/api/retail/prices?$filter=contains(productName, 'OpenAI')&$top=100"
    regions = set()
    page_count = 0
    while url and page_count < 5:
        request = httpx.Request("GET", url)
        response = client.send(request, follow_redirects=True)
        data = response.json()
        for item in data.get('Items', []):
            region = item.get('armRegionName', '')
            if region:
                regions.add(region)
        url = data.get('NextPageLink')
        page_count += 1
    return sorted(regions)


def fetch_pricing_as_list(region: str):
    """Fetch Azure OpenAI pricing as a list of dicts."""
    url = f"https://prices.azure.com/api/retail/prices?$filter=contains(productName, 'OpenAI') and armRegionName eq '{region}'"

    items = []
    while url:
        request = httpx.Request("GET", url)
        response = client.send(request, follow_redirects=True)
        data = response.json()
        url = data.get('NextPageLink')
        items.extend(data.get('Items', []))

    # Sort by meterName and return structured data
    items.sort(key=lambda x: x.get('meterName', ''))

    results = []
    for item in items:
        results.append({
            'Meter': item.get('meterName', 'N/A'),
            'Price': item.get('retailPrice', 'N/A'),
            'Unit': item.get('unitOfMeasure', 'N/A'),
            'Product': item.get('productName', 'N/A'),
            'SkuName': item.get('skuName', ''),
        })
    return results


async def fetch_from_msft_mcp(url: str):
    """Reusable helper to fetch any doc from Microsoft MCP Server."""
    async with streamable_http_client(MSFT_MCP_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("microsoft_docs_fetch", {"url": url})
            return result.content[0].text