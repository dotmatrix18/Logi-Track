# LogiTrack: Supply Chain & Logistics Performance Analytics

End-to-end logistics analytics project (HCL GUVI Data Science mini project, **Adrish Manna**, batch DSGA-C-WE-E-B15).
Raw CSVs → data-quality analysis → cleaning → SQL database with PK/FK constraints → feature engineering → EDA → hypothesis testing → SQL-driven Streamlit dashboard → business insights.

**Skills:** Python · Pandas · SQL (SQLite via SQLAlchemy) · EDA · Statistics (SciPy) · Data visualisation (Matplotlib/Seaborn/Plotly) · Streamlit · Business analysis

---

## 1. Objective
Analyse 7 related logistics datasets to understand **delivery performance, driver efficiency, vehicle utilisation, route efficiency and customer satisfaction**, and turn the findings into actionable recommendations. Key business questions:

1. What is the overall delivery success rate?
2. Which routes have the most delays?
3. How does driver experience affect delivery performance?
4. Which vehicle types are most efficient?
5. What factors influence customer satisfaction?
6. Are there seasonal patterns in delivery delays?
7. Which warehouses have the best performance?

## 2. Dataset
These are the official GUVI files, downloaded from the Google Drive links in the project brief (`logitrack_*_expanded.csv`). They are stored in `data/raw/` under the file names from the recommended directory structure.

| Table | Rows | Primary key | Foreign keys |
|---|---|---|---|
| warehouses | 15 | warehouse_id | n/a |
| drivers | 75 | driver_id | n/a |
| vehicles | 45 | vehicle_id | n/a |
| routes | 150 | route_id | n/a |
| shipments | 3,000 | shipment_id | warehouse_id, driver_id, vehicle_id, route_id |
| deliveries | 3,000 | delivery_id | shipment_id (1:1) |
| feedback | 3,000 | feedback_id | delivery_id (1:1) |

> The brief's summary table quotes 10/50/30/90/2,000 rows. Those counts belong to an older, smaller version of the files. The brief's dataset section names the `_expanded` files, which are the complete and consistent 7-table set, so the expanded version is used here. Shipments run from Jan 2024 to Dec 2025.

ER diagram and data dictionary: see `notebooks/01_data_cleaning.ipynb` (Step 2) and `sql/schema.sql`.

## 3. Project structure
```
LogiTrack/
├── data/
│   ├── raw/                         # official GUVI CSVs (logitrack_<table>.csv)
│   ├── cleaned/                     # <table>_cleaned.csv + logitrack_master_features.csv
│   └── logitrack.db                 # SQLite database (generated)
├── notebooks/                       # executed notebooks (outputs saved)
│   ├── 01_data_cleaning.ipynb       # Steps 1-6: business problem, ER, load, quality, cleaning, SQL load
│   ├── 02_feature_engineering.ipynb # Step 7
│   ├── 03_eda.ipynb                 # Step 8
│   ├── 04_statistical_analysis.ipynb# Step 9: 5 tests (+3 supporting)
│   └── 05_sql_analysis.ipynb        # Step 10 (SQL): the 10 business queries with insights
├── sql/
│   ├── schema.sql                   # tables + PK/FK/CHECK constraints, indexes, vw_logitrack view
│   └── analysis_queries.sql         # 10 business queries + dashboard support queries
├── dashboard/
│   └── app.py                       # Streamlit dashboard (Step 10)
├── src/
│   ├── data_cleaning.py             # quality checks + cleaning rules
│   ├── feature_engineering.py       # joins + engineered features
│   ├── utils.py                     # paths, DB connection (env var), schema/load helpers
│   └── pipeline.py                  # one-command rebuild of cleaned data + database
├── reports/
│   ├── Business_Insights_Report.md  # Step 11: insights and recommendations
│   ├── statistical_test_results.csv
│   ├── delay_outliers_zscore.csv
│   ├── figures/                     # all EDA/statistics charts (PNG)
│   └── dashboard_screenshots/
├── presentation/
│   ├── LogiTrack_Presentation.pptx  # 15-slide final presentation (also as PDF)
│   └── LogiTrack_Presentation.pdf
├── tests/test_dashboard_smoke.py    # headless Streamlit smoke tests
├── requirements.txt
├── .env.example                     # how to point to another DB without hard-coding credentials
└── README.md
```

