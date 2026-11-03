https://upi-pulse-analyst-pnnj8sbma3nu4dfznhghy5.streamlit.app/
# 📊 UPI Pulse Analyst

**Short description:** An analytics dashboard on PhonePe's open Pulse data (36 states/UTs, 780 districts, 2018 to Q2 2026) covering digital payment growth, category mix, user engagement, and district-level anomaly screening. Built with Python, pandas, scikit-learn and Streamlit, and containerised with Docker. A natural-language (text-to-SQL) layer is in progress.

## Key findings (Q2 2026)
- **Volume +24.2% YoY, value +18.4% YoY**, so the average ticket is shrinking (about -4.7%): growth is coming from small, frequent payments.
- **Retail's share of transactions rose from 51.6% (Q2 2022) to 63.9%**, while Utility fell from 10.2% to 5.4% and P2P from 38.3% to 30.8%.
- **North-East states are growing fastest** (Mizoram +36%, Sikkim +34%, Assam +33% YoY) vs about 17% for Rajasthan and Himachal Pradesh, which suggests a newer-adoption curve.
- **Engagement depth varies about 9x**: Telangana has about 106 transactions per registered user in the quarter vs about 12 in Manipur, so registrations alone are a weak health metric.
- **Concentration:** the top 10 districts account for about 20% of all transactions; Bengaluru Urban alone has 2.1 B in the quarter.
- **Anomaly screening:** an Isolation Forest flags Uttarakhand/Ladakh/Himachal hill districts (e.g. Rudraprayag, +179% QoQ). The likely explanation is April-June tourist and pilgrimage seasonality, not fraud (a hypothesis to validate with year-over-year comparisons).

## Method
1. `load_data.py` parses the Pulse JSON tree into tidy DataFrames (state x category, district x amount, users).
2. `analysis.py` computes growth, mix shift, ticket size, engagement and anomaly scores.
3. `app.py` is the Streamlit dashboard.

## Run it
```bash
git clone https://github.com/PhonePe/pulse.git
pip install -r requirements.txt
streamlit run app.py
# or: docker build -t upi-pulse . && docker run -p 8501:8501 upi-pulse
```

## Limitations
Pulse data is aggregated by quarter and geography, so it can't support user-level fraud detection; anomaly flags are a screening aid. Metrics follow PhonePe's own definitions.

## Roadmap
Text-to-SQL ("which states grew fastest last year?") with read-only, schema-aware queries; year-over-year seasonality adjustment for anomalies; scheduled data refresh.
