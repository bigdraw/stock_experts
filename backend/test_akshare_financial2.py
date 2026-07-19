import os
import sys
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"
for k in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]:
    os.environ.pop(k, None)

sys.stdout.reconfigure(encoding="utf-8")

import akshare as ak
import traceback

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

# Try EM version of financial analysis indicator
test_api(
    "ak.stock_financial_analysis_indicator_em(symbol='000001')",
    lambda: ak.stock_financial_analysis_indicator_em(symbol="000001"),
)

# Try stock_a_gxl_lg (dividend yield + PE/PB maybe)
test_api(
    "ak.stock_a_gxl_lg(symbol='000001')",
    lambda: ak.stock_a_gxl_lg(symbol="000001"),
)

# Try stock_financial_abstract (non-THS)
test_api(
    "ak.stock_financial_abstract(symbol='000001')",
    lambda: ak.stock_financial_abstract(symbol="000001"),
)

# Try stock_financial_benefit_ths (income statement)
test_api(
    "ak.stock_financial_benefit_ths(symbol='000001', indicator='按报告期')",
    lambda: ak.stock_financial_benefit_ths(symbol="000001", indicator="按报告期"),
)
