from src.providers.azure import fetch_model_retirements, fetch_model_pricing

# Test 1: Model retirements
print("=== Testing fetch_model_retirements ===")
result = fetch_model_retirements()
print(result[:500])  # print first 500 chars

# Test 2: Model pricing
print("=== Testing fetch_model_pricing ===")
result = fetch_model_pricing("swedencentral")
print(result)