## 4. Setup & run
```bash
# 1) create an environment (Python 3.10+; tested on 3.13)
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2) (re)build cleaned data + SQLite database. The DB is already included, so this step is optional
python -m src.pipeline

# 3) launch the dashboard (run from the project root)
streamlit run dashboard/app.py       # opens http://localhost:8501

# 4) re-run the notebooks (optional)
jupyter notebook notebooks/          # run 01 → 05 in order

# 5) smoke-test the dashboard headlessly (optional)
python tests/test_dashboard_smoke.py
```
**Database connection.** `src/utils.get_engine()` reads the SQLAlchemy URL from the `LOGITRACK_DB_URL` environment variable, so no credentials are hard-coded. If the variable is not set, it uses `sqlite:///data/logitrack.db`. To use MySQL, `pip install pymysql` and set, for example, `export LOGITRACK_DB_URL="mysql+pymysql://<user>:<password>@localhost/logitrack"`. `schema.sql` is written in SQLite dialect, so for MySQL replace the `||` concatenation in the view with `CONCAT()`.

## 5. Methodology (11 steps)
| Step | What was done | Where |
|---|---|---|
| 1 Business problem | Stakeholders, objectives, 7 key questions | NB01 |
| 2 Dataset & ER | 7 tables, PK/FK, relationships, data dictionary | NB01, `schema.sql` |
| 3 Load raw data | Pandas load, shape, dtypes, structure overview | NB01 |
| 4 Data quality | Missing values, duplicates, PK uniqueness, types, invalid categories, ranges, IQR outliers, 19 cross-table rule checks | NB01, `src/data_cleaning.py` |
| 5 Cleaning | Text/casing normalisation, category mapping, type conversion, de-duplication, range checks, imputation, business-rule fixes, FK cascade. Also tested on a deliberately corrupted copy of the data | NB01 |
| 6 SQL storage | SQLAlchemy connection, `schema.sql` (PK/FK/CHECK), load in parent→child order, verification, FK-violation test | NB01 |
| 7 Feature engineering | delivery_days, is_delayed, weight/distance/experience categories, month/day/hour, quarter, delay severity, capacity utilisation, speed, rating category | NB02, `src/feature_engineering.py` |
| 8 EDA | Univariate, bivariate, multivariate, trend, correlation and distribution analysis (15 saved chart panels) | NB03 |
| 9 Statistics | Paired t, one-sample t, Pearson, Spearman, Z-score (+ Welch t, Pearson delay-rating, χ²) | NB04 |
| 10 SQL & dashboard | 10 business queries (CTEs, joins, subqueries, window functions); Streamlit with 6 sidebar filters applied to every tab | NB05, `sql/`, `dashboard/app.py` |
| 11 Insights | Observation → Interpretation → Business impact | `reports/Business_Insights_Report.md`, dashboard "Insights" tab |

### Data-quality decisions
* **288 In-Transit/Cancelled deliveries** had a delivery timestamp and `delay_hours = 0`. Both were set to **NULL**, because the order was never delivered and the delay is undefined. SQL `AVG()` therefore excludes them and the delay KPIs are not understated.
* **1,457 "Delivered" rows have delay > 0** (up to about 20 h). Following the brief, `is_delayed = delay_hours > 0`, and the status column is kept for the success-rate KPI.
* **252 shipments are dated before the driver's join date.** They are kept and flagged as `driver_join_conflict`.
* IQR outliers in weight (73) and delay (324) are real business variation. They are kept and analysed with Z-scores.

