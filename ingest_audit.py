"""Load YOUR real query history into COSTLENS.QUERY_LOG from Exasol's audit log (EXA_DBA_AUDIT_SQL).
Needs auditing enabled on the instance. Check column names on your version before running.
Optional team map: python ingest_audit.py teams.csv   (columns: USER_NAME,TEAM). Others become 'Unassigned'."""
import sys, pandas as pd
from db import connect
c = connect(); c.execute("CREATE SCHEMA IF NOT EXISTS COSTLENS")
c.execute("CREATE OR REPLACE TABLE COSTLENS.QUERY_LOG (TS TIMESTAMP, USER_ID VARCHAR(20), TEAM VARCHAR(20), DASHBOARD VARCHAR(40), SQL_TEXT VARCHAR(500), RUNTIME_MS DECIMAL(18,0), SCANNED_MB DECIMAL(18,2))")
c.execute("""INSERT INTO COSTLENS.QUERY_LOG
  SELECT START_TIME, SUBSTR(USER_NAME, 1, 20), 'Unassigned', 'Unknown', SUBSTR(SQL_TEXT, 1, 500), CAST(DURATION * 1000 AS DECIMAL(18,0)), 0
  FROM EXA_DBA_AUDIT_SQL WHERE SUCCESS = TRUE AND COMMAND_CLASS = 'DQL'""")  # DQL = SELECT statements
if len(sys.argv) > 1:
    for u, t in pd.read_csv(sys.argv[1]).itertuples(index=False):
        c.execute("UPDATE COSTLENS.QUERY_LOG SET TEAM = {t} WHERE USER_ID = {u}", {"t": t[:20], "u": u[:20]})
print("Loaded", c.execute("SELECT COUNT(*) FROM COSTLENS.QUERY_LOG").fetchval(), "queries. Scanned MB is 0 here: cost = runtime only.")
