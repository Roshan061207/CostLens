"""Team login, role-scoped files and ledger with a tamper-evident hash chain, access log, and operations health. Everything lives in Exasol.
Roles: member = sees only files they uploaded | lead = sees all files of their team, sets budgets | admin = sees every team.
Everyone can upload to their own team. Setup (no open sign-up):  python secure.py add NAME TEAM PASSWORD [member|lead|admin]  |  demo TEAM  |  seed
Set COSTLENS_SECRET to a long random string so sessions survive restarts. Serve over HTTPS in any real deployment."""
import os, re, sys, hmac, hashlib, time, base64, json, secrets, random, threading
from fastapi import APIRouter, HTTPException, Header, Depends
from pydantic import BaseModel
from db import connect

R, SECRET, _bad, ROLES = APIRouter(), (os.getenv("COSTLENS_SECRET") or secrets.token_hex(32)).encode(), {}, ("member", "lead", "admin")
LOCK, _t, _init = threading.Lock(), threading.local(), []
DEMO_PASSWORD = "CostLensDemo2026!"
DEMO_USERS = [
    ("finance-demo", "Finance"),
    ("marketing-demo", "Marketing"),
    ("ops-demo", "Ops"),
    ("product-demo", "Product"),
]
SCHEMA = ["CREATE SCHEMA IF NOT EXISTS COSTLENS",
 "CREATE TABLE IF NOT EXISTS COSTLENS.USERS (NAME VARCHAR(40), TEAM VARCHAR(40), SALT VARCHAR(32), PW VARCHAR(128), ROLE VARCHAR(10))",
 "CREATE TABLE IF NOT EXISTS COSTLENS.UPLOADS (ID DECIMAL(18,0) IDENTITY, TEAM VARCHAR(40), NAME VARCHAR(80), UPLOADED_BY VARCHAR(40), TS TIMESTAMP, ROWS_N DECIMAL(9,0), TOTAL DECIMAL(16,2))",
 "CREATE TABLE IF NOT EXISTS COSTLENS.LEDGER (ID DECIMAL(18,0) IDENTITY, TEAM VARCHAR(40), DT VARCHAR(10), CAT VARCHAR(40), DESCR VARCHAR(200), AMT DECIMAL(14,2), ENTERED_BY VARCHAR(40), PREV VARCHAR(64), HASH VARCHAR(64), UPLOAD_ID DECIMAL(18,0))",
 "CREATE TABLE IF NOT EXISTS COSTLENS.BUDGETS (TEAM VARCHAR(40), CAT VARCHAR(40), MONTHLY DECIMAL(14,2))",
 "CREATE TABLE IF NOT EXISTS COSTLENS.ACCESS_LOG (TS TIMESTAMP, NAME VARCHAR(40), TEAM VARCHAR(40), ACTIVITY VARCHAR(60))"]

def C():
    """One connection per thread (pyexasol connections are not thread-safe)."""
    if not hasattr(_t, "c"):
        _t.c = connect()
        with LOCK:
            if not _init:
                [_t.c.execute(x) for x in SCHEMA]
                try: _t.c.execute("ALTER TABLE COSTLENS.LEDGER DISTRIBUTE BY TEAM")  # co-locates a team's rows; helps on multi-node clusters
                except Exception: pass
                _init.append(1)
    return _t.c

def pw_hash(pw, salt): return hashlib.scrypt(pw.encode(), salt=salt.encode(), n=2**14, r=8, p=1).hex()
def sign(p): return hmac.new(SECRET, p.encode(), "sha256").hexdigest()
def mint(u, t, role):
    p = base64.urlsafe_b64encode(json.dumps({"u": u, "t": t, "r": role, "x": time.time() + 8 * 3600}).encode()).decode()
    return p + "." + sign(p)
def who(authorization: str = Header("")):
    try:
        p, s = authorization.replace("Bearer ", "").split(".")
        assert hmac.compare_digest(s, sign(p)); d = json.loads(base64.urlsafe_b64decode(p)); assert d["x"] > time.time(); return d
    except Exception: raise HTTPException(401, "Sign in again")
