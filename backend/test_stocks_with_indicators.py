"""Test script to verify stocks with indicators endpoint."""

import asyncio
import httpx

BASE_URL = "http://127.0.0.1:8000"


async def test_stocks_with_indicators():
    """Test the new /stocks/with-indicators endpoint."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Login first
        login_resp = await client.post(
            f"{BASE_URL}/api/v1/auth/login",
            json={"username": "admin", "password": "***REMOVED***"}
        )
        
        if login_resp.status_code != 200:
            print(f"[FAIL] Login failed: {login_resp.status_code}")
            return False
        
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Test the new endpoint
        print("\n=== Testing /stocks/with-indicators endpoint ===")
        resp = await client.get(
            f"{BASE_URL}/api/v1/stocks/with-indicators",
            headers=headers,
            params={"limit": 10}
        )
        
        if resp.status_code != 200:
            print(f"[FAIL] Request failed: {resp.status_code}")
            print(f"Response: {resp.text}")
            return False
        
        stocks = resp.json()
        print(f"[PASS] Fetched {len(stocks)} stocks with indicators")
        
        # Check if indicators are present
        if stocks:
            sample = stocks[0]
            print(f"\nSample stock: {sample['code']} - {sample['name']}")
            print(f"  Basic info:")
            print(f"    code: {sample['code']}")
            print(f"    name: {sample['name']}")
            print(f"    market: {sample['market']}")
            print(f"    industry: {sample.get('industry')}")
            print(f"    sector: {sample.get('sector')}")
            print(f"    is_active: {sample['is_active']}")
            print(f"  Financial indicators:")
            print(f"    pe_ratio: {sample.get('pe_ratio')}")
            print(f"    pb_ratio: {sample.get('pb_ratio')}")
            print(f"    market_cap: {sample.get('market_cap')}")
            print(f"    is_profitable: {sample.get('is_profitable')}")
            
            # Count how many stocks have indicators
            with_pe = sum(1 for s in stocks if s.get('pe_ratio') is not None)
            with_pb = sum(1 for s in stocks if s.get('pb_ratio') is not None)
            with_mc = sum(1 for s in stocks if s.get('market_cap') is not None)
            
            print(f"\n[INFO] Stocks with indicators (out of {len(stocks)}):")
            print(f"  pe_ratio: {with_pe}")
            print(f"  pb_ratio: {with_pb}")
            print(f"  market_cap: {with_mc}")
            
            return True
        else:
            print("[WARN] No stocks returned")
            return False


if __name__ == "__main__":
    result = asyncio.run(test_stocks_with_indicators())
    if result:
        print("\n[PASS] Test passed!")
    else:
        print("\n[FAIL] Test failed!")
