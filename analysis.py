"""Analysis helpers: growth, mix shift, ticket size, and district-level anomaly detection."""
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

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

def district_anomalies(d, period, contamination=0.01, seed=42):
    """Flag districts whose quarter looks unusual vs. their own history and peers.

    Features: QoQ count growth, QoQ amount growth, ticket-size z-score within state.
    Unsupervised (Isolation Forest) - a screening tool, not a fraud verdict.
    """
    d = d.sort_values(["state", "district", "year", "quarter"]).copy()
    g = d.groupby(["state", "district"])
    d["count_qoq"] = g.txn_count.pct_change()
    d["amount_qoq"] = g.txn_amount.pct_change()
    d["ticket"] = d.txn_amount / d.txn_count
    d["ticket_z"] = d.groupby(["state", "period"]).ticket.transform(lambda s: (s - s.mean()) / (s.std() + 1e-9))
    cur = d[(d.period == period) & (d.txn_count > 1_000_000)].dropna(subset=["count_qoq", "amount_qoq", "ticket_z"]).copy()
    feats = cur[["count_qoq", "amount_qoq", "ticket_z"]].replace([np.inf, -np.inf], np.nan).fillna(0)
    model = IsolationForest(contamination=contamination, random_state=seed).fit(feats)
    cur["anomaly_score"] = -model.score_samples(feats)
    cur["flagged"] = model.predict(feats) == -1
    return cur.sort_values("anomaly_score", ascending=False)
