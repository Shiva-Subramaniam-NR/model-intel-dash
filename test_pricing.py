import httpx
import json

client = httpx.Client()

# Test 1: Get Azure OpenAI pricing for a specific region
region = "swedencentral"
url = f"https://prices.azure.com/api/retail/prices?$filter=contains(productName, 'OpenAI') and armRegionName eq '{region}'&$top=20"

request = httpx.Request("GET", url)
response = client.send(request, follow_redirects=True)
data = response.json()

print(f"Azure OpenAI pricing for region: {region}")
print(f"Total results: {data.get('Count', 0)}")
print()

for item in data.get("Items", [])[:20]:
    print(f"  {item.get('productName')} | {item.get('meterName')} | ${item.get('retailPrice')} | {item.get('unitOfMeasure')}")

client.close()
