import pandas as pd, plotly.graph_objects as go, streamlit as st
import analysis as A
from db import connect, timed
from explain import explain, ticket

st.set_page_config(page_title="CostLens", page_icon="◐", layout="wide")
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Sora:wght@500;700&family=IBM+Plex+Sans:wght@400;500&display=swap');
:root{--ink:#12202B;--mute:#5B6B78;--line:#D9E0E6;--teal:#0F766E;--amber:#B45309;--paper:#F3F5F7}
html,body,[class*=st-]{font-family:'IBM Plex Sans',sans-serif;color:var(--ink)}
.stApp{background:var(--paper)} #MainMenu,footer,header{visibility:hidden}
.block-container{max-width:1100px;padding-top:2.2rem}
h1,h2,h3{font-family:'Sora',sans-serif;letter-spacing:-.02em}
.hero{font-family:'Sora';font-size:2.5rem;font-weight:700;line-height:1.15;max-width:760px;margin:0 0 .4rem}
.sub{color:var(--mute);font-size:1.05rem;max-width:640px;margin-bottom:1.6rem}
.eq{display:flex;flex-wrap:wrap;align-items:flex-end;gap:.9rem;margin:.4rem 0 1.4rem}
.eq .f{border-bottom:3px solid var(--line);padding-bottom:.35rem}
.eq .f.hot{border-color:var(--amber)} .eq .n{font-family:'Sora';font-size:2.6rem;font-weight:700;line-height:1}
.eq .l{color:var(--mute);font-size:.9rem;margin-top:.3rem} .eq .op{font-size:1.8rem;color:var(--mute);padding-bottom:1.1rem}
.eq .tot .n{color:var(--amber)}
.find{background:#fff;border:1px solid var(--line);border-left:4px solid var(--teal);border-radius:6px;padding:1rem 1.2rem;margin-bottom:.8rem}
.find code{font-size:.82rem;color:var(--ink);background:var(--paper);padding:.15rem .4rem;border-radius:4px;word-break:break-all}
.find .meta{color:var(--mute);font-size:.9rem;margin-top:.4rem}
.stTabs [data-baseweb=tab]{font-family:'Sora';font-weight:500}
.stButton>button{background:var(--teal);color:#fff;border:0;border-radius:6px;padding:.6rem 1.2rem;font-weight:500}
.stButton>button:hover{background:#0B5F58;color:#fff} .stButton>button:focus-visible{outline:3px solid var(--amber)}
</style>""", unsafe_allow_html=True)

rate = st.sidebar.number_input("Rate card (₹ per cost unit)", 0.01, 100.0, 0.50, 0.05,
    help="Cost unit = runtime seconds + scanned MB / 100. This is a model, not your invoice.")

@st.cache_resource
def conn(): return connect()

try:
    c = conn(); m = c.export_to_pandas(A.MONTHLY); m.columns = [x.upper() for x in m.columns]
except Exception as e:
    st.error("CostLens can't reach Exasol. Start Exasol Personal, set EXA_DSN / EXA_USER / EXA_PASSWORD, "
             "then run `python setup_data.py`.")
    st.caption(str(e)[:200]); st.stop()

u, q, cpq, tot = A.decompose(m)
st.markdown(f"<div class='hero'>Your bill grew {tot-1:.0%}. Usage grew {u*q-1:.0%}.</div>"
            "<div class='sub'>CostLens reads the query history in Exasol, shows what drove the gap, "
            "and proves each fix with a measured result.</div>", unsafe_allow_html=True)

t1, tw, t2, t3 = st.tabs(["Why it grew", "Who spends", "What to fix", "Prove it"])

with t1:
    st.markdown(f"""<div class='eq'>
      <div class='f'><div class='n'>{u:.2f}</div><div class='l'>active users</div></div><div class='op'>×</div>
      <div class='f'><div class='n'>{q:.2f}</div><div class='l'>queries per user</div></div><div class='op'>×</div>
      <div class='f hot'><div class='n'>{cpq:.2f}</div><div class='l'>cost per query</div></div><div class='op'>=</div>
      <div class='f tot'><div class='n'>{tot:.2f}</div><div class='l'>total cost, first vs last month</div></div></div>""", unsafe_allow_html=True)
    idx = lambda s: s / s.iloc[0] * 100
    fig = go.Figure()
    fig.add_scatter(x=m.PERIOD, y=idx(m.USERS * m.QUERIES / m.USERS), name="Queries (usage)", line=dict(color="#5B6B78", width=2))
    fig.add_scatter(x=m.PERIOD, y=idx(m.UNITS), name="Cost", line=dict(color="#B45309", width=3), fill="tonexty", fillcolor="rgba(180,83,9,.12)")
    fig.update_layout(height=340, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      yaxis_title="Index (first month = 100)", legend=dict(orientation="h", y=1.12), font=dict(family="IBM Plex Sans"))
    fig.update_yaxes(gridcolor="#D9E0E6"); st.plotly_chart(fig, use_container_width=True)
    st.caption(f"The shaded gap is cost growth that usage doesn't explain. Cost per query rose {cpq-1:.0%}, so the waste is in how queries run, not how many.")

rep = c.export_to_pandas(A.REPEATS); rep.columns = [x.upper() for x in rep.columns]
star = c.export_to_pandas(A.STARS); star.columns = [x.upper() for x in star.columns]

with t2:
    st.markdown("**Repeated heavy queries**, same query shape run over and over, ranked by cost.")
    for _, r in rep.head(3).iterrows():
        st.markdown(f"<div class='find'><code>{r.PATTERN}</code><div class='meta'>{int(r.RUNS):,} runs by {int(r.USERS)} users · "
                    f"₹{r.UNITS*rate:,.0f} · est. saving ₹{r.UNITS*rate*0.8:,.0f} if served from a summary table (assumed 80%, measured in the next tab)</div></div>", unsafe_allow_html=True)
    st.markdown("**Wide scans**")
    st.markdown(f"<div class='find'><code>SELECT * …</code><div class='meta'>{int(star.RUNS[0]):,} runs · ₹{star.UNITS[0]*rate:,.0f} · "
                "select only the columns the report uses</div></div>", unsafe_allow_html=True)

with t3:
    st.markdown("Applies the top fix on your Exasol instance and times the same report before and after.")
    if st.button("Apply fix and measure"):
        with st.spinner("Running both versions five times each…"):
            b = timed(c, A.BEFORE); c.execute(A.FIX); a = timed(c, A.AFTER)
        k1, k2, k3 = st.columns(3)
        k1.metric("Before", f"{b*1000:,.0f} ms"); k2.metric("After", f"{a*1000:,.0f} ms")
        k3.metric("Faster by", f"{b/a:,.1f}×", f"{1-a/b:.0%} less time")
        st.success("Fix applied: SALES_DAILY summary table now serves this report. Times are medians of 5 runs with the query cache off.")

def load(sql):
    d = c.export_to_pandas(sql); d.columns = [x.upper() for x in d.columns]; return d
team, dash, peak, unused = load(A.TEAMS), load(A.DASHBOARDS), load(A.PEAK), load(A.UNUSED)

with tw:
    st.markdown("Where the modelled cost lands, in ₹.")
    for col, d, key, title in zip(st.columns(2), (team, dash), ("TEAM", "DASHBOARD"), ("Cost by team", "Cost by dashboard")):
        f = go.Figure(go.Bar(x=d.UNITS * rate, y=d[key], orientation="h", marker_color="#0F766E"))
        f.update_layout(title=title, height=300, margin=dict(l=0, r=0, t=40, b=0), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        yaxis=dict(autorange="reversed"), xaxis_title="₹", font=dict(family="IBM Plex Sans"))
        col.plotly_chart(f, use_container_width=True)
    top = dash.iloc[0]
    st.caption(f"{top.DASHBOARD} alone accounts for {top.UNITS / dash.UNITS.sum():.0%} of modelled cost.")

with t2:
    r, pk = rep.iloc[0], peak.iloc[0]
    st.markdown("**Peak-hour load**")
    st.markdown(f"<div class='find'><code>Queries over 5 s</code><div class='meta'>{int(pk.RUNS):,} runs · {pk.PEAK_UNITS / pk.UNITS:.0%} of their cost lands "
                "between 10:00 and 16:00. Schedule these refreshes off-peak.</div></div>", unsafe_allow_html=True)
    st.markdown("**Unused tables**")
    st.markdown(f"<div class='find'><code>{', '.join(unused.TABLE_NAME)}</code><div class='meta'>{len(unused)} tables, "
                f"{unused.SIZE_MB.sum() / 1024:.1f} GB never referenced in this query history. Archive or drop after owner sign-off.</div></div>", unsafe_allow_html=True)
    st.markdown("**Explanation and ticket for the top finding**")
    facts = {"kind": "repeated heavy query", "pattern": r.PATTERN, "runs": int(r.RUNS), "users": int(r.USERS),
             "cost_rupees": round(float(r.UNITS * rate)), "fix": "serve it from a pre-aggregated summary table"}
    st.write(st.cache_data(explain)(facts)); st.code(ticket(facts), language="markdown")