### KPI rules (dashboard and SQL)
| KPI | Rule |
|---|---|
| Total Shipments | `COUNT(shipment_id)` |
| Total Deliveries | completed deliveries: status ∈ {Delivered, Delayed} |
| Delivery Success Rate | Delivered / all shipments × 100 |
| Average Delay Hours | `AVG(delay_hours)` over completed deliveries (NULLs ignored) |
| Average Rating | `AVG(rating)` for ratings 1-5 |

## 6. Dashboard
`streamlit run dashboard/app.py`
* **Sidebar filters:** shipment month range, delivery status, warehouse, route type, driver, vehicle type. They are injected into every SQL query as bound parameters, so **all KPIs and charts in every tab** update together.
* **Tabs:** Business Overview (5 KPI cards and more) · Delivery Analysis (status distribution, delay by route type, monthly trends, delay by warehouse, warehouse×quarter heatmap, day-of-week) · Driver Performance (top 10 by rating, experience vs performance, workload distribution) · Vehicle & Route Analysis (utilisation, fleet usage, best/worst lanes, distance vs delay) · Customer Feedback (rating distribution, rating by status, rating trend vs the 4.0 target, delay impact) · Insights · **SQL Queries** (the 10 queries, run live with the current filters).
* Queries are loaded from `sql/analysis_queries.sql`, so the dashboard, NB05 and the SQL file always match.

## 7. Key findings
| # | Finding |
|---|---|
| 1 | **Success rate 74.4%** (Delivered). 16.0% Delayed, 4.9% In-Transit, 4.7% Cancelled. Only 28.6% of completed deliveries have zero delay. Average delay 7.08 h (median 3.2 h). |
| 2 | **Delays drive satisfaction:** rating falls from 4.58 (on time) to 2.84 (> 24 h late). Delay vs rating r = −0.59; Cohen's d = 0.93. Cancelled and In-Transit orders get about 2★. |
| 3 | Average rating **3.89 is significantly below the 4.0 target** (t = −5.53, p < 0.001). Completed orders alone average 4.10, so failed and late orders cause the gap. |
| 4 | **Distance does not explain delay** (Pearson r = −0.03, p = 0.11), and route types are similar (6.9-7.4 h). Specific lanes are the problem: Ahmedabad→Delhi 14.1 h, Kolkata→Ahmedabad 13.2 h, Delhi→Hyderabad 12.8 h (47% Delayed). |
| 5 | Driver experience trims delay slightly (Junior 7.7 h vs Expert 6.8 h) but does **not** affect rating (Spearman ρ = 0.03, p = 0.10). Q1 vs Q2 delivery time for the same drivers did not change (paired t p = 0.56). |
| 6 | **Bikes** are the most efficient (lowest delay 6.5 h, 54% load factor). **Trucks** have the most delay (7.5 h) and only 45% utilisation while moving 82% of the weight. 4 of 45 vehicles are idle. |
| 7 | Best hubs: Delhi, Patna, Lucknow, Chandigarh (about 78% success). Weakest: Jaipur (67%) and Nagpur (69%) (χ² p = 0.42, so a watch-list). Delay spikes in Mar-24, Dec-24 and Apr/May-25, and Monday dispatches are the slowest (8.1 h). |
| 8 | 90 extreme delays (|Z| > 3, > 39 h) average 2.8★ and are over-represented at the Kochi and Ahmedabad hubs. |

**Recommendations:** proactive delay alerts and compensation for delays over 24 h; root-cause fixes on the top-10 delayed lanes and realistic Express SLAs; scorecards for the Jaipur and Nagpur hubs; extra Monday and peak-month capacity; pairing juniors with experts; truck load consolidation and maintenance in off-peak months. Full detail is in `reports/Business_Insights_Report.md`.

## 8. Notes
* Version control: initialise Git in this folder (`git init`) and commit regularly. `.gitignore` excludes the generated DB, `.env` and caches.
* Reproducibility: `python -m src.pipeline` rebuilds everything from `data/raw/`, and the notebooks can be re-run top to bottom.