def note(me, a): C().execute("INSERT INTO COSTLENS.ACCESS_LOG VALUES (CURRENT_TIMESTAMP, {n}, {t}, {a})", {"n": me["u"], "t": me["t"], "a": a[:60]})
def scope(me, by):
    """Who may see which rows: admin all, lead their team, member only what they uploaded."""
    if me["r"] == "admin": return "1=1", {}
    if me["r"] == "lead": return "TEAM={t}", {"t": me["t"]}
    return f"TEAM={{t}} AND {by}={{u}}", {"t": me["t"], "u": me["u"]}

class Login(BaseModel): name: str; team: str; password: str
@R.post("/api/auth/login")
def login(b: Login):
    k = (b.name, b.team)
    if _bad.get(k, (0, 0))[0] >= 5 and time.time() < _bad[k][1]: raise HTTPException(429, "Too many attempts. Wait 5 minutes.")
    r = C().execute("SELECT SALT, PW, ROLE FROM COSTLENS.USERS WHERE NAME={n} AND TEAM={t}", {"n": b.name, "t": b.team}).fetchone()
    if not r or not hmac.compare_digest(pw_hash(b.password, r[0]), r[1]):
        _bad[k] = (_bad.get(k, (0, 0))[0] + 1, time.time() + 300); raise HTTPException(401, "Wrong name, team or password")
    _bad.pop(k, None); return {"token": mint(b.name, b.team, r[2]), "name": b.name, "team": b.team, "role": r[2]}

def digest(prev, team, dt, cat, d, amt, by): return hashlib.sha256("|".join([prev, team, dt, cat, d, f"{float(amt):.2f}", by]).encode()).hexdigest()
def put(c, team, user, rows, fname="Manual entry"):
    ok = []
    for x in rows:
        amt, cat, d = round(float(x["amount"]), 2), x["category"].strip().title()[:40], x.get("description", "")[:200]
        if not (0 < amt < 1e9) or not cat or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", x["date"]): raise HTTPException(400, f"Bad row: {d[:30] or cat}")
        ok.append((x["date"], cat, d, amt))
    p = {"t": team, "u": user}
    c.execute("INSERT INTO COSTLENS.UPLOADS (TEAM,NAME,UPLOADED_BY,TS,ROWS_N,TOTAL) VALUES ({t},{n},{u},CURRENT_TIMESTAMP,{r},{s})", {**p, "n": fname[:80], "r": len(ok), "s": round(sum(o[3] for o in ok), 2)})
    uid = int(c.execute("SELECT MAX(ID) FROM COSTLENS.UPLOADS WHERE TEAM={t} AND UPLOADED_BY={u}", p).fetchval())
    r = c.execute("SELECT HASH FROM COSTLENS.LEDGER WHERE TEAM={t} ORDER BY ID DESC LIMIT 1", p).fetchone(); prev = r[0] if r else "GENESIS"
    for dt, cat, d, amt in ok:
        h = digest(prev, team, dt, cat, d, amt, user)
        c.execute("INSERT INTO COSTLENS.LEDGER (TEAM,DT,CAT,DESCR,AMT,ENTERED_BY,PREV,HASH,UPLOAD_ID) VALUES ({t},{dt},{k},{d},{a},{u},{p},{h},{i})",
                  {**p, "dt": dt, "k": cat, "d": d, "a": amt, "p": prev, "h": h, "i": uid}); prev = h

class Row(BaseModel): date: str; category: str; description: str = ""; amount: float
class Rows(BaseModel): rows: list[Row]; file_name: str = "Manual entry"
@R.post("/api/ledger")
def add(b: Rows, me: dict = Depends(who)):
    if not 0 < len(b.rows) <= 500: raise HTTPException(400, "Send 1 to 500 rows")
    with LOCK: put(C(), me["t"], me["u"], [x.dict() for x in b.rows], b.file_name)  # lock keeps the hash chain in order
    note(me, f"add {len(b.rows)} rows"); return {"added": len(b.rows)}

