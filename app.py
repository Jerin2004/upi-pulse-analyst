
import warnings
warnings.filterwarnings("ignore")

import os
import pathlib
import subprocess
import tempfile
import sqlite3

import pandas as pd
import plotly.express as px
import streamlit as st

from analysis import (
    national_trend,
    seasonal_anomalies,
    state_growth,
    ticket_size,
    txns_per_user,
)
from db import build_db
from load_data import (
    add_period,
    load_district,
    load_state_category,
    load_users,
)
from sql.queries import QUERIES
from sql_ai import UnsafeSQL, answer, run_sql


# --------------------------------------------------
# PAGE CONFIGURATION
# --------------------------------------------------

st.set_page_config(
    page_title="UPI Pulse Analyst",
    page_icon="📊",
    layout="wide"
)

DATA_ROOT = os.environ.get("PULSE_PATH", "pulse")

if not pathlib.Path(DATA_ROOT).exists():
    subprocess.run(
        [
            "git",
            "clone",
            "--depth",
            "1",
            "https://github.com/PhonePe/pulse.git",
            DATA_ROOT,
        ],
        check=True,
    )


# --------------------------------------------------
# DATA LOADING
# --------------------------------------------------

@st.cache_data(show_spinner="Loading PhonePe Pulse data...")
def load():

    sc = add_period(load_state_category(DATA_ROOT))
    d = add_period(load_district(DATA_ROOT))
    u = add_period(load_users(DATA_ROOT))

    # Normalize period values
    sc["period"] = sc["period"].astype(str)
    d["period"] = d["period"].astype(str)
    u["period"] = u["period"].astype(str)

    return sc, d, u


@st.cache_resource(show_spinner="Building SQL database...")
def get_db():

    path = pathlib.Path(tempfile.gettempdir()) / "pulse_analyst.db"

    if not path.exists():
        build_db(DATA_ROOT, path)

    return str(path)


def groq_key():

    try:
        return st.secrets["GROQ_API_KEY"]
    except Exception:
        return os.environ.get("GROQ_API_KEY")


# --------------------------------------------------
# INITIALIZE DATA
# --------------------------------------------------

sc, d, u = load()

DB = get_db()


# --------------------------------------------------
# QUARTER SELECTION
# --------------------------------------------------

periods = sorted(
    sc["period"].dropna().astype(str).unique()
)

if not periods:
    st.error("No quarterly data found.")
    st.stop()

latest = st.sidebar.selectbox(
    "Quarter",
    periods[::-1],
    index=0,
)

# Calculate equivalent quarter from previous year
try:
    year = int(latest[:4])
    quarter = latest[4:]

    prior = f"{year - 1}{quarter}"

except (ValueError, TypeError, IndexError):
    prior = None


# Check historical data availability separately
has_prior_sc = (
    prior is not None and prior in set(sc["period"])
)

has_prior_d = (
    prior is not None and prior in set(d["period"])
)

has_prior = has_prior_sc and has_prior_d


# --------------------------------------------------
# HELPER FUNCTIONS
# --------------------------------------------------

def clean(series):
    return series.str.replace("-", " ").str.title()


def safe_growth(current, previous):

    if pd.isna(previous) or previous == 0:
        return None

    return f"{current / previous - 1:+.1%} YoY"


# --------------------------------------------------
# AGGREGATIONS
# --------------------------------------------------

tot = sc.groupby("period").txn_count.sum()
amt = d.groupby("period").txn_amount.sum()

if latest not in tot.index or latest not in amt.index:
    st.error(f"Missing transaction data for {latest}.")
    st.stop()

latest_txns = tot[latest]
latest_amt = amt[latest]

if latest_txns == 0:
    st.error("Transaction count is zero for the selected quarter.")
    st.stop()


# --------------------------------------------------
# DASHBOARD HEADER
# --------------------------------------------------

st.title("📊 UPI Pulse Analyst")

st.caption(
    "Digital payments trends, user behaviour, SQL analytics "
    "and anomaly screening on PhonePe's open Pulse data."
)


# --------------------------------------------------
# KEY METRICS
# --------------------------------------------------

c1, c2, c3, c4 = st.columns(4)

if has_prior and prior in tot.index and prior in amt.index:

    txn_growth = safe_growth(
        latest_txns,
        tot[prior]
    )

    value_growth = safe_growth(
        latest_amt,
        amt[prior]
    )

    previous_ticket = (
        amt[prior] / tot[prior]
        if tot[prior] != 0 else 0
    )

    current_ticket = latest_amt / latest_txns

    ticket_growth = (
        f"{current_ticket / previous_ticket - 1:+.1%} YoY"
        if previous_ticket > 0 else None
    )

