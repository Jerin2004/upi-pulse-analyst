"""Analysis helpers: growth, mix shift, ticket size, and district-level anomaly detection."""
import numpy as np
import pandas as pd

def national_trend(sc):
    return sc.groupby(["year", "quarter", "period", "category"], as_index=False).txn_count.sum()

def state_growth(sc, latest, prior):
    s = sc.groupby(["state", "period"]).txn_count.sum().unstack()
    out = pd.DataFrame({"txn_latest": s[latest], "yoy_growth": s[latest] / s[prior] - 1})
    return out.sort_values("yoy_growth", ascending=False).reset_index()

def ticket_size(d, period):
    x = d[d.period == period].groupby("state")[["txn_count", "txn_amount"]].sum()
    x["avg_ticket_inr"] = x.txn_amount / x.txn_count
    return x.reset_index()

def txns_per_user(sc, u, period):
    tx = sc[sc.period == period].groupby("state").txn_count.sum()
    us = u[u.period == period].set_index("state").registered_users
    return (tx / us).rename("txns_per_registered_user").reset_index()

def seasonal_anomalies(df, period, z_threshold=3.5):
    """Rank districts by how far their QoQ growth deviates from their OWN seasonal norm.

    `df` is the output of sql/seasonal_anomaly.sql (qoq vs average QoQ of the same quarter in the prior 3 years).
    The excess is standardised with a robust z-score (median / MAD) within the quarter, which removes the
    market-wide slowdown effect and is not distorted by the outliers we are trying to find.
    """
    cur = df[df.period == period].copy()
    med = cur.excess_qoq.median()
    mad = (cur.excess_qoq - med).abs().median() * 1.4826
    cur["robust_z"] = (cur.excess_qoq - med) / (mad + 1e-9)
    cur["flagged"] = cur.robust_z.abs() >= z_threshold
    cur["direction"] = cur.robust_z.apply(lambda z: "above seasonal norm" if z > 0 else "below seasonal norm")
    return cur.reindex(cur.robust_z.abs().sort_values(ascending=False).index)
