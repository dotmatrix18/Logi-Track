"""
feature_engineering.py
----------------------
Step 7: build one analysis-ready row per shipment by joining the 7 cleaned
tables and deriving business features.

Feature definitions (documented so the KPIs are reproducible):
  delivery_hours     actual_dt - shipment_dt in hours (NULL if not delivered)
  delivery_days      delivery_hours / 24  (brief: "actual delivery time - shipment time")
  is_delayed         1 if delay_hours > 0 else 0 (NULL for In-Transit/Cancelled)
  is_completed       1 if status in (Delivered, Delayed)
  is_success         1 if status = 'Delivered'
  weight_category    Light (<50 kg) | Medium (50-500) | Heavy (500-1500) | Very Heavy (>1500)
  distance_category  Short (<500 km) | Medium (500-1000) | Long (1000-1500) | Very Long (>1500)
  experience_level   Junior (0-3 yrs) | Mid (4-7) | Senior (8-14) | Expert (15+)
  delivery_month / delivery_day_of_week / delivery_hour   from actual_dt
  shipment_month / shipment_quarter / shipment_day_of_week / shipment_hour  from shipment_dt
  capacity_utilization_pct   weight_kg / vehicle capacity_kg * 100
  delay_severity     On-time | Minor (<=6h) | Moderate (6-24h) | Severe (>24h)
  rating_category    Negative (1-2) | Neutral (3) | Positive (4-5)
  speed_kmph         distance_km / delivery_hours
  driver_join_conflict  1 if shipment_dt < driver join_date (data-quality flag)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

DAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
WEIGHT_LABELS = ["Light", "Medium", "Heavy", "Very Heavy"]
DISTANCE_LABELS = ["Short", "Medium", "Long", "Very Long"]
EXPERIENCE_LABELS = ["Junior", "Mid", "Senior", "Expert"]


def weight_category(w: pd.Series) -> pd.Series:
    return pd.cut(w, bins=[-np.inf, 50, 500, 1500, np.inf], labels=WEIGHT_LABELS, right=False)


def distance_category(km: pd.Series) -> pd.Series:
    return pd.cut(km, bins=[-np.inf, 500, 1000, 1500, np.inf], labels=DISTANCE_LABELS, right=False)


def experience_level(years: pd.Series) -> pd.Series:
    return pd.cut(years, bins=[-np.inf, 3, 7, 14, np.inf], labels=EXPERIENCE_LABELS, right=True)


def delay_severity(delay: pd.Series) -> pd.Series:
    out = pd.Series(pd.NA, index=delay.index, dtype="object")
    out[delay == 0] = "On-time"
    out[(delay > 0) & (delay <= 6)] = "Minor (<=6h)"
    out[(delay > 6) & (delay <= 24)] = "Moderate (6-24h)"
    out[delay > 24] = "Severe (>24h)"
    return out


def build_master(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Join the 7 cleaned tables (shipment grain) and rename clashing columns."""
    w = t["warehouses"].rename(columns={"name": "warehouse_name", "city": "warehouse_city",
                                         "state": "warehouse_state", "capacity": "warehouse_capacity"})
    d = t["drivers"].rename(columns={"name": "driver_name", "experience": "driver_experience",
                                      "rating": "driver_rating", "join_date": "driver_join_date"})
    v = t["vehicles"].rename(columns={"status": "vehicle_status"})
    r = t["routes"]
    de = t["deliveries"].rename(columns={"status": "delivery_status"})
    f = t["feedback"].rename(columns={"rating": "customer_rating", "comment": "feedback_comment"})

    m = (t["shipments"]
         .merge(w, on="warehouse_id", how="left")
         .merge(d, on="driver_id", how="left")
         .merge(v, on="vehicle_id", how="left")
         .merge(r, on="route_id", how="left")
         .merge(de, on="shipment_id", how="left")          # LEFT: keep shipments w/o delivery
         .merge(f, on="delivery_id", how="left"))          # LEFT: keep deliveries w/o feedback
    return m


