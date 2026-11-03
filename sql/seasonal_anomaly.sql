-- Seasonally adjusted district anomalies.
-- For every district/quarter: QoQ growth vs the average QoQ growth of the SAME quarter in the previous 3 years (limits distortion from early-adoption years).
WITH g AS (
  SELECT state, district, year, quarter, period, txn_count,
         txn_count * 1.0 / LAG(txn_count) OVER w - 1 AS qoq
  FROM district
  WINDOW w AS (PARTITION BY state, district ORDER BY year, quarter)
),
s AS (
  SELECT *,
         AVG(qoq) OVER (PARTITION BY state, district, quarter ORDER BY year
                        ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) AS seasonal_qoq,
         COUNT(qoq) OVER (PARTITION BY state, district, quarter ORDER BY year
                        ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) AS n_prior
  FROM g
)
SELECT state, district, year, quarter, period, txn_count, qoq, seasonal_qoq,
       qoq - seasonal_qoq AS excess_qoq
FROM s
WHERE n_prior = 3 AND txn_count > 1000000;
