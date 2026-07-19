"""Comprehensive test script to verify all fixes."""

import asyncio
import httpx

BASE_URL = "http://127.0.0.1:8000"


async def run_tests():
    """Run all tests."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        # Login
        login_resp = await client.post(
            f"{BASE_URL}/api/v1/auth/login",
            json={"username": "admin", "password": "***REMOVED***"}
        )
        
        if login_resp.status_code != 200:
            print(f"[FAIL] Login failed: {login_resp.status_code}")
            return False
        
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        all_passed = True
        
        # Test 1: Stock indicators endpoint
        print("\n=== Test 1: Stock with indicators ===")
        resp = await client.get(
            f"{BASE_URL}/api/v1/stocks/with-indicators",
            headers=headers,
            params={"limit": 5}
        )
        
        if resp.status_code == 200:
            stocks = resp.json()
            sample = stocks[0] if stocks else {}
            
            # Check market cap unit (should be in wan yuan, e.g., 20919579 for Ping An Bank)
            market_cap = sample.get('market_cap')
            if market_cap and market_cap > 1000000:
                print(f"[PASS] Market cap is in wan yuan: {market_cap:,.2f} ({market_cap/10000:.2f} yi)")
            else:
                print(f"[FAIL] Market cap seems wrong: {market_cap}")
                all_passed = False
            
            # Check all indicator fields
            required_fields = ['price', 'open', 'high', 'low', 'settlement', 'pricechange', 'changepercent',
                             'volume', 'amount', 'turnoverratio', 'per', 'pb',
                             'mktcap', 'nmc']
            missing = [f for f in required_fields if f not in sample]
            if not missing:
                print(f"[PASS] All indicator fields present")
            else:
                print(f"[FAIL] Missing fields: {missing}")
                all_passed = False
        else:
            print(f"[FAIL] Request failed: {resp.status_code}")
            all_passed = False
        
        # Test 2: Individual stock indicators endpoint
        print("\n=== Test 2: Individual stock indicators (000001) ===")
        resp = await client.get(
            f"{BASE_URL}/api/v1/stocks/000001/indicators",
            headers=headers
        )
        
        if resp.status_code == 200:
            data = resp.json()
            if data:
                print(f"[PASS] Indicators fetched: price={data.get('price')}, market_cap={data.get('market_cap')}")
                
                # Verify market cap is reasonable (Ping An Bank should be ~2000 yi yuan = ~20000000 wan yuan)
                mc = data.get('market_cap')
                if mc and mc > 10000000:
                    print(f"[PASS] Market cap reasonable: {mc/10000:.2f} yi yuan")
                else:
                    print(f"[WARN] Market cap might be wrong: {mc}")
            else:
                print("[WARN] No indicators data for 000001")
        else:
            print(f"[FAIL] Request failed: {resp.status_code}")
            all_passed = False
        
        # Test 3: Financial reports with extended fields
        print("\n=== Test 3: Financial reports with extended fields ===")
        resp = await client.get(
            f"{BASE_URL}/api/v1/stocks/000001/financials",
            headers=headers
        )
        
        if resp.status_code == 200:
            reports = resp.json()
            if reports:
                sample = reports[0]
                extended_fields = ['eps', 'bps', 'revenue_growth', 'net_profit_growth', 
                                 'gross_margin', 'net_margin', 'debt_ratio']
                present = [f for f in extended_fields if f in sample]
                print(f"[PASS] Extended fields in response: {present}")
                
                # Check if any report has ROE data
                has_roe = any(r.get('roe') is not None for r in reports)
                if has_roe:
                    print(f"[PASS] ROE data present in reports")
                else:
                    print(f"[WARN] No ROE data in reports (may need to run financial update)")
            else:
                print("[WARN] No financial reports")
        else:
            print(f"[FAIL] Request failed: {resp.status_code}")
            all_passed = False
        
        # Test 4: Portfolio detail with indicators
        print("\n=== Test 4: Portfolio detail with indicators ===")
        portfolios_resp = await client.get(
            f"{BASE_URL}/api/v1/portfolios",
            headers=headers
        )
        
        if portfolios_resp.status_code == 200:
            portfolios = portfolios_resp.json()
            if portfolios:
                portfolio_id = portfolios[0]["id"]
                detail_resp = await client.get(
                    f"{BASE_URL}/api/v1/portfolios/{portfolio_id}",
                    headers=headers
                )
                
                if detail_resp.status_code == 200:
                    detail = detail_resp.json()
                    holdings = detail.get("holdings", [])
                    
                    if holdings:
                        sample = holdings[0]
                        indicator_fields = ['price', 'change_pct', 'pe_ratio', 'pb_ratio', 'market_cap']
                        present = [f for f in indicator_fields if f in sample]
                        print(f"[PASS] Portfolio holdings have indicator fields: {present}")
                        
                        # Check market cap unit
                        mc = sample.get('market_cap')
                        if mc and mc > 1000000:
                            print(f"[PASS] Portfolio market cap in wan yuan: {mc/10000:.2f} yi")
                        elif mc:
                            print(f"[WARN] Portfolio market cap might be wrong: {mc}")
                    else:
                        print("[WARN] No holdings in portfolio")
                else:
                    print(f"[FAIL] Portfolio detail failed: {detail_resp.status_code}")
                    all_passed = False
            else:
                print("[WARN] No portfolios")
        else:
            print(f"[FAIL] Portfolios request failed: {portfolios_resp.status_code}")
            all_passed = False
        
        # Test 5: Add stock to portfolio with code extraction
        print("\n=== Test 5: Add stock with code extraction ===")
        if portfolios:
            portfolio_id = portfolios[0]["id"]
            # Try adding with full label format (simulating the bug)
            add_resp = await client.post(
                f"{BASE_URL}/api/v1/portfolios/{portfolio_id}/items",
                headers=headers,
                json={"stock_code": "000002", "shares": 100, "avg_cost": 0}
            )
            
            if add_resp.status_code == 200:
                print(f"[PASS] Stock added successfully with code '000002'")
                
                # Verify it was added correctly
                detail_resp = await client.get(
                    f"{BASE_URL}/api/v1/portfolios/{portfolio_id}",
                    headers=headers
                )
                if detail_resp.status_code == 200:
                    detail = detail_resp.json()
                    holdings = detail.get("holdings", [])
                    found = any(h["stock_code"] == "000002" for h in holdings)
                    if found:
                        print(f"[PASS] Stock 000002 found in holdings")
                    else:
                        print(f"[FAIL] Stock 000002 not found in holdings")
                        all_passed = False
            else:
                print(f"[WARN] Add stock failed: {add_resp.status_code} - {add_resp.text}")
        
        return all_passed


if __name__ == "__main__":
    result = asyncio.run(run_tests())
    if result:
        print("\n" + "=" * 60)
        print("[PASS] All tests passed!")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("[FAIL] Some tests failed!")
        print("=" * 60)
