import warnings; warnings.filterwarnings("ignore")
import os
import pandas as pd
import subprocess, pathlib
import plotly.express as px
import streamlit as st
from load_data import load_state_category, load_district, load_users, add_period
from analysis import national_trend, state_growth, ticket_size, txns_per_user, district_anomalies

st.set_page_config(page_title="UPI Pulse Analyst", page_icon="📊", layout="wide")
DATA_ROOT = os.environ.get("PULSE_PATH", "pulse")  # clone of github.com/PhonePe/pulse
if not pathlib.Path(DATA_ROOT).exists():
    subprocess.run(["git", "clone", "--depth", "1",
                    "https://github.com/PhonePe/pulse.git", DATA_ROOT], check=True)
@st.cache_data(show_spinner="Loading PhonePe Pulse data...")
def load():
    return (add_period(load_state_category(DATA_ROOT)), add_period(load_district(DATA_ROOT)),
            add_period(load_users(DATA_ROOT)))

sc, d, u = load()
periods = sorted(sc.period.unique())
latest = st.sidebar.selectbox("Quarter", periods[::-1], index=0)
prior = f"{int(latest[:4]) - 1}{latest[4:]}"
clean = lambda s: s.str.replace("-", " ").str.title()

st.title("📊 UPI Pulse Analyst")
st.caption("Digital payments trends, user behaviour and anomaly screening on PhonePe's open Pulse data.")

tot = sc.groupby("period").txn_count.sum()
amt = d.groupby("period").txn_amount.sum()
c1, c2, c3, c4 = st.columns(4)
c1.metric("Transactions (qtr)", f"{tot[latest]/1e9:.1f} B", f"{tot[latest]/tot[prior]-1:+.1%} YoY")
c2.metric("Value (qtr)", f"₹{amt[latest]/1e12:.1f} L Cr", f"{amt[latest]/amt[prior]-1:+.1%} YoY")
c3.metric("Avg ticket", f"₹{amt[latest]/tot[latest]:,.0f}")
c4.metric("States / UTs", sc.state.nunique())

t1, t2, t3, t4 = st.tabs(["Trends", "States & users", "Anomaly screening", "Ask in plain English"])

with t1:
    nt = national_trend(sc)
    st.plotly_chart(px.area(nt, x="period", y="txn_count", color="category",
                            title="Quarterly transactions by category"), width="stretch")
    mix = nt.pivot(index="period", columns="category", values="txn_count")
    mix = mix.div(mix.sum(axis=1), axis=0).reset_index().melt("period", value_name="share")
    st.plotly_chart(px.line(mix, x="period", y="share", color="category",
                            title="Category mix: Retail share keeps rising, Utility keeps falling"),
                    width="stretch")

with t2:
    a, b = st.columns(2)
    g = state_growth(sc, latest, prior); g["state"] = clean(g.state)
    a.plotly_chart(px.bar(g.head(12), x="yoy_growth", y="state", orientation="h",
                          title=f"Fastest-growing states ({latest} vs {prior})").update_yaxes(autorange="reversed"),
                   width="stretch")
    tk = ticket_size(d, latest); tk["state"] = clean(tk.state)
    b.plotly_chart(px.bar(tk.sort_values("avg_ticket_inr", ascending=False).head(12), x="avg_ticket_inr", y="state",
                          orientation="h", title="Highest average ticket size (₹)").update_yaxes(autorange="reversed"),
                   width="stretch")
    tu = txns_per_user(sc, u, latest); tu["state"] = clean(tu.state)
    st.plotly_chart(px.bar(tu.sort_values("txns_per_registered_user", ascending=False), x="state",
                           y="txns_per_registered_user", title="Transactions per registered user (engagement depth)"),
                    width="stretch")

with t3:
    st.markdown("Unsupervised **Isolation Forest** over QoQ volume growth, QoQ value growth and ticket-size z-score "
                "within state. This is a *screening* tool: a flag means *look here*, not *fraud*.")
    an = district_anomalies(d, latest)
    show = an[an.flagged][["state", "district", "txn_count", "count_qoq", "amount_qoq", "ticket_z", "anomaly_score"]].copy()
    show["state"] = clean(show.state); show["district"] = show.district.str.title()
    st.dataframe(show.style.format({"count_qoq": "{:+.0%}", "amount_qoq": "{:+.0%}", "ticket_z": "{:.2f}",
                                    "anomaly_score": "{:.3f}", "txn_count": "{:,.0f}"}), width="stretch")
    st.info("Always check seasonality before calling something suspicious: hill and pilgrimage districts "
            "commonly spike in the April-June tourist season.")

with t4:
    st.markdown("**Coming next:** natural-language questions answered with read-only, schema-aware SQL "
                "(Groq / Llama) plus the chart and an explanation.")
