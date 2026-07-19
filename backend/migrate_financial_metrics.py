"""Migration script to add extended financial metrics columns to financial_reports table."""

import sqlite3
import sys

def migrate():
    """Add new columns to financial_reports table."""
    db_path = "data/stock.db"
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get existing columns
    cursor.execute("PRAGMA table_info(financial_reports)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    
    # New columns to add
    new_columns = [
        ("eps", "REAL"),
        ("bps", "REAL"),
        ("revenue_growth", "REAL"),
        ("net_profit_growth", "REAL"),
        ("gross_margin", "REAL"),
        ("net_margin", "REAL"),
        ("debt_ratio", "REAL"),
    ]
    
    added = []
    for col_name, col_type in new_columns:
        if col_name not in existing_columns:
            cursor.execute(f"ALTER TABLE financial_reports ADD COLUMN {col_name} {col_type}")
            added.append(col_name)
            print(f"Added column: {col_name}")
    
    conn.commit()
    conn.close()
    
    if added:
        print(f"\nMigration complete: added {len(added)} columns")
    else:
        print("\nNo new columns to add - table already up to date")

if __name__ == "__main__":
    migrate()