def Q(sql, p): return [[str(r[0]), float(r[1])] for r in C().execute(sql, p).fetchall()]
@R.get("/api/ledger/summary")
def summary(me: dict = Depends(who)):
    w, p = scope(me, "ENTERED_BY"); note(me, "view summary"); L = f"FROM COSTLENS.LEDGER WHERE {w}"
    d = {"cats": Q(f"SELECT CAT, SUM(AMT) {L} GROUP BY CAT ORDER BY 2 DESC", p), "months": Q(f"SELECT SUBSTR(DT,1,7), SUM(AMT) {L} GROUP BY 1 ORDER BY 1", p),
         "thismonth": Q(f"SELECT CAT, SUM(AMT) {L} AND SUBSTR(DT,1,7)=TO_CHAR(CURRENT_DATE,'YYYY-MM') GROUP BY CAT", p), "budgets": [], "teams": None}
    if me["r"] != "member":  # budgets belong to teams, so members (who see only their own uploads) get none
        d["budgets"] = Q("SELECT CAT, SUM(MONTHLY) FROM COSTLENS.BUDGETS WHERE " + ("1=1" if me["r"] == "admin" else "TEAM={t}") + " GROUP BY CAT", {} if me["r"] == "admin" else {"t": me["t"]})
    d["catmonths"] = [[r[0], r[1], float(r[2])] for r in C().execute(f"SELECT CAT, SUBSTR(DT,1,7), SUM(AMT) {L} GROUP BY CAT, SUBSTR(DT,1,7) ORDER BY 1, 2", p).fetchall()]
    if me["r"] == "admin": d["teams"] = Q("SELECT TEAM, SUM(AMT) FROM COSTLENS.LEDGER GROUP BY TEAM ORDER BY 2 DESC", {})
    return d

@R.get("/api/files")
def files(me: dict = Depends(who)):
    w, p = scope(me, "UPLOADED_BY"); note(me, "list files")
    rows = C().execute(f"SELECT ID, TEAM, NAME, UPLOADED_BY, TO_CHAR(TS,'YYYY-MM-DD HH24:MI'), ROWS_N, TOTAL FROM COSTLENS.UPLOADS WHERE {w} ORDER BY ID DESC LIMIT 50", p).fetchall()
    return {"files": [{"id": int(a), "team": b, "name": n, "by": u, "ts": t, "rows": int(r), "total": float(s)} for a, b, n, u, t, r, s in rows]}

@R.get("/api/files/{fid}")
def one_file(fid: int, me: dict = Depends(who)):
    w, p = scope(me, "UPLOADED_BY"); f = C().execute(f"SELECT NAME FROM COSTLENS.UPLOADS WHERE ID={{i}} AND {w}", {**p, "i": fid}).fetchone()
    if not f: raise HTTPException(404, "File not found")  # same answer whether it does not exist or you may not see it
    note(me, f"open file {fid}")
    rows = C().execute("SELECT DT, CAT, DESCR, AMT FROM COSTLENS.LEDGER WHERE UPLOAD_ID={i} ORDER BY ID", {"i": fid}).fetchall()
    return {"name": f[0], "rows": [{"date": a, "cat": b, "desc": c or "", "amt": float(d)} for a, b, c, d in rows]}

def chain(tm):
    prev, n = "GENESIS", 0
    for i, t, dt, k, d, a, u, pv, h in C().execute("SELECT ID,TEAM,DT,CAT,DESCR,AMT,ENTERED_BY,PREV,HASH FROM COSTLENS.LEDGER WHERE TEAM={t} ORDER BY ID", {"t": tm}).fetchall():
        if pv != prev or digest(prev, t, dt, k, d or "", a, u) != h: return {"ok": False, "rows": n, "broken_at": int(i), "team": tm}
        prev, n = h, n + 1
    return {"ok": True, "rows": n, "team": tm}
@R.get("/api/ledger/verify")
def verify(me: dict = Depends(who)):
    if me["r"] == "member": raise HTTPException(403, "Leads and admins only")
    note(me, "verify ledger"); teams = [r[0] for r in C().execute("SELECT DISTINCT TEAM FROM COSTLENS.LEDGER").fetchall()] if me["r"] == "admin" else [me["t"]]
    res = [chain(t) for t in teams]; bad = [r for r in res if not r["ok"]]
    return bad[0] if bad else {"ok": True, "rows": sum(r["rows"] for r in res)}

