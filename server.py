"""Backend for CostLens. Run: uvicorn server:app --port 8000, then open http://localhost:8000"""
import time, random, re
import numpy as np
from fastapi import FastAPI
from pydantic import BaseModel
from setup_data import HEAVY, STAR, NORMAL, TEAMS, DASH
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import analysis as A
from db import connect, timed
from explain import explain, ticket

app, _c = FastAPI(title="CostLens API"), []
from secure import R as _secure
app.include_router(_secure)
from fastapi import Request
from fastapi.responses import JSONResponse
from secure import who, ROLES, C as _conn
LEAD_ONLY, ADMIN_ONLY = {"/api/data", "/api/forecast", "/api/live", "/api/pattern", "/api/live/tick"}, {"/api/prove", "/api/scale"}
@app.middleware("http")
async def gate(request: Request, call_next):
    """Every platform endpoint needs a login. Only admins can run database fixes; leads can generate demo feed rows."""
    p = request.url.path
    if p in LEAD_ONLY | ADMIN_ONLY:
        try: me = who(request.headers.get("authorization", ""))
        except Exception: return JSONResponse({"detail": "Sign in at /org first"}, status_code=401)
        if ROLES.index(me["r"]) < ROLES.index("admin" if p in ADMIN_ONLY else "lead"): return JSONResponse({"detail": "Your role cannot do this"}, status_code=403)
    return await call_next(request)

def conn(): return _conn()  # one connection per thread

def hist(c):
    c.execute("CREATE TABLE IF NOT EXISTS COSTLENS.FIX_LOG (TS TIMESTAMP, FIX VARCHAR(80), BEFORE_MS DECIMAL(12,0), AFTER_MS DECIMAL(12,0))")
    d = c.export_to_pandas("SELECT TO_CHAR(TS, 'YYYY-MM-DD HH24:MI') AS TS, FIX, BEFORE_MS, AFTER_MS FROM COSTLENS.FIX_LOG ORDER BY TS DESC LIMIT 20")
    return [{"ts": x[0], "fix": x[1], "b": int(x[2]), "a": int(x[3])} for x in d.itertuples(index=False)]

def q(sql, name=None, meta=None):
    t = time.perf_counter(); d = conn().export_to_pandas(sql); d.columns = [x.upper() for x in d.columns]
    if meta is not None: meta.append({"name": name, "ms": round((time.perf_counter() - t) * 1000), "rows": len(d), "sql": " ".join(sql.split())})
    return d

@app.get("/api/data")
def data(rate: float = 0.5):
    meta = []
    m, rep, st, tm, ds, pk, un, hr = (q(s, n, meta) for n, s in (("Monthly cost", A.MONTHLY), ("Repeated queries", A.REPEATS), ("Wide scans", A.STARS), ("Cost by team", A.TEAMS), ("Cost by dashboard", A.DASHBOARDS), ("Peak-hour load", A.PEAK), ("Unused tables", A.UNUSED), ("Cost by hour", A.HOURLY)))
    dy, dt = q(A.DAILY, "Daily cost", meta), q(A.DAYTOP, "Top query per day", meta)
    r, p = rep.iloc[0], pk.iloc[0]
    facts = {"kind": "repeated heavy query", "pattern": r.PATTERN, "runs": int(r.RUNS), "users": int(r.USERS),
             "cost_rupees": round(float(r.UNITS) * rate), "fix": "serve it from a pre-aggregated summary table"}
    return {"months": [{"m": x.PERIOD, "u": int(x.USERS), "n": int(x.QUERIES), "c": float(x.UNITS)} for x in m.itertuples()],
            "teams": [[x.TEAM, float(x.UNITS)] for x in tm.itertuples()],
            "dash": [[x.DASHBOARD, float(x.UNITS)] for x in ds.itertuples()],
            "top": {"pattern": r.PATTERN, "runs": int(r.RUNS), "users": int(r.USERS), "units": float(r.UNITS)},
            "stars": {"runs": int(st.RUNS[0]), "units": float(st.UNITS[0])},
            "peak": {"runs": int(p.RUNS), "units": float(p.UNITS), "peak_units": float(p.PEAK_UNITS)},
            "hours": [[int(x.HR), float(x.UNITS)] for x in hr.itertuples()],
            "unused": [[x.TABLE_NAME, int(x.SIZE_MB)] for x in un.itertuples()],
            "meta": meta, "daily": [[x.D, float(x.UNITS)] for x in dy.itertuples()],
            "daytop": {x.D: [x.PATTERN, float(x.UNITS)] for x in dt.itertuples()}, "history": hist(conn()), "text": explain(facts), "ticket": ticket(facts)}

@app.post("/api/prove")
def prove():
    c = conn(); b = timed(c, A.BEFORE); c.execute(A.FIX); a = timed(c, A.AFTER)
    hist(c); c.execute(f"INSERT INTO COSTLENS.FIX_LOG VALUES (CURRENT_TIMESTAMP, 'Summary table for repeated query', {round(b * 1000)}, {round(a * 1000)})")
    return {"b": round(b * 1000), "a": round(a * 1000), "history": hist(c)}

