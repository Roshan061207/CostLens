"""Offline tests (no Exasol needed): python test_secure.py"""
import sys, types, time
m = types.ModuleType("db"); m.connect = lambda: None; sys.modules["db"] = m
import secure as s

def test_token():
    t = s.mint("a", "Fin", "lead"); assert s.who("Bearer " + t)["t"] == "Fin"
    for bad in (t[:-2] + "xx", "", "Bearer junk"):
        try: s.who(bad); assert False
        except s.HTTPException: pass
def test_scope():
    assert s.scope({"r": "admin", "t": "F", "u": "x"}, "B")[0] == "1=1"
    assert s.scope({"r": "lead", "t": "F", "u": "x"}, "B")[0] == "TEAM={t}"
    w, p = s.scope({"r": "member", "t": "F", "u": "x"}, "B"); assert "B={u}" in w and p["u"] == "x"
class Fake:
    def __init__(s_, rows): s_.rows = rows
    def execute(s_, *a, **k): return s_
    def fetchall(s_): return s_.rows
def make(n=4):
    prev, rows = "GENESIS", []
    for i in range(n):
        h = s.digest(prev, "F", "2026-10-0%d" % (i + 1), "Rent", "x", 100 + i, "u"); rows.append((i + 1, "F", "2026-10-0%d" % (i + 1), "Rent", "x", 100 + i, "u", prev, h)); prev = h
    return rows
def test_chain():
    s.C = lambda: Fake(make()); assert s.chain("F")["ok"]
    r = make(); r[2] = r[2][:5] + (999,) + r[2][6:]          # edit an amount
    s.C = lambda: Fake(r); assert s.chain("F")["broken_at"] == 3
    r = make(); del r[1]                                       # delete a row
    s.C = lambda: Fake(r); assert not s.chain("F")["ok"]
if __name__ == "__main__":
    for f in (test_token, test_scope, test_chain): f(); print("PASS", f.__name__)