def add_features(m: pd.DataFrame) -> pd.DataFrame:
    m = m.copy()
    for c in ["shipment_dt", "actual_dt", "feedback_dt", "driver_join_date"]:
        m[c] = pd.to_datetime(m[c], errors="coerce")

    # --- delivery time & delay -------------------------------------------------
    m["delivery_hours"] = ((m["actual_dt"] - m["shipment_dt"]).dt.total_seconds() / 3600).round(2)
    m["delivery_days"] = (m["delivery_hours"] / 24).round(3)
    m["is_completed"] = m["delivery_status"].isin(["Delivered", "Delayed"]).astype(int)
    m["is_success"] = (m["delivery_status"] == "Delivered").astype(int)
    m["is_cancelled"] = (m["delivery_status"] == "Cancelled").astype(int)
    m["is_delayed"] = np.where(m["delay_hours"].isna(), np.nan, (m["delay_hours"] > 0).astype(float))
    m["delay_severity"] = delay_severity(m["delay_hours"])

    # --- categories --------------------------------------------------------------
    m["weight_category"] = weight_category(m["weight_kg"]).astype(str)
    m["distance_category"] = distance_category(m["distance_km"]).astype(str)
    m["experience_level"] = experience_level(m["driver_experience"]).astype(str)
    m["rating_category"] = pd.cut(m["customer_rating"], bins=[0, 2, 3, 5],
                                  labels=["Negative", "Neutral", "Positive"]).astype(str).replace("nan", np.nan)

    # --- time features -----------------------------------------------------------
    m["delivery_month"] = m["actual_dt"].dt.to_period("M").astype(str).replace("NaT", np.nan)
    m["delivery_day_of_week"] = m["actual_dt"].dt.day_name()
    m["delivery_hour"] = m["actual_dt"].dt.hour
    m["shipment_month"] = m["shipment_dt"].dt.to_period("M").astype(str)
    m["shipment_month_name"] = m["shipment_dt"].dt.month_name()
    m["shipment_quarter"] = "Q" + m["shipment_dt"].dt.quarter.astype(str)
    m["shipment_year"] = m["shipment_dt"].dt.year
    m["shipment_day_of_week"] = m["shipment_dt"].dt.day_name()
    m["shipment_hour"] = m["shipment_dt"].dt.hour
    m["is_weekend"] = m["shipment_dt"].dt.dayofweek.isin([5, 6]).astype(int)

    m["route_name"] = m["origin_city"] + " -> " + m["dest_city"]

    # --- efficiency --------------------------------------------------------------
    m["capacity_utilization_pct"] = (100 * m["weight_kg"] / m["capacity_kg"]).round(2)
    m["speed_kmph"] = (m["distance_km"] / m["delivery_hours"]).round(2)
    m["feedback_lag_days"] = (m["feedback_dt"] - m["actual_dt"].dt.normalize()).dt.days

    # --- data-quality flags ------------------------------------------------------
    m["driver_join_conflict"] = (m["shipment_dt"] < m["driver_join_date"]).astype(int)
    return m


FEATURE_COLUMNS = [
    "shipment_id", "delivery_id", "feedback_id", "delivery_hours", "delivery_days", "is_completed",
    "is_success", "is_cancelled", "is_delayed", "delay_severity", "weight_category", "distance_category",
    "experience_level", "rating_category", "delivery_month", "delivery_day_of_week", "delivery_hour",
    "shipment_month", "shipment_month_name", "shipment_quarter", "shipment_year", "shipment_day_of_week",
    "shipment_hour", "is_weekend", "capacity_utilization_pct", "speed_kmph", "feedback_lag_days",
    "driver_join_conflict",
]


def build_features(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Convenience wrapper: join + engineer features (full analysis dataset)."""
    return add_features(build_master(tables))
