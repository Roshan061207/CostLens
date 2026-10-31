import os, ssl, time, statistics, pyexasol

def connect():
    """Connect to Exasol Personal. Override with EXA_DSN / EXA_USER / EXA_PASSWORD."""
    return pyexasol.connect(
        dsn=os.getenv("EXA_DSN", "localhost:8563"),
        user=os.getenv("EXA_USER", "sys"),
        password=os.getenv("EXA_PASSWORD", "exasol"),
        encryption=True,
        websocket_sslopt={"cert_reqs": ssl.CERT_NONE},  # local self-signed cert
    )

def timed(conn, sql, runs=5):
    """Median wall time in seconds. Query cache is off so repeats are honest."""
    conn.execute("ALTER SESSION SET QUERY_CACHE = 'OFF'")
    ts = []
    for _ in range(runs):
        t = time.perf_counter()
        conn.execute(sql).fetchall()
        ts.append(time.perf_counter() - t)
    return statistics.median(ts)
