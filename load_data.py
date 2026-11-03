"""Load PhonePe Pulse open data (github.com/PhonePe/pulse) into tidy pandas DataFrames."""
import json
from pathlib import Path
import pandas as pd

def _read(p):
    return json.loads(Path(p).read_text())

def load_state_category(root):
    """State x quarter x category (P2P/Retail/Utility) transaction counts."""
    rows = []
    base = Path(root) / "data/aggregated/transaction/country/india/state"
    for f in base.glob("*/*/*.json"):
        state, year, q = f.parts[-3], int(f.parts[-2]), int(f.stem)
        for t in _read(f)["data"]["transactionData"]:
            rows.append((state, year, q, t["name"], t["paymentInstruments"][0]["count"]))
    return pd.DataFrame(rows, columns=["state", "year", "quarter", "category", "txn_count"])

def load_district(root):
    """District x quarter transaction count and amount (INR)."""
    rows = []
    base = Path(root) / "data/map/transaction/hover/country/india/state"
    for f in base.glob("*/*/*.json"):
        state, year, q = f.parts[-3], int(f.parts[-2]), int(f.stem)
        for d in _read(f)["data"]["hoverDataList"]:
            m = d["metric"][0]
            rows.append((state, d["name"].replace(" district", ""), year, q, m["count"], m["amount"]))
    return pd.DataFrame(rows, columns=["state", "district", "year", "quarter", "txn_count", "txn_amount"])

def load_users(root):
    """State x quarter registered users."""
    rows = []
    base = Path(root) / "data/aggregated/user/country/india/state"
    for f in base.glob("*/*/*.json"):
        state, year, q = f.parts[-3], int(f.parts[-2]), int(f.stem)
        rows.append((state, year, q, _read(f)["data"]["aggregated"]["registeredUsers"]
                     if "registeredUsers" in _read(f)["data"]["aggregated"]
                     else _read(f)["data"]["aggregated"]["registeredCount"]))
    return pd.DataFrame(rows, columns=["state", "year", "quarter", "registered_users"])

def add_period(df):
    df["period"] = df["year"].astype(str) + "-Q" + df["quarter"].astype(str)
    return df
