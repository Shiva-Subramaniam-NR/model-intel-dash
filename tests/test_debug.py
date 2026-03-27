"""
Test fetch_model_retirements and fetch_model_pricing from azure.py.
Run from project root: python tests/test_debug.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from providers.azure import fetch_model_retirements, fetch_model_pricing


async def test_retirements():
    print("=== Testing fetch_model_retirements ===")
    result = await fetch_model_retirements()
    print(f"Length: {len(result)} chars")
    print(result[:600])


def test_pricing():
    region = "swedencentral"
    print(f"\n=== Testing fetch_model_pricing ({region}) ===")
    result = fetch_model_pricing(region)
    # Print first 1200 chars (a few model groups)
    print(result[:1200])


async def main():
    await test_retirements()
    test_pricing()


if __name__ == "__main__":
    asyncio.run(main())
