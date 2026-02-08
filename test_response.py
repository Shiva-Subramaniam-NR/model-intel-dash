import asyncio, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from providers.azure import fetch_model_retirements, fetch_model_availability

async def test():
    print("=== RETIREMENT DATA (first 3000 chars) ===")
    retirement = await fetch_model_retirements()
    with open("test_retirement_output.txt", "w", encoding="utf-8") as f:
        f.write(retirement)
    print(f"Length: {len(retirement)} chars. Saved to test_retirement_output.txt")

    print("\n=== AVAILABILITY DATA (first 3000 chars) ===")
    availability = await fetch_model_availability()
    with open("test_availability_output.txt", "w", encoding="utf-8") as f:
        f.write(availability)
    print(f"Length: {len(availability)} chars. Saved to test_availability_output.txt")

asyncio.run(test())
