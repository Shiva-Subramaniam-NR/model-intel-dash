# this program is to connect with Microsoft docs as MCP client and fetch relevant details

import httpx
from bs4 import BeautifulSoup as beautifulsoup

client = httpx.Client()

def fetch_model_retirements():
    """Fetch the Azure model retirements page from Microsoft Learn."""
    url =  "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/model-retirements"
    soup = beautifulsoup(httpx.get(url, follow_redirects=True).text, 'html.parser')
    tables = soup.find_all('table')

    output = ""
    for table in tables:
        rows = table.find_all('tr')
        for row in rows:
            cells = row.find_all(['th', 'td'])
            cell_texts = [cell.get_text(strip=True) for cell in cells]
            output += "\t".join(cell_texts) + "\n"
    return output


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

def fetch_model_availability():
    """Fetch the Azure model availability page from Microsoft Learn."""
    url = f"https://learn.microsoft.com/en-us/azure/ai-foundry/foundry-models/concepts/models-sold-directly-by-azure?view=foundry-classic&tabs=global-standard-aoai%2Cglobal-standard&pivots=azure-openai"
    soup = beautifulsoup(httpx.get(url, follow_redirects=True).text, 'html.parser')
    tables = soup.find_all('table')

    output = ""
    for table in tables:
        rows = table.find_all('tr')
        for row in rows:
            cells = row.find_all(['th', 'td'])
            cell_texts = [cell.get_text(strip=True) for cell in cells]
            output += "\t".join(cell_texts) + "\n"
    return output

def fetch_whats_new():
    """Fetch the Azure OpenAI Service What's New page from Microsoft Learn."""
    url = "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/whats-new?view=foundry-classic"
    soup = beautifulsoup(httpx.get(url, follow_redirects=True).text, 'html.parser')
    headings = soup.find_all(['h2', 'h3'])

    output = ""
    for heading in headings:
        if heading.name == 'h2':
            output += f"\n=== {heading.get_text(strip=True)} ===\n"
        elif heading.name == 'h3':
            title = heading.get_text(strip=True)
            # find_next_sibling('p') gets the next <p> after this <h3>
            p_tag = heading.find_next_sibling('p')
            summary = p_tag.get_text(strip=True) if p_tag else "No summary available."
            output += f"\n- {title}\n  {summary}\n\n"
    return output
