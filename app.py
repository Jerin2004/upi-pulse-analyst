
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


# ==================================================
# PAGE CONFIGURATION
# ==================================================

st.set_page_config(
    page_title="UPI Pulse Analyst",
    page_icon="📊",
    layout="wide",
)

DATA_ROOT = os.environ.get("PULSE_PATH", "pulse")


# ==================================================
# DATASET DOWNLOAD
# ==================================================


import shutil
import tempfile

def ensure_data():

    data_path = pathlib.Path(DATA_ROOT)

    expected_path = (
        data_path
        / "data/aggregated/transaction/country/india/state"
    )

    # Check whether actual dataset files exist
    existing_files = (
        list(expected_path.glob("*/*/*.json"))
        if expected_path.exists()
        else []
    )

    if existing_files:
        return

    st.info("PhonePe Pulse dataset missing. Downloading...")

    # Clone into a temporary directory first
    temp_path = pathlib.Path(
        tempfile.mkdtemp()
    ) / "pulse"

    try:

        subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "https://github.com/PhonePe/pulse.git",
                str(temp_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        if not (
            temp_path
            / "data/aggregated/transaction/country/india/state"
        ).exists():
            raise RuntimeError(
                "Cloned repository does not contain expected data."
            )

        # Replace incomplete dataset directory
        if data_path.exists():
            shutil.rmtree(data_path)

        shutil.copytree(temp_path, data_path)

    except Exception as e:

        raise RuntimeError(
            f"Unable to download PhonePe Pulse dataset: {e}"
        ) from e



# ==================================================
# DATABASE
# ==================================================

@st.cache_resource(show_spinner="Building SQL database...")
def get_db():

    path = pathlib.Path(tempfile.gettempdir()) / "pulse_analyst.db"

    # Build database if it does not exist
    if not path.exists():
        build_db(DATA_ROOT, path)

    return str(path)


# ==================================================
# GROQ API KEY
# ==================================================

def groq_key():

    try:
        return st.secrets["GROQ_API_KEY"]
    except Exception:
        return os.environ.get("GROQ_API_KEY")


# ==================================================
# HELPER FUNCTIONS
# ==================================================

def clean(series):

    return (
        series.astype(str)
        .str.replace("-", " ", regex=False)
        .str.title()
    )


def calculate_growth(current, previous):

    if pd.isna(previous) or previous == 0:
        return None

    return f"{current / previous - 1:+.1%} YoY"


def calculate_prior(latest):

    try:
        year = int(latest[:4])
        quarter = latest[4:]

        return f"{year - 1}{quarter}"

    except (ValueError, TypeError, IndexError):
        return None


# ==================================================
# INITIALIZE APPLICATION
# ==================================================

try:

    sc, d, u = load()

except Exception as e:

    st.error("Unable to load PhonePe Pulse data.")

    st.exception(e)

    st.info(
        "Check load_data.py, the dataset directory, "
        "and the Streamlit Cloud logs."
    )

    st.stop()


# ==================================================
# VALIDATE DATA
# ==================================================

required_columns = {
    "state_category": ["period", "state", "txn_count"],
    "district": ["period", "state", "district", "txn_amount"],
    "users": ["period"],
}

for name, frame, required in [
    ("State category", sc, required_columns["state_category"]),
    ("District", d, required_columns["district"]),
    ("Users", u, required_columns["users"]),
]:

    missing = [
        col for col in required
        if col not in frame.columns
    ]

    if missing:

        st.error(
            f"{name} dataset is missing columns: {missing}"
        )

        st.write("Available columns:", frame.columns.tolist())

        st.stop()


# ==================================================
# QUARTER SELECTION
# ==================================================

periods = sorted(
    sc["period"].dropna().astype(str).unique()
)

if not periods:

    st.error(
        "No quarterly data found in the state-category dataset."
    )

    st.write("Dataset shape:", sc.shape)
    st.write("Columns:", sc.columns.tolist())
    st.dataframe(sc.head(10))

    st.stop()


latest = st.sidebar.selectbox(
    "Quarter",
    periods[::-1],
    index=0,
)

prior = calculate_prior(latest)

sc_periods = set(sc["period"].astype(str))
d_periods = set(d["period"].astype(str))

has_prior_sc = prior in sc_periods if prior else False
has_prior_d = prior in d_periods if prior else False


# ==================================================
# DATABASE INITIALIZATION
# ==================================================

try:

    DB = get_db()

except Exception as e:

    st.error("Unable to initialize SQL database.")
    st.exception(e)
    st.stop()


# ==================================================
# AGGREGATIONS
# ==================================================

tot = sc.groupby("period")["txn_count"].sum()
amt = d.groupby("period")["txn_amount"].sum()

if latest not in tot.index:

    st.error(f"No transaction count available for {latest}.")
    st.stop()

if latest not in amt.index:

    st.error(f"No transaction amount available for {latest}.")
    st.stop()


latest_txns = tot[latest]
latest_amt = amt[latest]

if latest_txns == 0:

    st.error("Transaction count is zero.")
    st.stop()


# ==================================================
# HEADER
# ==================================================

st.title("📊 UPI Pulse Analyst")

st.caption(
    "Digital payments trends, user behaviour, SQL analytics "
    "and anomaly screening on PhonePe's open Pulse data."
)


# ==================================================
# METRICS
# ==================================================

c1, c2, c3, c4 = st.columns(4)

has_prior = (
    has_prior_sc
    and has_prior_d
    and prior in tot.index
    and prior in amt.index
)

if has_prior:

    txn_growth = calculate_growth(
        latest_txns,
        tot[prior],
    )

    value_growth = calculate_growth(
        latest_amt,
        amt[prior],
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
        f"Previous-year data ({prior}) is unavailable."
    )


c1.metric(
    "Transactions (qtr)",
    f"{latest_txns / 1e9:.1f} B",
    txn_growth,
)

c2.metric(
    "Value (qtr)",
    f"₹{latest_amt / 1e12:.1f} L Cr",
    value_growth,
)

c3.metric(
    "Avg ticket",
    f"₹{latest_amt / latest_txns:,.0f}",
    ticket_growth,
)

c4.metric(
    "States / UTs",
    sc["state"].nunique(),
)


# ==================================================
# TABS
# ==================================================

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
# TAB 1: TRENDS
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
        id_vars="period",
        value_name="share",
    )

    st.plotly_chart(
        px.line(
            mix,
            x="period",
            y="share",
            color="category",
            title="Quarterly transaction category mix",
        ),
        width="stretch",
    )

    common_periods = tot.index.intersection(amt.index)

    tk = pd.DataFrame({
        "period": common_periods,
        "avg_ticket_inr": (
            amt.loc[common_periods] /
            tot.loc[common_periods]
        ).values,
    })

    st.plotly_chart(
        px.line(
            tk,
            x="period",
            y="avg_ticket_inr",
            title="Average ticket size (₹)",
        ),
        width="stretch",
    )


