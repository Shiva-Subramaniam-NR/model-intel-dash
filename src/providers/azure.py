# this program is to connect with Microsoft docs as MCP client and fetch relevant details

from mcp.client.streamable_http import streamable_http_client
from mcp import ClientSession
import httpx
from bs4 import BeautifulSoup as beautifulsoup

client = httpx.Client()

MSFT_MCP_URL = "https://learn.microsoft.com/api/mcp"

async def fetch_model_retirements():
    """Fetch the Azure model retirements via Microsoft Learn MCP Server."""
    url = "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/model-retirements"
    return await fetch_from_msft_mcp(url)


def fetch_model_pricing(region: str):
    """Fetch the Azure model pricing page from Microsoft Learn."""
    url = f"https://prices.azure.com/api/retail/prices?$filter=contains(productName, 'OpenAI') and armRegionName eq '{region}'&$top=100"
    
    #fetch all the items from the API response with pagination
    items = []
    while url:
        request = httpx.Request("GET", url)
        response = client.send(request, follow_redirects=True)
        data = response.json()
        url = data.get('NextPageLink')
        items.extend(data.get('Items', []))

    # Sort items by meterName
    items.sort(key=lambda x: x.get('meterName', ''))

    # Build output with header
    output = "Meter | Price | Unit | Product\n"
    output += "-" * 60 + "\n"

    for item in items:
        meter = item.get('meterName', 'N/A')
        price = item.get('retailPrice', 'N/A')
        unit = item.get('unitOfMeasure', 'N/A')
        product = item.get('productName', 'N/A')
        output += f"{meter} | ${price} | {unit} | {product}\n"

    return output

async def fetch_model_availability():
    """Fetch the Azure model availability page from Microsoft Learn."""
    url = "https://learn.microsoft.com/en-us/azure/ai-foundry/foundry-models/concepts/models-sold-directly-by-azure?view=foundry-classic&tabs=global-standard-aoai%2Cglobal-standard&pivots=azure-openai"
    return await fetch_from_msft_mcp(url)

async def fetch_whats_new():
    """Fetch the Azure OpenAI Service What's New page from Microsoft Learn."""
    url = "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/whats-new?view=foundry-classic"
    return await fetch_from_msft_mcp(url)

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
    """Fetch Azure OpenAI pricing as a list of dicts for Streamlit dataframes."""
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
        })
    return results


async def fetch_from_msft_mcp(url: str):
    """Reusable helper to fetch any doc from Microsoft MCP Server."""
    async with streamable_http_client(MSFT_MCP_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("microsoft_docs_fetch", {"url": url})
            return result.content[0].text