"""Run after setup_data.py. Checks every analysis query on your Exasol."""
from db import connect
import analysis as A
c, ok = connect(), True
for n in ["MONTHLY", "REPEATS", "STARS", "TEAMS", "DASHBOARDS", "PEAK", "UNUSED", "HOURLY", "DAILY", "DAYTOP", "BEFORE"]:
    try: print(f"PASS {n}: {len(c.export_to_pandas(getattr(A, n)))} rows")
    except Exception as e: ok = False; print(f"FAIL {n}: {str(e)[:160]}")
print("All queries OK" if ok else "Send the FAIL lines to be fixed")
