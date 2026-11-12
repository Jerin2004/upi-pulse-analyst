
"""Load PhonePe Pulse open data into tidy pandas DataFrames."""

import json
from pathlib import Path

import pandas as pd


# --------------------------------------------------
# JSON READER
# --------------------------------------------------

def _read(path):
    with Path(path).open("r", encoding="utf-8") as file:
        return json.load(file)


# --------------------------------------------------
# VALIDATE DATASET
# --------------------------------------------------

def validate_dataset(root):

    root = Path(root)

    required_paths = {
        "state_category": (
            root / "data/aggregated/transaction/country/india/state"
        ),
        "district": (
            root / "data/map/transaction/hover/country/india/state"
        ),
        "users": (
            root / "data/aggregated/user/country/india/state"
        ),
    }

    errors = []

    for name, path in required_paths.items():

        if not path.exists():
            errors.append(f"{name}: directory missing ({path})")
            continue

        files = list(path.glob("*/*/*.json"))

        if not files:
            errors.append(f"{name}: no JSON files found ({path})")

    if errors:
        raise FileNotFoundError(
            "PhonePe Pulse dataset validation failed:\n"
            + "\n".join(errors)
        )

    return required_paths


# --------------------------------------------------
# STATE CATEGORY DATA
# --------------------------------------------------

def load_state_category(root):

    """State x quarter x category transaction counts."""

    base = (
        Path(root)
        / "data/aggregated/transaction/country/india/state"
    )

    rows = []

    files = sorted(base.glob("*/*/*.json"))

    for file in files:

        state = file.parts[-3]
        year = int(file.parts[-2])
        quarter = int(file.stem)

        data = _read(file)["data"]

        for transaction in data.get("transactionData", []):

            instruments = transaction.get("paymentInstruments", [])

            if not instruments:
                continue

            rows.append({
                "state": state,
                "year": year,
                "quarter": quarter,
                "category": transaction.get("name", "Unknown"),
                "txn_count": instruments[0].get("count", 0),
            })

    df = pd.DataFrame(rows)

    if df.empty:
        raise ValueError(
            f"No state-category transaction records found in {base}"
        )

    return df


# --------------------------------------------------
# DISTRICT DATA
# --------------------------------------------------

def load_district(root):

    """District x quarter transaction count and amount."""

    base = (
        Path(root)
        / "data/map/transaction/hover/country/india/state"
    )

    rows = []

    files = sorted(base.glob("*/*/*.json"))

    for file in files:

        state = file.parts[-3]
        year = int(file.parts[-2])
        quarter = int(file.stem)

        data = _read(file)["data"]

        for district in data.get("hoverDataList", []):

            metrics = district.get("metric", [])

            if not metrics:
                continue

            metric = metrics[0]

            rows.append({
                "state": state,
                "district": district.get("name", "").replace(
                    " district", ""
                ),
                "year": year,
                "quarter": quarter,
                "txn_count": metric.get("count", 0),
                "txn_amount": metric.get("amount", 0),
            })

    df = pd.DataFrame(rows)

    if df.empty:
        raise ValueError(
            f"No district transaction records found in {base}"
        )

    return df


# --------------------------------------------------
# USER DATA
# --------------------------------------------------

def load_users(root):

    """State x quarter registered users."""

    base = (
        Path(root)
        / "data/aggregated/user/country/india/state"
    )

    rows = []

    files = sorted(base.glob("*/*/*.json"))

    for file in files:

        state = file.parts[-3]
        year = int(file.parts[-2])
        quarter = int(file.stem)

        data = _read(file)["data"]

        aggregated = data.get("aggregated", {})

        registered_users = aggregated.get(
            "registeredUsers",
            aggregated.get("registeredCount", 0),
        )

        rows.append({
            "state": state,
            "year": year,
            "quarter": quarter,
            "registered_users": registered_users,
        })

    df = pd.DataFrame(rows)

    if df.empty:
        raise ValueError(
            f"No registered-user records found in {base}"
        )

    return df


# --------------------------------------------------
# ADD QUARTER PERIOD
# --------------------------------------------------

def add_period(df):

    """Generate period labels such as 2025-Q1."""

    df = df.copy()

    required = ["year", "quarter"]

    missing = [
        col for col in required
        if col not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Cannot generate period. Missing columns: {missing}"
        )

    df["year"] = pd.to_numeric(
        df["year"],
        errors="coerce",
    )

    df["quarter"] = pd.to_numeric(
        df["quarter"],
        errors="coerce",
    )

    df = df.dropna(
        subset=["year", "quarter"]
    ).copy()

    df["year"] = df["year"].astype(int)
    df["quarter"] = df["quarter"].astype(int)

    df = df[
        df["quarter"].between(1, 4)
    ].copy()

    df["period"] = (
        df["year"].astype(str)
        + "-Q"
        + df["quarter"].astype(str)
    )

    return df


# --------------------------------------------------
# LOAD ALL DATASETS
# --------------------------------------------------

def load_all(root):

    """Load and validate all PhonePe Pulse datasets."""

    validate_dataset(root)

    sc = add_period(load_state_category(root))
    district = add_period(load_district(root))
    users = add_period(load_users(root))

    return sc, district, users
