"""
LogiTrack: Supply Chain & Logistics Performance Dashboard (Streamlit)
=====================================================================
Run from the project root:

    streamlit run dashboard/app.py

* Connected directly to the SQL database (SQLAlchemy; URL from the
  LOGITRACK_DB_URL env var, default SQLite file data/logitrack.db).
* Every KPI and chart is produced by a SQL query loaded from
  sql/analysis_queries.sql; the sidebar filters are injected into each query
  as bound parameters, so every tab respects the selected filters.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import utils  # noqa: E402

st.set_page_config(page_title="LogiTrack Dashboard", page_icon="🚚", layout="wide")

STATUS_ORDER = ["Delivered", "Delayed", "In-Transit", "Cancelled"]
STATUS_COLORS = {"Delivered": "#1b9e77", "Delayed": "#d95f02", "In-Transit": "#7570b3", "Cancelled": "#e7298a"}
DAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
EXP_ORDER = ["Junior", "Mid", "Senior", "Expert"]


# --------------------------------------------------------------------------- #
# Data access
# --------------------------------------------------------------------------- #
@st.cache_resource
def get_engine():
    return utils.get_engine()


@st.cache_data
def load_query_library() -> dict[str, dict]:
    """Parse sql/analysis_queries.sql into {id: {title, sql}} (single source of truth)."""
    raw = (utils.SQL_DIR / "analysis_queries.sql").read_text(encoding="utf-8")
    lib = {}
    for block in re.split(r"^-- name: ", raw, flags=re.M)[1:]:
        header, body = block.split("\n", 1)
        qid, title = [p.strip() for p in header.split("|", 1)]
        body = body.split("\n-- ====")[0]  # drop trailing section banners
        lib[qid] = {"title": title, "sql": body.strip().rstrip(";")}
    return lib


@st.cache_data(show_spinner=False)
def run_sql(sql: str, params: tuple) -> pd.DataFrame:
    with get_engine().connect() as conn:
        return pd.read_sql(text(sql), conn, params=dict(params))


@st.cache_data
def filter_options() -> dict:
    q = lambda s: run_sql(s, tuple())  # noqa: E731
    return {
        "months": q("SELECT DISTINCT shipment_month AS m FROM vw_logitrack ORDER BY m")["m"].tolist(),
        "status": q("SELECT DISTINCT status AS s FROM deliveries")["s"].tolist(),
        "warehouses": q("SELECT warehouse_id, name || ' (' || city || ')' AS label FROM warehouses ORDER BY warehouse_id"),
        "route_types": q("SELECT DISTINCT route_type AS r FROM routes ORDER BY r")["r"].tolist(),
        "drivers": q("SELECT driver_id, name || ' (#' || driver_id || ')' AS label FROM drivers ORDER BY name"),
        "vehicle_types": q("SELECT DISTINCT vehicle_type AS v FROM vehicles ORDER BY v")["v"].tolist(),
    }


def in_clause(column: str, values: list, prefix: str, params: dict) -> str:
    """Build 'AND column IN (:p0, :p1 ...)' with bound parameters (no SQL injection)."""
    keys = []
    for i, v in enumerate(values):
        k = f"{prefix}{i}"
        params[k] = v
        keys.append(f":{k}")
    return f" AND {column} IN ({', '.join(keys)})"


def build_filters(sel: dict) -> tuple[str, str, tuple]:
    """Return (FILTERS clause, VFILTERS clause, params) for the current sidebar selection."""
    params: dict = {}
    clause = " AND shipment_month BETWEEN :m_start AND :m_end"
    params["m_start"], params["m_end"] = sel["months"]
    if sel["status"]:
        clause += in_clause("delivery_status", sel["status"], "st", params)
    if sel["warehouses"]:
        clause += in_clause("warehouse_id", sel["warehouses"], "wh", params)
    if sel["route_types"]:
        clause += in_clause("route_type", sel["route_types"], "rt", params)
    if sel["drivers"]:
        clause += in_clause("driver_id", sel["drivers"], "dr", params)
    vclause = ""
    if sel["vehicle_types"]:
        clause += in_clause("vehicle_type", sel["vehicle_types"], "vt", params)
        vclause = in_clause("v.vehicle_type", sel["vehicle_types"], "vv", params)
    return clause, vclause, tuple(sorted(params.items()))


def q(qid: str) -> pd.DataFrame:
    """Run a library query with the active filters."""
    sql = QUERIES[qid]["sql"].replace("/*FILTERS*/", FILTERS).replace("/*VFILTERS*/", VFILTERS)
    return run_sql(sql, PARAMS)


def fmt(v, suffix="", digits=2):
    return "–" if v is None or pd.isna(v) else f"{v:,.{digits}f}{suffix}"


# --------------------------------------------------------------------------- #
# Guard: database must exist
# --------------------------------------------------------------------------- #
if utils.get_db_url().startswith("sqlite") and not utils.DEFAULT_DB_PATH.exists():
    st.error("Database not found. Build it first from the project root:  `python -m src.pipeline`  "
             "(or run notebooks 01 and 02).")
    st.stop()

QUERIES = load_query_library()
opts = filter_options()

# --------------------------------------------------------------------------- #
# Sidebar filters
# --------------------------------------------------------------------------- #
st.sidebar.title("🚚 LogiTrack")
st.sidebar.caption("Filters apply to every KPI, chart and table in all tabs.")
months = opts["months"]
m_range = st.sidebar.select_slider("Shipment month range", options=months, value=(months[0], months[-1]))
sel_status = st.sidebar.multiselect("Delivery status", STATUS_ORDER, placeholder="All statuses")
wh_map = dict(zip(opts["warehouses"]["label"], opts["warehouses"]["warehouse_id"]))
sel_wh = st.sidebar.multiselect("Warehouse", list(wh_map), placeholder="All warehouses")
sel_rt = st.sidebar.multiselect("Route type", opts["route_types"], placeholder="All route types")
dr_map = dict(zip(opts["drivers"]["label"], opts["drivers"]["driver_id"]))
sel_dr = st.sidebar.multiselect("Driver", list(dr_map), placeholder="All drivers")
sel_vt = st.sidebar.multiselect("Vehicle type", opts["vehicle_types"], placeholder="All vehicle types")

FILTERS, VFILTERS, PARAMS = build_filters({
    "months": m_range, "status": sel_status, "warehouses": [int(wh_map[w]) for w in sel_wh],
    "route_types": sel_rt, "drivers": [int(dr_map[d]) for d in sel_dr], "vehicle_types": sel_vt,
})
st.sidebar.divider()
st.sidebar.caption(f"Database: `{get_engine().url.render_as_string(hide_password=True).split('/')[-1]}`")

# --------------------------------------------------------------------------- #
# Header + KPI cards (Business Overview data)
# --------------------------------------------------------------------------- #
st.title("LogiTrack: Supply Chain & Logistics Performance Analytics")
st.caption("Interactive analysis of 3,000 shipments across 15 warehouses, 75 drivers, 45 vehicles and 150 routes (Jan 2024 to Dec 2025).")

overview = q("q01")
ov = overview.iloc[0] if len(overview) else None
if ov is None or not ov["total_shipments"]:
    st.warning("No shipments match the current filters. Widen the selection in the sidebar.")
    st.stop()

tabs = st.tabs(["📊 Business Overview", "🚚 Delivery Analysis", "👤 Driver Performance",
                "🛣️ Vehicle & Route Analysis", "⭐ Customer Feedback", "💡 Insights", "🧾 SQL Queries"])

# ---------------- Business Overview ----------------
with tabs[0]:
    st.subheader("Business Overview")
    c = st.columns(5)
    c[0].metric("Total Deliveries", f"{int(ov['total_deliveries']):,}", help="Completed deliveries: status Delivered or Delayed")
    c[1].metric("Total Shipments", f"{int(ov['total_shipments']):,}", help="COUNT of shipments matching the filters")
    c[2].metric("Average Delay Hours", fmt(ov["avg_delay_hours"], " h"), help="AVG(delay_hours) over completed deliveries; In-Transit/Cancelled are NULL and excluded")
    c[3].metric("Average Rating", fmt(ov["avg_rating"], " / 5"), help="AVG(customer rating), valid ratings 1-5 only")
    c[4].metric("Delivery Success Rate", fmt(ov["success_rate_pct"], " %"), help="Delivered / all shipments × 100")
    c = st.columns(5)
    c[0].metric("Delivered", f"{int(ov['delivered']):,}")
    c[1].metric("Delayed", f"{int(ov['delayed']):,}")
    c[2].metric("In-Transit", f"{int(ov['in_transit']):,}")
    c[3].metric("Cancelled", f"{int(ov['cancelled']):,}")
    c[4].metric("Zero-delay share (completed)", fmt(ov["on_time_pct_of_completed"], " %"), help="delay_hours = 0 among completed deliveries")

    left, right = st.columns(2)
    status = q("s01")
    left.plotly_chart(px.pie(status, names="delivery_status", values="shipments", hole=0.45, color="delivery_status",
                             color_discrete_map=STATUS_COLORS, title="Shipment outcome mix"), width="stretch")
    monthly = q("q05")
    fig = go.Figure()
    fig.add_bar(x=monthly["month"], y=monthly["shipments"], name="Shipments", marker_color="#b0bec5")
    fig.add_scatter(x=monthly["month"], y=monthly["success_rate_pct"], name="Success rate %", yaxis="y2", mode="lines+markers", line_color="#1b9e77")
    fig.update_layout(title="Monthly volume and success rate", yaxis=dict(title="Shipments"),
                      yaxis2=dict(title="Success %", overlaying="y", side="right"), legend=dict(orientation="h", y=-0.25))
    right.plotly_chart(fig, width="stretch")
    with st.expander("KPI calculation rules"):
        st.markdown("""
