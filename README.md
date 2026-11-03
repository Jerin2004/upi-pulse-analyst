# 📊 UPI Pulse Analyst

**Live demo:** https://upi-pulse-analyst-pnnj8sbma3nu4dfznhghy5.streamlit.app/

**Short description:** An analytics app on PhonePe's open Pulse data (36 states/UTs, 780 districts, Q1 2018 to Q2 2026). It combines SQL analytics (window functions, CTEs, joins on a SQLite warehouse), seasonality-aware anomaly screening, a Streamlit dashboard, and a guarded natural-language-to-SQL assistant (Groq / Llama 3.3). Python, pandas, SQLite, scikit-learn, Streamlit, Docker, GitHub Actions.

## Key findings (Q2 2026)
- **Volume +24.2% YoY, value +18.4% YoY.** The average ticket is now ₹1,177 (-4.6% YoY) and has fallen every year since its Q2 2021 peak of ₹1,894 (about -38%): growth is increasingly small, frequent payments.
- **The category mix has swung.** Utility peaked at 18.6% of transactions in Q2 2021 and is now 5.4%; Retail went from 37.3% (Q2 2021) to 63.9%; P2P is 30.8%.
- **North-East states are growing fastest** (Mizoram +36%, Sikkim +34%, Assam +33% YoY) against about 17% for Rajasthan and Himachal Pradesh, which suggests a newer-adoption curve.
- **Engagement depth varies about 9x:** Telangana has about 106 transactions per registered user in the quarter vs about 12 in Manipur, so registrations alone are a weak health metric.
- **Concentration:** 85 of 780 districts (about 11%) account for half of all transactions; Bengaluru Urban alone is 5.5% of national volume.
- **Seasonality matters for anomaly detection.** A naive model flagged many Uttarakhand/Ladakh/Himachal hill districts in Q2 2026. Rudraprayag's Q2 jump has been +116% to +167% every year since 2022, so the raw flag was mostly seasonal. After adjusting for each district's own seasonal pattern, Rudraprayag is still the only strong outlier (+179% QoQ vs a usual ~+138%, robust z ≈ 10). I have not established why; that would need outside data.

## What's inside
| File | Purpose |
|---|---|
| `load_data.py` | Parses the Pulse JSON tree into tidy DataFrames |
| `db.py` | Builds a SQLite database and a read-only connection |
| `sql/queries.py` | Curated analytical SQL (LAG/RANK/running SUM windows, CTEs, joins) |
| `sql/seasonal_anomaly.sql` | Seasonally adjusted QoQ growth vs the same quarter in the previous 3 years |
| `analysis.py` | Growth, ticket size, engagement, robust-z anomaly ranking |
| `sql_ai.py` | Natural language to SQL with safety layers |
| `app.py` | Streamlit app (Trends, States & users, Anomaly screening, SQL Explorer, Ask in plain English) |
| `tests/` | pytest suite for the SQL guardrails; CI runs it on every push |

## Text-to-SQL safety design
The LLM is treated as untrusted. Generated SQL passes through (1) validation (a single SELECT/WITH, no write/DDL/PRAGMA/ATTACH, known tables only, no comments, automatic row limit), (2) a read-only SQLite connection, (3) a SQLite authorizer that only allows SELECT/READ/FUNCTION, and (4) a query time budget. The generated SQL is always shown so the user can check it.

## Run it
```bash
git clone https://github.com/PhonePe/pulse.git   # the app also does this automatically if missing
pip install -r requirements.txt
streamlit run app.py          # or: python -m streamlit run app.py
pytest -q                     # run the tests
```
To enable the AI tab, set `GROQ_API_KEY` as an environment variable or in `.streamlit/secrets.toml` (never commit it). Docker: `docker build -t upi-pulse . && docker run -p 8501:8501 upi-pulse`.

## Limitations
- Pulse data is aggregated by quarter and geography, so it cannot support user-level, funnel or fraud analysis; anomaly flags are a screening aid.
- Category definitions and coverage follow PhonePe's own methodology and may change over time.
- Text-to-SQL accuracy depends on the model; always read the SQL shown.

## Roadmap
Scheduled data refresh, forecasting with seasonal models, an evaluation set of question/SQL pairs for the assistant.
