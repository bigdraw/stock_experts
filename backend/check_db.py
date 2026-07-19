"""Check database for stock 000001."""

import sqlite3

conn = sqlite3.connect('data/stock.db')
cursor = conn.cursor()

# Get column names
cursor.execute("PRAGMA table_info(financial_reports)")
columns = [row[1] for row in cursor.fetchall()]
print("Columns:", columns)

# Get data for stock 000001
cursor.execute("""
    SELECT stock_code, report_type, report_date, 
           price, open, high, low, settlement, change, change_pct,
           volume, amount, turnover_ratio,
           pe_ratio, pb_ratio, market_cap, circulating_market_cap,
           is_profitable
    FROM financial_reports 
    WHERE stock_code = '000001' 
    ORDER BY report_date DESC 
    LIMIT 3
""")

rows = cursor.fetchall()
print(f"\nFound {len(rows)} records for stock 000001:")
for row in rows:
    print("\nRecord:")
    print(f"  stock_code: {row[0]}")
    print(f"  report_type: {row[1]}")
    print(f"  report_date: {row[2]}")
    print(f"  price: {row[3]}")
    print(f"  open: {row[4]}")
    print(f"  high: {row[5]}")
    print(f"  low: {row[6]}")
    print(f"  settlement: {row[7]}")
    print(f"  change: {row[8]}")
    print(f"  change_pct: {row[9]}")
    print(f"  volume: {row[10]}")
    print(f"  amount: {row[11]}")
    print(f"  turnover_ratio: {row[12]}")
    print(f"  pe_ratio: {row[13]}")
    print(f"  pb_ratio: {row[14]}")
    print(f"  market_cap: {row[15]}")
    print(f"  circulating_market_cap: {row[16]}")
    print(f"  is_profitable: {row[17]}")

conn.close()
