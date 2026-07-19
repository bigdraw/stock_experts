"""Inspect Sina API response to see all available fields and their units."""

import requests
import json
import os

# Bypass proxy
for key in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
    if key in os.environ:
        del os.environ[key]
os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'

s = requests.Session()
s.trust_env = False

r = s.get(
    'https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData',
    params={
        'page': '1',
        'num': '5',
        'sort': 'symbol',
        'asc': '1',
        'node': 'hs_a',
        'symbol': '',
        '_s_r_a': 'page'
    },
    timeout=10
)

data = json.loads(r.text)

print(f"Total stocks returned: {len(data)}")
print(f"\nFields in first stock ({data[0].get('name', 'unknown')}):")
print("=" * 60)

# Print all fields with their values
for key, value in sorted(data[0].items()):
    print(f"  {key:20s} = {value}")

print("\n\nAll 5 stocks:")
print("=" * 60)
for stock in data:
    print(f"\n{stock.get('code')} {stock.get('name')}:")
    print(f"  trade (price): {stock.get('trade')}")
    print(f"  mktcap: {stock.get('mktcap')}")
    print(f"  nmc: {stock.get('nmc')}")
    print(f"  per: {stock.get('per')}")
    print(f"  pb: {stock.get('pb')}")
    print(f"  volume: {stock.get('volume')}")
    print(f"  amount: {stock.get('amount')}")
    print(f"  turnoverratio: {stock.get('turnoverratio')}")