class Bud(BaseModel): category: str; monthly: float; team: str = ""
@R.post("/api/budget")
def budget(b: Bud, me: dict = Depends(who)):
    if me["r"] == "member": raise HTTPException(403, "Leads and admins only")
    p = {"t": b.team if me["r"] == "admin" and b.team else me["t"], "k": b.category.strip().title()[:40], "m": round(b.monthly, 2)}
    C().execute("DELETE FROM COSTLENS.BUDGETS WHERE TEAM={t} AND CAT={k}", p); C().execute("INSERT INTO COSTLENS.BUDGETS VALUES ({t},{k},{m})", p); note(me, "set budget " + p["k"]); return {"ok": True}

class Ask(BaseModel): question: str
@R.post("/api/ask")
def ask(b: Ask, me: dict = Depends(who)):
    """Grounded Q&A. Only category and month totals (never descriptions or files) are sent, and only if ANTHROPIC_API_KEY is set."""
    d = summary(me); facts = {k: d[k] for k in ("cats", "months", "thismonth", "budgets", "catmonths")}; note(me, "ask")
    fb = "Top categories: " + ", ".join(f"{k} Rs {v:,.0f}" for k, v in d["cats"][:3]) + ". Set ANTHROPIC_API_KEY on the server for free-form answers."
    if not os.getenv("ANTHROPIC_API_KEY"): return {"answer": fb, "llm": False}
    try:
        import anthropic
        r = anthropic.Anthropic().messages.create(model="claude-sonnet-5-5", max_tokens=300, messages=[{"role": "user", "content":
            "You are a finance analyst. Answer using ONLY these aggregated rupee figures; if they do not contain the answer, say so. Be brief.\nData: " + json.dumps(facts) + "\nQuestion: " + b.question[:300]}])
        return {"answer": r.content[0].text.strip(), "llm": True}
    except Exception: return {"answer": fb, "llm": False}

class Ev(BaseModel): action: str
@R.post("/api/log")
def log(b: Ev, me: dict = Depends(who)): note(me, "client: " + b.action); return {"ok": True}

@R.get("/api/ops")
def ops(me: dict = Depends(who)):
    c = C(); note(me, "view ops")
    f = c.execute("SELECT PIPELINE, COUNT(*), SUM(CASE WHEN ALERTED=0 THEN 1 ELSE 0 END), SUM(MINUTES) FROM COSTLENS.PIPELINE_RUNS WHERE STATUS='FAILED' GROUP BY PIPELINE ORDER BY 3 DESC, 2 DESC").fetchall()
    d = c.execute("SELECT DASHBOARD, OWNER, DAYS_BETWEEN(CURRENT_DATE, LAST_REFRESH), MISMATCH_PCT FROM COSTLENS.DASHBOARD_STATE ORDER BY 3 DESC").fetchall()
    q = c.execute("SELECT TITLE, TEAM, DAYS_BETWEEN(CURRENT_DATE, OPENED) FROM COSTLENS.REQUESTS WHERE STATUS='OPEN' ORDER BY 3 DESC").fetchall()
    return {"pipes": [{"p": a, "fails": int(b), "silent": int(s), "min": int(m)} for a, b, s, m in f],
            "dash": [{"d": a, "owner": o, "stale": int(s), "mismatch": float(m)} for a, o, s, m in d],
            "reqs": [{"t": a, "team": t, "age": int(g)} for a, t, g in q]}