| KPI | Rule | NULL / invalid handling |
|---|---|---|
| Total Shipments | `COUNT(shipment_id)` | n/a |
| Total Deliveries | `COUNT(*) WHERE status IN ('Delivered','Delayed')` | In-Transit and Cancelled are not deliveries |
| Average Delay Hours | `AVG(delay_hours)` | NULL for In-Transit/Cancelled, so `AVG` ignores them |
| Average Rating | `AVG(rating) WHERE rating BETWEEN 1 AND 5` | invalid ratings are cleaned upstream and excluded |
| Delivery Success Rate | `Delivered / total shipments × 100` | `NULLIF` guards against divide-by-zero |
""")

# ---------------- Delivery Analysis ----------------
with tabs[1]:
    st.subheader("Delivery Analysis")
    a, b = st.columns(2)
    status["delivery_status"] = pd.Categorical(status["delivery_status"], STATUS_ORDER, ordered=True)
    a.plotly_chart(px.bar(status.sort_values("delivery_status"), x="delivery_status", y="shipments", color="delivery_status",
                          color_discrete_map=STATUS_COLORS, text="shipments", title="Delivery status distribution"), width="stretch")
    rt = q("q02")
    b.plotly_chart(px.bar(rt, x="route_type", y="avg_delay_hours", color="route_type", text="avg_delay_hours",
                          hover_data=["shipments", "delayed_status_pct", "avg_distance_km"],
                          title="Average delay by route type (hours)"), width="stretch")
    fig = px.line(monthly, x="month", y=["delivered", "delayed"], markers=True, title="Monthly delivery trends",
                  color_discrete_map={"delivered": STATUS_COLORS["Delivered"], "delayed": STATUS_COLORS["Delayed"]})
    fig.add_scatter(x=monthly["month"], y=monthly["avg_delay_hours"], name="avg delay (h)", yaxis="y2", line=dict(dash="dot", color="black"))
    fig.update_layout(yaxis=dict(title="Shipments"), yaxis2=dict(title="Avg delay (h)", overlaying="y", side="right"), legend=dict(orientation="h", y=-0.25))
    st.plotly_chart(fig, width="stretch")
    wh = q("q04")
    wh["warehouse"] = wh["warehouse_name"] + " (" + wh["city"] + ")"
    a, b = st.columns(2)
    a.plotly_chart(px.bar(wh.sort_values("avg_delay_hours"), x="avg_delay_hours", y="warehouse", orientation="h",
                          color="avg_delay_hours", color_continuous_scale="Reds", title="Average delay by warehouse (hours)"), width="stretch")
    b.plotly_chart(px.bar(wh.sort_values("success_rate_pct"), x="success_rate_pct", y="warehouse", orientation="h",
                          color="success_rate_pct", color_continuous_scale="Greens", title="Success rate by warehouse (%)"), width="stretch")
    a, b = st.columns(2)
    heat = q("s08").pivot(index="warehouse", columns="shipment_quarter", values="avg_delay_hours")
    a.plotly_chart(px.imshow(heat, text_auto=".1f", color_continuous_scale="Reds", aspect="auto", title="Delay heatmap: warehouse × quarter (h)"), width="stretch")
    dow = q("q10")
    b.plotly_chart(px.bar(dow, x="day_of_week", y="avg_delay_hours", text="avg_delay_hours", color="success_rate_pct",
                          color_continuous_scale="RdYlGn", title="Day-of-week analysis (avg delay, coloured by success %)"), width="stretch")
    st.markdown("**Delay analysis by distance category**")
    st.dataframe(q("q08"), width="stretch", hide_index=True)

# ---------------- Driver Performance ----------------
with tabs[2]:
    st.subheader("Driver Performance")
    top = q("q03")
    a, b = st.columns([3, 2])
    top["driver"] = top["driver_name"] + " (#" + top["driver_id"].astype(str) + ")"
    fig = px.bar(top, x="avg_customer_rating", y="driver", orientation="h",
                 color="experience_level", text="avg_customer_rating", hover_data=["shipments", "avg_delay_hours", "success_rate_pct"],
                 category_orders={"experience_level": EXP_ORDER}, title="Top 10 drivers by customer rating (min 5 shipments)")
    fig.update_yaxes(categoryorder="total ascending")      # best driver on top regardless of colour group
    a.plotly_chart(fig, width="stretch")
    b.dataframe(top[["rating_rank", "driver_name", "experience_level", "shipments", "avg_customer_rating", "avg_delay_hours", "success_rate_pct"]],
                width="stretch", hide_index=True)
    work = q("s03")
    exp = q("q09")
    a, b = st.columns(2)
    fig = px.scatter(work, x="driver_experience", y="avg_delay_hours", size="shipments", color="avg_rating",
                     color_continuous_scale="RdYlGn", hover_name="driver_name",
                     title="Driver experience vs performance (bubble = workload, colour = rating)")
    fit = work.dropna(subset=["driver_experience", "avg_delay_hours"])
    if len(fit) > 2 and fit["driver_experience"].nunique() > 1:   # simple least-squares trend line
        slope, intercept = np.polyfit(fit["driver_experience"], fit["avg_delay_hours"], 1)
        xs = np.array([fit["driver_experience"].min(), fit["driver_experience"].max()])
        fig.add_scatter(x=xs, y=slope * xs + intercept, mode="lines", name=f"trend ({slope:+.2f} h/yr)", line=dict(color="black", dash="dash"))
    a.plotly_chart(fig, width="stretch")
    fig = go.Figure()
    fig.add_bar(x=exp["experience_level"], y=exp["avg_delay_hours"], name="Avg delay (h)", marker_color="#d95f02")
    fig.add_scatter(x=exp["experience_level"], y=exp["avg_success_rate_pct"], name="Success %", yaxis="y2", mode="lines+markers", line_color="#1b9e77")
    fig.update_layout(title="Performance by experience level", yaxis=dict(title="Avg delay (h)"),
                      yaxis2=dict(title="Success %", overlaying="y", side="right"), legend=dict(orientation="h", y=-0.2))
    b.plotly_chart(fig, width="stretch")
    a, b = st.columns(2)
    a.plotly_chart(px.histogram(work, x="shipments", nbins=20, title="Driver workload distribution (shipments per driver)",
                                color_discrete_sequence=["#7570b3"]), width="stretch")
    b.plotly_chart(px.box(work, x="experience_level", y="shipments", points="all", category_orders={"experience_level": EXP_ORDER},
                          title="Workload by experience level"), width="stretch")
    st.markdown("**Driver performance by experience level**")
    st.dataframe(exp, width="stretch", hide_index=True)

# ---------------- Vehicle & Route Analysis ----------------
with tabs[3]:
    st.subheader("Vehicle & Route Analysis")
    veh = q("q06")
    a, b = st.columns(2)
    a.plotly_chart(px.bar(veh, x="vehicle_type", y="avg_capacity_utilization_pct", color="vehicle_type", text="avg_capacity_utilization_pct",
                          hover_data=["vehicles", "idle_vehicles", "shipments_per_vehicle", "avg_delay_hours"],
                          title="Vehicle utilisation: average load as % of capacity"), width="stretch")
    fig = go.Figure()
    fig.add_bar(x=veh["vehicle_type"], y=veh["shipments_per_vehicle"], name="Shipments per vehicle", marker_color="#66c2a5")
    fig.add_bar(x=veh["vehicle_type"], y=veh["idle_vehicles"], name="Idle vehicles", marker_color="#fc8d62")
    fig.update_layout(barmode="group", title="Fleet usage: shipments per vehicle and idle vehicles")
    b.plotly_chart(fig, width="stretch")
    st.dataframe(veh, width="stretch", hide_index=True)
    routes = q("s02")
    a, b = st.columns(2)
    fig = px.bar(routes.head(10), x="avg_delay_hours", y="route_name", orientation="h", color="route_type",
                 hover_data=["shipments", "success_rate_pct", "distance_km"], title="Route performance: 10 most-delayed lanes (≥5 shipments)")
    fig.update_yaxes(categoryorder="total ascending")
    a.plotly_chart(fig, width="stretch")
    fig = px.bar(routes.tail(10), x="avg_delay_hours", y="route_name", orientation="h", color="route_type",
                 hover_data=["shipments", "success_rate_pct", "distance_km"], title="Route performance: 10 best lanes (lowest delay)")
    fig.update_yaxes(categoryorder="total descending")
    b.plotly_chart(fig, width="stretch")
    dist = q("s04")
    a, b = st.columns(2)
    a.plotly_chart(px.scatter(dist, x="distance_km", y="delay_hours", color="route_type", opacity=0.5,
                              title="Distance vs delay (each dot = completed delivery)"), width="stretch")
    a.caption(f"Pearson r (current filter) = {dist['distance_km'].corr(dist['delay_hours']):.3f}" if len(dist) > 2 else "")
    b.plotly_chart(px.box(dist, x="distance_category", y="delay_hours", color="distance_category",
                          category_orders={"distance_category": ["Short", "Medium", "Long", "Very Long"]},
                          title="Delay distribution by distance category"), width="stretch")

# ---------------- Customer Feedback ----------------
with tabs[4]:
    st.subheader("Customer Feedback")
    a, b = st.columns(2)
    rd = q("s05")
    a.plotly_chart(px.bar(rd, x="rating", y="feedback_count", text="feedback_count", color="rating", color_continuous_scale="RdYlGn",
                          title="Rating distribution"), width="stretch")
    rs = q("q07")
    b.plotly_chart(px.bar(rs, x="delivery_status", y="avg_rating", text="avg_rating", color="delivery_status", color_discrete_map=STATUS_COLORS,
                          hover_data=["feedback_count", "positive_pct", "negative_pct"], title="Average rating by delivery status"), width="stretch")
    trend = q("s06")
    fig = px.line(trend, x="month", y="avg_rating", markers=True, title="Rating trends over time (avg rating by shipment month)")
    fig.add_hline(y=4.0, line_dash="dash", line_color="red", annotation_text="Target 4.0")
    st.plotly_chart(fig, width="stretch")
    a, b = st.columns(2)
    sev = q("s07")
    a.plotly_chart(px.bar(sev, x="delay_severity", y="avg_rating", text="avg_rating", color="avg_rating", color_continuous_scale="RdYlGn",
                          title="Impact of delay on rating"), width="stretch")
    b.plotly_chart(px.area(trend, x="month", y=["positive_pct", "negative_pct"], title="Positive (4-5★) vs negative (1-2★) share %"),
                   width="stretch")

# ---------------- Insights ----------------
with tabs[5]:
    st.subheader("Business Insights & Recommendations")
    st.caption("Headline figures are for the full dataset (see reports/Business_Insights_Report.md). The live values reflect the current filters.")
    k = st.columns(3)
    k[0].metric("Success rate (filtered)", fmt(ov["success_rate_pct"], " %"))
    k[1].metric("Avg rating (filtered)", fmt(ov["avg_rating"]), delta=None if pd.isna(ov["avg_rating"]) else f"{ov['avg_rating'] - 4.0:+.2f} vs 4.0 target")
    k[2].metric("Avg delay (filtered)", fmt(ov["avg_delay_hours"], " h"))
    st.markdown("""
