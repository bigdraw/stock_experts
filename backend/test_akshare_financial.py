import os
import sys
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"
for k in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]:
    os.environ.pop(k, None)

sys.stdout.reconfigure(encoding="utf-8")

import akshare as ak
import traceback

print(f"akshare version: {ak.__version__}")

def test_api(name, func):
    print(f"\n{'='*80}")
    print(f"API: {name}")
    print(f"{'='*80}")
    try:
        df = func()
        print(f"Columns ({len(df.columns)}): {list(df.columns)}")
        print(f"Total rows: {len(df)}")
        print(f"\nFirst 3 rows:")
        print(df.head(3).to_string())
    except Exception as e:
        print(f"ERROR: {e}")
        traceback.print_exc()

# 1 - financial abstract THS
test_api(
    "ak.stock_financial_abstract_ths(symbol='000001', indicator='按报告期')",
    lambda: ak.stock_financial_abstract_ths(symbol="000001", indicator="按报告期"),
)

# 2 - financial analysis indicator
test_api(
    "ak.stock_financial_analysis_indicator(symbol='000001')",
    lambda: ak.stock_financial_analysis_indicator(symbol="000001"),
)

# 3 - try stock_a_lg_indicator (renamed in newer versions)
try:
    fn = getattr(ak, "stock_a_lg_indicator", None) or getattr(ak, "stock_a_indicator_lg", None)
    if fn:
        test_api(
            f"ak.{fn.__name__}(symbol='000001')",
            lambda: fn(symbol="000001"),
        )
    else:
        print("\nstock_a_lg_indicator / stock_a_indicator_lg: NOT FOUND")
except Exception as e:
    print(f"ERROR finding lg indicator: {e}")

# 4 - search for similar APIs
print(f"\n{'='*80}")
print("Searching akshare for 'financial' and 'indicator' related APIs...")
print(f"{'='*80}")
financial_apis = [attr for attr in dir(ak) if "financial" in attr.lower()]
indicator_apis = [attr for attr in dir(ak) if "indicator" in attr.lower() and "stock" in attr.lower()]
lg_apis = [attr for attr in dir(ak) if "lg" in attr.lower()]

print(f"\nFinancial APIs: {financial_apis}")
print(f"Indicator APIs: {indicator_apis}")
print(f"LG APIs: {lg_apis}")
