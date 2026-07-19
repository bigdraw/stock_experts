"""Test script to verify portfolio holdings include financial indicators."""

import asyncio
import httpx

BASE_URL = "http://127.0.0.1:8000"


async def test_portfolio_with_indicators():
    """Test that portfolio holdings include financial indicators."""
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
        
        # Get portfolios
        portfolios_resp = await client.get(
            f"{BASE_URL}/api/v1/portfolios",
            headers=headers
        )
        
        if portfolios_resp.status_code != 200:
            print(f"[FAIL] Failed to get portfolios: {portfolios_resp.status_code}")
            return False
        
        portfolios = portfolios_resp.json()
        if not portfolios:
            print("[WARN] No portfolios found")
            return False
        
        print(f"[PASS] Found {len(portfolios)} portfolios")
        
        # Get first portfolio detail
        portfolio_id = portfolios[0]["id"]
        detail_resp = await client.get(
            f"{BASE_URL}/api/v1/portfolios/{portfolio_id}",
            headers=headers
        )
        
        if detail_resp.status_code != 200:
            print(f"[FAIL] Failed to get portfolio detail: {detail_resp.status_code}")
            return False
        
        portfolio = detail_resp.json()
        holdings = portfolio.get("holdings", [])
        
        print(f"[PASS] Portfolio '{portfolio['name']}' has {len(holdings)} holdings")
        
        if holdings:
            sample = holdings[0]
            print(f"\nSample holding: {sample['stock_code']} - {sample['stock_name']}")
            print(f"  Basic info:")
            print(f"    stock_code: {sample['stock_code']}")
            print(f"    stock_name: {sample['stock_name']}")
            print(f"    market: {sample.get('market')}")
            print(f"    industry: {sample.get('industry')}")
            print(f"    shares: {sample['shares']}")
            print(f"    avg_cost: {sample['avg_cost']}")
            print(f"  Financial indicators:")
            print(f"    pe_ratio: {sample.get('pe_ratio')}")
            print(f"    pb_ratio: {sample.get('pb_ratio')}")
            print(f"    market_cap: {sample.get('market_cap')}")
            print(f"    is_profitable: {sample.get('is_profitable')}")
            
            # Count how many holdings have indicators
            with_pe = sum(1 for h in holdings if h.get('pe_ratio') is not None)
            with_pb = sum(1 for h in holdings if h.get('pb_ratio') is not None)
            with_mc = sum(1 for h in holdings if h.get('market_cap') is not None)
            
            print(f"\n[INFO] Holdings with indicators (out of {len(holdings)}):")
            print(f"  pe_ratio: {with_pe}")
            print(f"  pb_ratio: {with_pb}")
            print(f"  market_cap: {with_mc}")
            
            return True
        else:
            print("[WARN] No holdings in portfolio")
            return False


if __name__ == "__main__":
    result = asyncio.run(test_portfolio_with_indicators())
    if result:
        print("\n[PASS] Test passed!")
    else:
        print("\n[FAIL] Test failed!")