def seed(c):
    """Synthetic operations data: nightly pipeline runs, dashboard freshness/consistency, and a request queue."""
    c.execute("""CREATE OR REPLACE TABLE COSTLENS.PIPELINE_RUNS AS SELECT 'pipe_' || TO_CHAR(MOD(i,6)) AS PIPELINE,
      ADD_DAYS(TIMESTAMP '2026-05-01 02:00:00', FLOOR(i/6)) AS RUN_TS, CASE WHEN MOD(i*17,23)=0 THEN 'FAILED' ELSE 'OK' END AS STATUS,
      20 + MOD(i*13,40) AS MINUTES, CASE WHEN MOD(i*17,23)=0 AND MOD(i,3)=0 THEN 1 ELSE 0 END AS ALERTED
      FROM (SELECT LEVEL AS i FROM DUAL CONNECT BY LEVEL <= 1080)""")
    c.execute("CREATE OR REPLACE TABLE COSTLENS.DASHBOARD_STATE (DASHBOARD VARCHAR(40), OWNER VARCHAR(30), LAST_REFRESH DATE, MISMATCH_PCT DECIMAL(5,1))")
    c.execute("INSERT INTO COSTLENS.DASHBOARD_STATE VALUES ('Exec KPIs','Finance',ADD_DAYS(CURRENT_DATE,-1),0.4),('Revenue','Finance',ADD_DAYS(CURRENT_DATE,-19),6.8),('Churn','Product',ADD_DAYS(CURRENT_DATE,-2),0.9),('Campaigns','Marketing',ADD_DAYS(CURRENT_DATE,-34),11.5),('Ops board','Ops',ADD_DAYS(CURRENT_DATE,-3),1.2)")
    c.execute("CREATE OR REPLACE TABLE COSTLENS.REQUESTS (TITLE VARCHAR(80), TEAM VARCHAR(30), OPENED DATE, STATUS VARCHAR(10))")
    c.execute("INSERT INTO COSTLENS.REQUESTS VALUES ('Churn by cohort','Product',ADD_DAYS(CURRENT_DATE,-27),'OPEN'),('Regional revenue split','Finance',ADD_DAYS(CURRENT_DATE,-16),'OPEN'),('Campaign ROI by channel','Marketing',ADD_DAYS(CURRENT_DATE,-9),'OPEN'),('Ticket backlog trend','Ops',ADD_DAYS(CURRENT_DATE,-4),'OPEN')")

def demo(c, team):
    random.seed(3); base = {"Salary": 900000, "Software": 120000, "Allowance": 60000, "Insurance": 70000, "Benefits": 50000, "Travel": 60000, "Food": 30000, "Maintenance": 25000, "Parking": 15000, "Rent": 200000, "Events": 20000}
    grow, rows = {"Software": .09, "Travel": .12, "Food": .05}, []
    for m in range(6):
        for k, b in base.items(): rows.append({"date": f"2026-{5 + m:02d}-{random.randint(1, 28):02d}", "category": k, "description": f"{k} (synthetic)", "amount": b * (1 + grow.get(k, .01)) ** m * random.uniform(.95, 1.05)})
    put(c, team, "demo", rows, "Synthetic demo data")
    for k, b in base.items(): c.execute("INSERT INTO COSTLENS.BUDGETS VALUES ({t},{k},{m})", {"t": team, "k": k, "m": round(b * 1.05)})

def demo_users(c):
    """Create or refresh the team-scoped sample accounts for local demonstrations."""
    for name, team in DEMO_USERS:
        salt = secrets.token_hex(8)
        password_hash = pw_hash(DEMO_PASSWORD, salt)
        params = {"n": name, "t": team, "s": salt, "h": password_hash}
        exists = c.execute(
            "SELECT COUNT(*) FROM COSTLENS.USERS WHERE NAME={n} AND TEAM={t}", params
        ).fetchval()
        if exists:
            c.execute(
                "UPDATE COSTLENS.USERS SET SALT={s}, PW={h}, ROLE='lead' WHERE NAME={n} AND TEAM={t}",
                params,
            )
        else:
            c.execute(
                "INSERT INTO COSTLENS.USERS VALUES ({n},{t},{s},{h},'lead')", params
            )
        print(f"{team}: {name} (lead)")

if __name__ == "__main__":
    c, a = C(), sys.argv[1:]
    if not a:
        raise SystemExit("Usage: python secure.py add|demo|seed|demo-users ...")
    if a[0] == "add":
        s = secrets.token_hex(8); c.execute("INSERT INTO COSTLENS.USERS VALUES ({n},{t},{s},{h},{r})", {"n": a[1], "t": a[2], "s": s, "h": pw_hash(a[3], s), "r": a[4] if len(a) > 4 and a[4] in ROLES else "member"}); print("user added")
    elif a[0] == "demo": demo(c, a[1]); print("synthetic ledger and budgets added for", a[1])
    elif a[0] == "seed": seed(c); print("operations data seeded")
    elif a[0] == "demo-users": demo_users(c)