| # | Observation | Interpretation | Business impact / action |
|---|---|---|---|
| 1 | 74.4% of shipments are *Delivered*; 16% Delayed, 9.6% never completed (In-Transit/Cancelled). | About 1 in 4 orders misses the promise. | Set a 80% success-rate target; daily exception report for In-Transit > 72 h. |
| 2 | Rating falls from **4.58 (on time) to 2.84 (> 24 h late)**; delay vs rating r = −0.59. Cancelled/In-Transit ≈ 2 stars. | Punctuality is the main lever on satisfaction. | Proactive delay alerts, compensation for > 24 h delays, cut cancellations. |
| 3 | Mean rating 3.89 is **significantly below the 4.0 target** (p < 0.001), but completed orders average 4.10. | The gap is caused by failed and severely late orders, not by routine service. | Focus on the bottom 10% of orders (cancelled + severe delays). |
| 4 | Distance does not explain delay (r = −0.03); specific lanes do (Ahmedabad→Delhi 14 h, Kolkata→Ahmedabad 13 h, Delhi→Hyderabad 47% delayed). | Delays come from operational bottlenecks, not kilometres. | Lane-level root-cause review, buffer scheduling on the top-10 delayed lanes. |
| 5 | Jaipur (67%) and Nagpur (69%) hubs trail Delhi/Patna/Lucknow (≈78%); Kochi and Ahmedabad are over-represented in extreme delays. | Hub execution varies (statistically weak overall, p = 0.42), so monitor before acting. | Hub scorecards; share best practice from top hubs. |
| 6 | Junior drivers average 7.7 h delay vs 6.8 h for Senior/Expert; rating difference is small. | Experience helps punctuality a little. | Pair juniors with experts on the worst lanes; recognise top-10 drivers. |
| 7 | Bikes: lowest delay (6.5 h), highest utilisation (54%). Trucks: most delay (7.5 h), 45% utilisation; 4 vehicles idle (maintenance/retired). | Truck capacity is under-used. | Consolidate truck loads, right-size the fleet, schedule maintenance off-peak. |
| 8 | Monday dispatches are slowest (8.1 h vs ≈6.8 h); delay spikes in Mar-24, Dec-24, Apr/May-25. | Weekend backlog and peak-season pressure. | Extra Monday capacity and seasonal staffing plans. |
""")

# ---------------- SQL Queries ----------------
with tabs[6]:
    st.subheader("The 10 key SQL queries behind this dashboard")
    st.caption("Loaded from `sql/analysis_queries.sql`. `/*FILTERS*/` is replaced with your sidebar filters as bound parameters; the live result is shown under each query.")
    with st.expander("Active filter clause"):
        st.code(f"FILTERS  -> WHERE 1=1{FILTERS}\nVFILTERS -> WHERE 1=1{VFILTERS}\nparams   -> {dict(PARAMS)}", language="sql")
    for qid in [f"q{i:02d}" for i in range(1, 11)]:
        with st.expander(QUERIES[qid]["title"], expanded=(qid == "q01")):
            st.code(QUERIES[qid]["sql"], language="sql")
            st.dataframe(q(qid), width="stretch", hide_index=True)

st.divider()
st.caption("LogiTrack · Built by Adrish Manna · Python · Pandas · SQL (SQLite via SQLAlchemy) · Streamlit · Plotly")