else:

    txn_growth = None
    value_growth = None
    ticket_growth = None

    st.sidebar.warning(
        f"Previous-year data ({prior}) is unavailable. "
        "YoY comparisons are disabled."
    )


c1.metric(
    "Transactions (qtr)",
    f"{latest_txns / 1e9:.1f} B",
    txn_growth
)

c2.metric(
    "Value (qtr)",
    f"₹{latest_amt / 1e12:.1f} L Cr",
    value_growth
)

c3.metric(
    "Avg ticket",
    f"₹{latest_amt / latest_txns:,.0f}",
    ticket_growth
)

c4.metric(
    "States / UTs",
    sc.state.nunique()
)


# --------------------------------------------------
# DASHBOARD TABS
# --------------------------------------------------

t1, t2, t3, t4, t5 = st.tabs(
    [
        "Trends",
        "States & users",
        "Anomaly screening",
        "SQL Explorer",
        "Ask in plain English",
    ]
)


# ==================================================
# TAB 1: NATIONAL TRENDS
# ==================================================

with t1:

    nt = national_trend(sc)

    st.plotly_chart(
        px.area(
            nt,
            x="period",
            y="txn_count",
            color="category",
            title="Quarterly transactions by category",
        ),
        width="stretch",
    )

    mix = nt.pivot(
        index="period",
        columns="category",
        values="txn_count",
    )

    mix = mix.div(
        mix.sum(axis=1),
        axis=0,
    ).reset_index().melt(
        "period",
        value_name="share",
    )

    st.plotly_chart(
        px.line(
            mix,
            x="period",
            y="share",
            color="category",
            title=(
                "Category mix: Utility/P2P surged in 2020-21, "
                "Retail has gained share every year since"
            ),
        ),
        width="stretch",
    )

    tk = pd.DataFrame({
        "period": amt.index,
        "avg_ticket_inr": (amt / tot.reindex(amt.index)).values,
    })

    st.plotly_chart(
        px.line(
            tk,
            x="period",
            y="avg_ticket_inr",
            title=(
                "Average ticket size (₹) "
                "has fallen every year since its 2021 peak"
            ),
        ),
        width="stretch",
    )


# ==================================================
# TAB 2: STATES AND USERS
# ==================================================

with t2:

    a, b = st.columns(2)

    # State growth chart requires previous-year data
    if has_prior_sc:

        g = state_growth(sc, latest, prior)

        g["state"] = clean(g.state)

        a.plotly_chart(
            px.bar(
                g.head(12),
                x="yoy_growth",
                y="state",
                orientation="h",
                title=f"Fastest-growing states ({latest} vs {prior})",
            ).update_yaxes(autorange="reversed"),
            width="stretch",
        )

    else:

        a.warning(
            f"Previous-year state data ({prior}) is unavailable. "
            "State growth cannot be calculated."
        )

    # Ticket size
    tkt = ticket_size(d, latest)

    tkt["state"] = clean(tkt.state)

    b.plotly_chart(
        px.bar(
            tkt.sort_values(
                "avg_ticket_inr",
                ascending=False,
            ).head(12),
            x="avg_ticket_inr",
            y="state",
            orientation="h",
            title="Highest average ticket size (₹)",
        ).update_yaxes(autorange="reversed"),
        width="stretch",
    )

    # Transactions per registered user
    tu = txns_per_user(sc, u, latest)

    tu["state"] = clean(tu.state)

    st.plotly_chart(
        px.bar(
            tu.sort_values(
                "txns_per_registered_user",
                ascending=False,
            ),
            x="state",
            y="txns_per_registered_user",
            title="Transactions per registered user (engagement depth)",
        ),
        width="stretch",
    )


# ==================================================
# TAB 3: ANOMALY SCREENING
# ==================================================

