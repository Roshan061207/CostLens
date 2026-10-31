"""Create the COSTLENS schema, a synthetic 6-month query log, and a real SALES table.
Usage: python setup_data.py [--rows 5000000]   (all data is synthetic)"""
import argparse, numpy as np, pandas as pd
from db import connect

HEAVY = "SELECT region, SUM(amount) FROM sales WHERE sale_date >= DATE '2026-0{m}-01' GROUP BY region"
STAR = "SELECT * FROM sales WHERE region = 'R{n}'"
NORMAL = ["SELECT product_id, COUNT(*) FROM orders WHERE customer_id = {n} GROUP BY product_id",
          "SELECT status, COUNT(*) FROM tickets WHERE team_id = {n} GROUP BY status",
          "SELECT name FROM customers WHERE id = {n}"]
TEAMS = ["Finance", "Marketing", "Ops", "Product"]
DASH = ["Revenue", "Churn", "Ops board", "Campaigns", "Exec KPIs"]

def make_log(seed=7, months=6):
    rng, rows = np.random.default_rng(seed), []
    for m in range(months):
        f = m / (months - 1)
        users = round(40 * 1.09 ** f)
        n = round(users * 300 * 1.03 ** f)          # usage: +9% users, +10% queries/user
        p_heavy, p_star = 0.04 + 0.016 * f, 0.03 + 0.01 * f   # waste creeps up -> cost/query rises
        kind = rng.choice(3, n, p=[p_heavy, p_star, 1 - p_heavy - p_star])
        day = rng.integers(0, 28, n); hour = rng.integers(8, 20, n)
        for k, d, h in zip(kind, day, hour):
            u = int(rng.integers(0, users)); dash = (["Exec KPIs", "Revenue"] if k == 0 else DASH)[int(rng.integers(0, 2 if k == 0 else 5))]; h = int(rng.integers(11, 15)) if k == 0 else h
            if k == 0: sql, rt, mb = HEAVY.format(m=int(rng.integers(1, 7))), rng.normal(9000, 1500), rng.normal(900, 100)
            elif k == 1: sql, rt, mb = STAR.format(n=int(rng.integers(0, 40))), rng.normal(3000, 600), rng.normal(400, 80)
            else: sql, rt, mb = NORMAL[int(rng.integers(0, 3))].format(n=int(rng.integers(1, 9999))), rng.lognormal(5.8, 0.5), rng.lognormal(1.5, 0.5)
            rows.append((pd.Timestamp(2026, 4 + m, 1 + int(d), int(h), int(rng.integers(0, 60))), f"u{u:03d}", TEAMS[u % 4], dash, sql, max(int(rt), 5), round(max(mb, 0.1), 2)))
    return pd.DataFrame(rows, columns=["TS", "USER_ID", "TEAM", "DASHBOARD", "SQL_TEXT", "RUNTIME_MS", "SCANNED_MB"])

def incident():
    """A runaway cross join on 12 Aug: the kind of spike the alerts should catch."""
    ts = pd.date_range("2026-08-12 14:00", periods=40, freq="3min")
    return pd.DataFrame({"TS": ts, "USER_ID": "u007", "TEAM": "Marketing", "DASHBOARD": "Campaigns",
        "SQL_TEXT": "SELECT * FROM sales a CROSS JOIN sales b WHERE a.region = b.region", "RUNTIME_MS": 120000, "SCANNED_MB": 5000.0})

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--rows", type=int, default=5_000_000)
    a = ap.parse_args(); c = connect()
    c.execute("CREATE SCHEMA IF NOT EXISTS COSTLENS")
    c.execute("CREATE OR REPLACE TABLE COSTLENS.QUERY_LOG (TS TIMESTAMP, USER_ID VARCHAR(20), TEAM VARCHAR(20), DASHBOARD VARCHAR(40), SQL_TEXT VARCHAR(500), RUNTIME_MS DECIMAL(18,0), SCANNED_MB DECIMAL(18,2))")
    df = pd.concat([make_log(), incident()], ignore_index=True); c.import_from_pandas(df, ("COSTLENS", "QUERY_LOG")); print(f"QUERY_LOG: {len(df):,} rows")
    c.execute(f"""CREATE OR REPLACE TABLE COSTLENS.SALES AS
        SELECT ADD_DAYS(DATE '2026-01-01', MOD(i, 270)) AS SALE_DATE, 'R' || TO_CHAR(MOD(i * 7, 40)) AS REGION,
               CAST(MOD(i * 31, 1000) / 10.0 AS DECIMAL(10,2)) AS AMOUNT
        FROM (SELECT LEVEL AS i FROM DUAL CONNECT BY LEVEL <= {a.rows})""")
    print(f"SALES: {a.rows:,} rows")
    c.execute("CREATE OR REPLACE TABLE COSTLENS.TABLE_CATALOG (TABLE_NAME VARCHAR(60), SIZE_MB DECIMAL(12,0))")
    c.execute("INSERT INTO COSTLENS.TABLE_CATALOG VALUES ('sales',900),('orders',600),('tickets',120),('customers',80),('tmp_export_2024',4200),('sales_backup_v1',3100),('old_campaign_data',1800),('staging_orders_old',2500),('scratch_test',700)")
    print("TABLE_CATALOG: 9 tables (synthetic; in production read EXA_ALL_TABLES)")
