"""Curated analytical SQL (SQLite). Each entry: title, question, sql. Shown in the app's SQL Explorer tab."""

QUERIES = {
"yoy_trend": {
  "title": "National volume & value with YoY and 4-quarter moving average",
  "question": "How fast is UPI growing, and is the average ticket changing?",
  "sql": """WITH q AS (
  SELECT period, year, quarter,
         SUM(txn_count)  AS txns,
         SUM(txn_amount) AS amount
  FROM district
  GROUP BY period, year, quarter
)
SELECT period,
       txns,
       ROUND(txns * 1.0 / LAG(txns, 4) OVER (ORDER BY year, quarter) - 1, 3)   AS txn_yoy,
       ROUND(amount * 1.0 / LAG(amount, 4) OVER (ORDER BY year, quarter) - 1, 3) AS value_yoy,
       ROUND(amount * 1.0 / txns, 1)                                            AS avg_ticket_inr,
       ROUND(AVG(txns) OVER (ORDER BY year, quarter ROWS 3 PRECEDING), 0)       AS txns_4q_avg
FROM q
ORDER BY year, quarter;"""},

"state_rank": {
  "title": "State ranking by YoY growth (RANK window)",
  "question": "Which states are growing fastest, and how does that compare with their size?",
  "sql": """WITH s AS (
  SELECT state, period, year, quarter, SUM(txn_count) AS txns
  FROM state_category
  GROUP BY state, period, year, quarter
),
g AS (
  SELECT state, period, txns,
         txns * 1.0 / LAG(txns, 4) OVER (PARTITION BY state ORDER BY year, quarter) - 1 AS yoy
  FROM s
)
SELECT RANK() OVER (ORDER BY yoy DESC) AS growth_rank,
       state, txns, ROUND(yoy, 3) AS yoy_growth,
       RANK() OVER (ORDER BY txns DESC) AS size_rank
FROM g
WHERE period = (SELECT MAX(period) FROM state_category)
ORDER BY growth_rank;"""},

"category_mix": {
  "title": "Category mix over time (share of quarter via window SUM)",
  "question": "Is UPI shifting from person-to-person to merchant payments?",
  "sql": """SELECT period, category, txn_count,
       ROUND(txn_count * 1.0 / SUM(txn_count) OVER (PARTITION BY period), 4) AS share
FROM (
  SELECT period, category, SUM(txn_count) AS txn_count
  FROM state_category
  GROUP BY period, category
)
ORDER BY period, category;"""},

"pareto": {
  "title": "Concentration: cumulative share of districts (running SUM)",
  "question": "How concentrated is payment activity across districts?",
  "sql": """WITH d AS (
  SELECT state, district, SUM(txn_count) AS txns
  FROM district
  WHERE period = (SELECT MAX(period) FROM district)
  GROUP BY state, district
),
r AS (
  SELECT state, district, txns,
         ROW_NUMBER() OVER (ORDER BY txns DESC) AS rnk,
         SUM(txns) OVER (ORDER BY txns DESC ROWS UNBOUNDED PRECEDING) * 1.0 / SUM(txns) OVER () AS cum_share
  FROM d
)
SELECT rnk, state, district, txns, ROUND(cum_share, 4) AS cum_share
FROM r
ORDER BY rnk;"""},

"engagement": {
  "title": "Engagement depth: transactions per registered user (join + CTE)",
  "question": "Which states have the most active users, not just the most registrations?",
  "sql": """WITH t AS (
  SELECT state, SUM(txn_count) AS txns
  FROM state_category
  WHERE period = (SELECT MAX(period) FROM state_category)
  GROUP BY state
)
SELECT t.state,
       u.registered_users,
       t.txns,
       ROUND(t.txns * 1.0 / u.registered_users, 1) AS txns_per_user
FROM t
JOIN users u ON u.state = t.state AND u.period = (SELECT MAX(period) FROM users)
ORDER BY txns_per_user DESC;"""},

"ticket_by_state": {
  "title": "Average ticket by state vs national average",
  "question": "Where do people pay more per transaction?",
  "sql": """WITH s AS (
  SELECT state, SUM(txn_amount) * 1.0 / SUM(txn_count) AS ticket
  FROM district
  WHERE period = (SELECT MAX(period) FROM district)
  GROUP BY state
)
SELECT state, ROUND(ticket, 0) AS avg_ticket_inr,
       ROUND(ticket / AVG(ticket) OVER () - 1, 3) AS vs_avg
FROM s
ORDER BY ticket DESC;"""},
}

QUERY_FILES = {"seasonal_anomaly": "sql/seasonal_anomaly.sql"}