@app.post("/api/scale")
def scale(factor: int = 10):
    factor = max(1, min(int(factor), 100)); c = conn()
    c.execute(f"CREATE OR REPLACE TABLE COSTLENS.QUERY_LOG_X AS SELECT l.* FROM COSTLENS.QUERY_LOG l CROSS JOIN (SELECT LEVEL AS K FROM DUAL CONNECT BY LEVEL <= {factor}) k")
    rows = c.execute("SELECT COUNT(*) FROM COSTLENS.QUERY_LOG_X").fetchval()
    t = time.perf_counter(); c.export_to_pandas(A.REPEATS.replace("COSTLENS.QUERY_LOG", "COSTLENS.QUERY_LOG_X"))
    return {"rows": int(rows), "ms": round((time.perf_counter() - t) * 1000)}

def live_table(c):
    c.execute("CREATE TABLE IF NOT EXISTS COSTLENS.QUERY_LIVE (TS TIMESTAMP, USER_ID VARCHAR(20), TEAM VARCHAR(20), DASHBOARD VARCHAR(40), SQL_TEXT VARCHAR(500), RUNTIME_MS DECIMAL(18,0), SCANNED_MB DECIMAL(18,2))")

@app.post("/api/live/tick")
def tick(n: int = 4):
    """Demo workload: writes new queries into Exasol as they 'arrive'. In production, read Exasol's audit log instead."""
    c = conn(); live_table(c); vals = []
    for _ in range(max(1, min(n, 20))):
        k = random.choices([0, 1, 2], [.08, .05, .87])[0]
        if k == 0: sql, rt, mb = HEAVY.format(m=random.randint(1, 6)), random.gauss(9000, 1500), random.gauss(900, 100)
        elif k == 1: sql, rt, mb = STAR.format(n=random.randint(0, 39)), random.gauss(3000, 600), random.gauss(400, 80)
        else: sql, rt, mb = random.choice(NORMAL).format(n=random.randint(1, 9999)), random.lognormvariate(5.8, .5), random.lognormvariate(1.5, .5)
        u = random.randint(0, 45)
        vals.append("(CURRENT_TIMESTAMP, 'u%03d', '%s', '%s', '%s', %d, %.2f)" % (u, TEAMS[u % 4], random.choice(DASH), sql.replace("'", "''"), max(int(rt), 5), max(mb, .1)))
    c.execute("INSERT INTO COSTLENS.QUERY_LIVE VALUES " + ",".join(vals)); return {"ok": True}

@app.get("/api/live")
def live():
    c = conn(); live_table(c)
    r = q(f"SELECT TO_CHAR(TS, 'HH24:MI:SS') AS TM, TEAM, SQL_TEXT, {A.COST} AS UNITS FROM COSTLENS.QUERY_LIVE ORDER BY TS DESC LIMIT 12")
    t = q(f"SELECT COUNT(*) AS N, COALESCE(SUM({A.COST}), 0) AS UNITS FROM COSTLENS.QUERY_LIVE").iloc[0]
    return {"recent": [{"t": x.TM, "team": x.TEAM, "sql": x.SQL_TEXT, "u": float(x.UNITS)} for x in r.itertuples()], "n": int(t.N), "units": float(t.UNITS)}

class P(BaseModel):
    sql: str

@app.post("/api/pattern")
def pattern(p: P):
    """Pre-flight: the pasted SQL is NEVER executed. Only its normalized shape is looked up in the history."""
    pat = re.sub(r"[0-9]+", "?", re.sub(r"'[^']*'", "?", " ".join(p.sql.split()))).replace("'", "''")
    r = q(f"SELECT COUNT(*) AS RUNS, AVG({A.COST}) AS AU, AVG(RUNTIME_MS) AS MS FROM COSTLENS.QUERY_LOG WHERE {A.PATTERN} = '{pat}'").iloc[0]
    return {"runs": int(r.RUNS), "avg_units": float(r.AU or 0), "avg_ms": float(r.MS or 0)}

@app.get("/api/forecast")
def forecast():
    """Linear trend per team over the last 4 months (Exasol does the aggregation, numpy only fits the line)."""
    tm, inc, mo = q(A.TEAMMONTH), q(A.INCIDENTS).iloc[0], q(A.MONTHLY)
    ms = list(mo.PERIOD); y, mth = map(int, ms[-1].split("-"))
    nxt = [f"{y + (mth + k - 1) // 12}-{(mth + k - 1) % 12 + 1:02d}" for k in (1, 2, 3)]
    teams = []
    for t, g in tm.groupby("TEAM"):
        v = [float(x) for x in g.UNITS][-4:]; sl, ic = np.polyfit(range(len(v)), v, 1)
        teams.append({"team": t, "hist": v, "proj": [max(0.0, float(ic + sl * (len(v) - 1 + k))) for k in (1, 2, 3)]})
    us = q(A.userrisk(ms[-1], ms[-2]))
    return {"next": nxt, "teams": teams, "incident": {"runs": int(inc.RUNS), "units": float(inc.UNITS)},
            "users": [{"id": x.USER_ID, "team": x.TEAM, "last": float(x.LAST_U), "prev": float(x.PREV_U)} for x in us.itertuples()]}

app.mount("/static", StaticFiles(directory="static"), name="static")  # local OCR engine and chart libraries, so nothing loads from a CDN

@app.get("/org")
def org(): return FileResponse("static/org.html")

@app.get("/")
def index(): return FileResponse("static/landing.html")

@app.get("/platform")
def platform(): return FileResponse("static/index.html")