with t3:

    st.markdown(
        "**Seasonally adjusted anomaly screening.** "
        "Each district's quarter-on-quarter growth is compared with "
        "its own average for the same quarter in the previous 3 years "
        "(SQL window functions), then standardised with a robust "
        "z-score (median/MAD) across districts. A flag means "
        "*behaving unlike its usual seasonal pattern* and is a "
        "reason to investigate, not evidence of fraud."
    )

    z_thr = st.slider(
        "Flag threshold (|robust z|)",
        2.5,
        6.0,
        3.5,
        0.5,
    )

    seas = pd.read_sql(
        pathlib.Path("sql/seasonal_anomaly.sql").read_text(),
        sqlite3.connect(DB),
    )

    an = seasonal_anomalies(
        seas,
        latest,
        z_thr,
    )

    if an.empty:

        st.warning(
            "Not enough history for this quarter "
            "(needs 3 prior years of the same quarter)."
        )

    else:

        top = an.head(10).copy()

        top["state"] = clean(top.state)
        top["district"] = top.district.str.title()

        st.dataframe(
            top[
                [
                    "state",
                    "district",
                    "txn_count",
                    "qoq",
                    "seasonal_qoq",
                    "robust_z",
                    "direction",
                    "flagged",
                ]
            ].style.format(
                {
                    "txn_count": "{:,.0f}",
                    "qoq": "{:+.0%}",
                    "seasonal_qoq": "{:+.0%}",
                    "robust_z": "{:.1f}",
                }
            ),
            width="stretch",
        )

        st.caption(
            f"{int(an.flagged.sum())} of {len(an)} "
            f"districts flagged in {latest}."
        )

        opts = [
            f"{r.district.title()} "
            f"({r.state.replace('-', ' ').title()})"
            for r in an.head(10).itertuples()
        ]

        pick = st.selectbox(
            "Inspect a district's history",
            opts,
        )

        row = an.iloc[opts.index(pick)]

        hist = d[
            (d.state == row.state)
            & (d.district == row.district)
        ].sort_values(
            ["year", "quarter"]
        )

        st.plotly_chart(
            px.line(
                hist,
                x="period",
                y="txn_count",
                markers=True,
                title=(
                    f"{pick}: quarterly transactions "
                    "(look for a repeating seasonal peak)"
                ),
            ),
            width="stretch",
        )


# ==================================================
# TAB 4: SQL EXPLORER
# ==================================================

with t4:

    st.markdown(
        "Curated analytical queries (SQLite): window functions, "
        "CTEs and joins on the same data. "
        "Pick one, read the SQL, see the result."
    )

    key = st.selectbox(
        "Query",
        list(QUERIES),
        format_func=lambda k: QUERIES[k]["title"],
    )

    q = QUERIES[key]

    st.markdown(
        f"**Question:** {q['question']}"
    )

    st.code(
        q["sql"],
        language="sql",
    )

    res = run_sql(
        DB,
        q["sql"],
    )

    st.dataframe(
        res,
        width="stretch",
    )


# ==================================================
# TAB 5: ASK IN PLAIN ENGLISH
# ==================================================

with t5:

    st.markdown(
        "Ask a question in plain English. An LLM (Groq / Llama 3.3) "
        "writes the SQL; it is validated, run on a **read-only** "
        "connection with an authorizer and a time limit, "
        "and shown to you so you can check it."
    )

    examples = [
        "Which 5 states had the highest YoY transaction growth in the latest quarter?",
        "How has the Retail share of transactions changed each year in Q2?",
        "Top 10 districts by average ticket size with at least 5 million transactions",
    ]

    ex = st.selectbox(
        "Examples",
        [""] + examples,
    )

    question = st.text_input(
        "Your question",
        value=ex,
    )

    if st.button(
        "Run",
        disabled=not question,
    ):

        if not groq_key():

            st.info(
                "Add a GROQ_API_KEY (Streamlit secrets or environment "
                "variable) to enable this. You can still write SQL "
                "yourself below."
            )

        else:

            with st.spinner("Thinking..."):

                out = answer(
                    question,
                    DB,
                    api_key=groq_key(),
                )

            if out["error"]:
                st.error(out["error"])

            if out["explanation"]:
                st.markdown(out["explanation"])

            if out["sql"]:
                st.code(
                    out["sql"],
                    language="sql",
                )

            if out["df"] is not None:

                st.dataframe(
                    out["df"],
                    width="stretch",
                )

                num = out["df"].select_dtypes(
                    "number"
                ).columns

                if (
                    2 <= len(out["df"].columns)
                    and len(num) >= 1
                    and 1 < len(out["df"]) <= 60
                ):

                    x = [
                        c
                        for c in out["df"].columns
                        if c not in num[:1]
                    ][0]

                    st.plotly_chart(
                        px.bar(
                            out["df"],
                            x=x,
                            y=num[0],
                        ),
                        width="stretch",
                    )

    # SQL CONSOLE
    with st.expander("SQL console (write your own SELECT)"):

        schema = pd.read_sql(
            "SELECT name FROM sqlite_master WHERE type='table'",
            sqlite3.connect(DB),
        )

        st.caption(
            "Tables: "
            + ", ".join(schema.name)
            + ". Only SELECT/WITH is allowed."
        )

        mine = st.text_area(
            "SQL",
            "SELECT state, SUM(txn_count) AS txns\n"
            "FROM state_category\n"
            "WHERE period = '2026-Q2'\n"
            "GROUP BY state\n"
            "ORDER BY txns DESC\n"
            "LIMIT 10",
            height=140,
        )

        if st.button("Run my SQL"):

            try:

                st.dataframe(
                    run_sql(DB, mine),
                    width="stretch",
                )

            except UnsafeSQL as e:

                st.error(f"Blocked: {e}")

            except Exception as e:

                st.error(f"SQL error: {e}")
