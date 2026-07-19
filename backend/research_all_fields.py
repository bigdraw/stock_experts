"""Research all available fields from akshare APIs."""

import os
import json

# Bypass proxy
for key in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
    if key in os.environ:
        del os.environ[key]
os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'

import akshare as ak
import pandas as pd

print("=" * 80)
print("1. Sina API - Market Data Fields")
print("=" * 80)

import requests
s = requests.Session()
s.trust_env = False

r = s.get(
    'https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData',
    params={
        'page': '1',
        'num': '1',
        'sort': 'symbol',
        'asc': '1',
        'node': 'hs_a',
        'symbol': '',
        '_s_r_a': 'page'
    },
    timeout=10
)

data = json.loads(r.text)
if data:
    print(f"\nTotal fields: {len(data[0])}")
    print("\nAll fields:")
    for i, (key, value) in enumerate(sorted(data[0].items()), 1):
        print(f"  {i:2d}. {key:25s} = {value}")

print("\n" + "=" * 80)
print("2. stock_financial_abstract_ths - Financial Summary Fields")
print("=" * 80)

try:
    df = ak.stock_financial_abstract_ths(symbol="000001", indicator="按报告期")
    print(f"\nTotal fields: {len(df.columns)}")
    print(f"Total rows: {len(df)}")
    print("\nAll columns:")
    for i, col in enumerate(df.columns, 1):
        sample_val = df[col].iloc[0] if len(df) > 0 else None
        print(f"  {i:2d}. {col}")
    
    print("\nSample data (latest report):")
    if len(df) > 0:
        for col in df.columns:
            print(f"  {col}: {df[col].iloc[0]}")
except Exception as e:
    print(f"Error: {e}")

print("\n" + "=" * 80)
print("3. stock_financial_benefit_ths - Income Statement Fields")
print("=" * 80)

try:
    df = ak.stock_financial_benefit_ths(symbol="000001", indicator="按报告期")
    print(f"\nTotal fields: {len(df.columns)}")
    print(f"Total rows: {len(df)}")
    print("\nAll columns:")
    for i, col in enumerate(df.columns, 1):
        print(f"  {i:2d}. {col}")
except Exception as e:
    print(f"Error: {e}")

print("\n" + "=" * 80)
print("4. stock_financial_debt_ths - Balance Sheet Fields")
print("=" * 80)

try:
    df = ak.stock_financial_debt_ths(symbol="000001", indicator="按报告期")
    print(f"\nTotal fields: {len(df.columns)}")
    print(f"Total rows: {len(df)}")
    print("\nAll columns:")
    for i, col in enumerate(df.columns, 1):
        print(f"  {i:2d}. {col}")
except Exception as e:
    print(f"Error: {e}")

print("\n" + "=" * 80)
print("5. stock_financial_cash_ths - Cash Flow Fields")
print("=" * 80)

try:
    df = ak.stock_financial_cash_ths(symbol="000001", indicator="按报告期")
    print(f"\nTotal fields: {len(df.columns)}")
    print(f"Total rows: {len(df)}")
    print("\nAll columns:")
    for i, col in enumerate(df.columns, 1):
        print(f"  {i:2d}. {col}")
except Exception as e:
    print(f"Error: {e}")