# ==================================================
# TAB 2: STATES AND USERS
# ==================================================

with t2:

    a, b = st.columns(2)

    if has_prior_sc:

        g = state_growth(sc, latest, prior)

        g["state"] = clean(g["state"])

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
            "Previous-year state data unavailable."
        )

    tkt = ticket_size(d, latest)

    tkt["state"] = clean(tkt["state"])

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

    if not u.empty:

        tu = txns_per_user(sc, u, latest)

        tu["state"] = clean(tu["state"])

        st.plotly_chart(
            px.bar(
                tu.sort_values(
                    "txns_per_registered_user",
                    ascending=False,
                ),
                x="state",
                y="txns_per_registered_user",
                title="Transactions per registered user",
            ),
            width="stretch",
        )


# ==================================================
# TAB 3: ANOMALY SCREENING
# ==================================================

with t3:

    st.markdown(
        "**Seasonally adjusted anomaly screening.** "
        "Each district's quarterly growth is compared with "
        "its historical seasonal pattern. A flag is a reason "
        "to investigate, not evidence of fraud."
    )

    z_thr = st.slider(
        "Flag threshold (|robust z|)",
        2.5,
        6.0,
        3.5,
        0.5,
    )

    anomaly_file = pathlib.Path("sql/seasonal_anomaly.sql")

    if not anomaly_file.exists():

        st.error("sql/seasonal_anomaly.sql not found.")

    else:

        try:

            with sqlite3.connect(DB) as conn:

                seas = pd.read_sql(
                    anomaly_file.read_text(),
                    conn,
                )

            an = seasonal_anomalies(
                seas,
                latest,
                z_thr,
            )

            if an.empty:

                st.warning(
                    "Not enough historical data for this quarter."
                )

            else:

                top = an.head(10).copy()

                top["state"] = clean(top["state"])
                top["district"] = top["district"].str.title()

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
                    (d["state"] == row.state)
                    & (d["district"] == row.district)
                ].sort_values(
                    ["year", "quarter"]
                )

                st.plotly_chart(
                    px.line(
                        hist,
                        x="period",
                        y="txn_count",
                        markers=True,
                        title=f"{pick}: quarterly transactions",
                    ),
                    width="stretch",
                )

        except Exception as e:

            st.error("Anomaly analysis failed.")
            st.exception(e)


# ==================================================
# TAB 4: SQL EXPLORER
# ==================================================

with t4:

    st.markdown(
        "Curated analytical queries using SQLite, "
        "window functions, CTEs and joins."
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

    try:

        res = run_sql(
            DB,
            q["sql"],
        )

        st.dataframe(
            res,
            width="stretch",
        )

    except Exception as e:

        st.error("SQL query failed.")
        st.exception(e)


# ==================================================
# TAB 5: ASK IN PLAIN ENGLISH
# ==================================================

with t5:

    st.markdown(
        "Ask a question in plain English. Groq / Llama 3.3 "
        "generates SQL, which is validated and executed "
        "on a read-only database connection."
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
        disabled=not question.strip(),
    ):

        key_value = groq_key()

        if not key_value:

            st.info(
                "Add GROQ_API_KEY in Streamlit secrets "
                "or environment variables to enable AI SQL."
            )

        else:

            try:

                with st.spinner("Thinking..."):

                    out = answer(
                        question,
                        DB,
                        api_key=key_value,
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
                        include="number"
                    ).columns

                    if (
                        len(out["df"]) > 1
                        and len(out["df"]) <= 60
                        and len(out["df"].columns) >= 2
                        and len(num) >= 1
                    ):

                        x = next(
                            (
                                col for col in out["df"].columns
                                if col not in num
                            ),
                            None,
                        )

                        if x:

                            st.plotly_chart(
                                px.bar(
                                    out["df"],
                                    x=x,
                                    y=num[0],
                                ),
                                width="stretch",
                            )

            except Exception as e:

                st.error("AI SQL execution failed.")
                st.exception(e)


    # --------------------------------------------------
    # CUSTOM SQL CONSOLE
    # --------------------------------------------------

    with st.expander("SQL console (write your own SELECT)"):

        try:

            with sqlite3.connect(DB) as conn:

                schema = pd.read_sql(
                    "SELECT name FROM sqlite_master WHERE type='table'",
                    conn,
                )

            st.caption(
                "Tables: "
                + ", ".join(schema["name"])
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

        except Exception as e:

            st.error("Unable to load SQL schema.")
            st.exception(e)
