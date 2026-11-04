"""
data_cleaning.py
----------------
Step 4 (Data Quality Analysis) and Step 5 (Data Cleaning & Preprocessing).

Design:
  * ``quality_report``      -> per-table checks (nulls, duplicates, PK uniqueness,
                               invalid categories, out-of-range numbers, outliers)
  * ``cross_table_checks``  -> relationship / business-logic checks (orphan FKs,
                               delivery before shipment, overweight loads, ...)
  * ``clean_all``           -> applies the cleaning rules to every table and returns
                               the cleaned tables plus a log of every action taken.

All rules are written defensively so the same pipeline works on the official
GUVI files *and* on any messier refresh of them (whitespace, casing variants,
duplicate rows, missing values, bad dates, negative numbers, orphan keys ...).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------- #
# Expected schema (from the project brief data dictionary)
# --------------------------------------------------------------------------- #
SCHEMA = {
    "warehouses": {"warehouse_id": "int", "name": "str", "city": "str", "state": "str", "capacity": "int"},
    "drivers": {"driver_id": "int", "name": "str", "experience": "int", "rating": "float", "join_date": "date"},
    "vehicles": {"vehicle_id": "int", "vehicle_type": "str", "capacity_kg": "int", "fuel_type": "str", "status": "str"},
    "routes": {"route_id": "int", "origin_city": "str", "dest_city": "str", "distance_km": "float", "route_type": "str"},
    "shipments": {
        "shipment_id": "int", "warehouse_id": "int", "driver_id": "int", "vehicle_id": "int",
        "route_id": "int", "shipment_dt": "datetime", "weight_kg": "float", "priority": "str",
    },
    "deliveries": {"delivery_id": "int", "shipment_id": "int", "actual_dt": "datetime", "status": "str", "delay_hours": "float"},
    "feedback": {"feedback_id": "int", "delivery_id": "int", "rating": "int", "comment": "str", "feedback_dt": "date"},
}

PK = {t: list(cols)[0] for t, cols in SCHEMA.items()}

# Allowed values for categorical columns (canonical spelling)
ALLOWED = {
    ("vehicles", "vehicle_type"): ["Truck", "Van", "Bike"],
    ("vehicles", "fuel_type"): ["Diesel", "Petrol", "Electric"],
    ("vehicles", "status"): ["Active", "Maintenance", "Retired"],
    ("routes", "route_type"): ["Express", "Standard", "Economy"],
    ("shipments", "priority"): ["High", "Medium", "Low"],
    ("deliveries", "status"): ["Delivered", "Delayed", "In-Transit", "Cancelled"],
}

# Valid numeric ranges (inclusive). None = open bound.
RANGES = {
    ("warehouses", "capacity"): (1, None),
    ("drivers", "experience"): (0, 50),
    ("drivers", "rating"): (1, 5),
    ("vehicles", "capacity_kg"): (1, None),
    ("routes", "distance_km"): (1, None),
    ("shipments", "weight_kg"): (0.01, None),
    ("deliveries", "delay_hours"): (0, None),
    ("feedback", "rating"): (1, 5),
}

COMPLETED_STATUSES = ["Delivered", "Delayed"]   # shipments that actually reached the customer


# --------------------------------------------------------------------------- #
# Step 4: data quality analysis
# --------------------------------------------------------------------------- #
def _iqr_outliers(s: pd.Series) -> int:
    s = pd.to_numeric(s, errors="coerce").dropna()
    if s.empty:
        return 0
    q1, q3 = s.quantile([0.25, 0.75])
    iqr = q3 - q1
    return int(((s < q1 - 1.5 * iqr) | (s > q3 + 1.5 * iqr)).sum())


def quality_report(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Return one row per table/column with the main data-quality indicators."""
    rows = []
    for t, df in tables.items():
        pk = PK[t]
        for col, kind in SCHEMA[t].items():
            s = df[col] if col in df.columns else pd.Series(dtype=object)
            row = {
                "table": t, "column": col, "expected_type": kind, "actual_dtype": str(s.dtype),
                "missing": int(s.isna().sum()),
                "missing_pct": round(100 * s.isna().mean(), 2) if len(s) else 0.0,
                "unique": int(s.nunique()),
                "invalid_type": 0, "invalid_category": 0, "out_of_range": 0, "iqr_outliers": 0,
            }
            if kind in ("int", "float"):
                num = pd.to_numeric(s, errors="coerce")
                row["invalid_type"] = int((num.isna() & s.notna()).sum())
                if (t, col) in RANGES:
                    lo, hi = RANGES[(t, col)]
                    bad = pd.Series(False, index=num.index)
                    if lo is not None:
                        bad |= num < lo
                    if hi is not None:
                        bad |= num > hi
                    row["out_of_range"] = int(bad.sum())
                if not col.endswith("_id"):
                    row["iqr_outliers"] = _iqr_outliers(num)
            elif kind in ("date", "datetime"):
                parsed = pd.to_datetime(s, errors="coerce")
                row["invalid_type"] = int((parsed.isna() & s.notna()).sum())
            if (t, col) in ALLOWED:
                row["invalid_category"] = int((~s.dropna().isin(ALLOWED[(t, col)])).sum())
            if col == pk:
                row["pk_duplicates"] = int(s.duplicated().sum())
            rows.append(row)
    rep = pd.DataFrame(rows)
    rep["pk_duplicates"] = rep["pk_duplicates"].fillna(0).astype(int)
    return rep


def table_summary(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Shape, duplicate rows and PK uniqueness per table."""
    return pd.DataFrame(
        [
            {
                "table": t, "rows": len(df), "columns": df.shape[1],
                "duplicate_rows": int(df.duplicated().sum()),
                "pk_unique": bool(df[PK[t]].is_unique),
                "total_missing": int(df.isna().sum().sum()),
            }
            for t, df in tables.items()
        ]
    )


def cross_table_checks(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Relationship and business-rule checks across tables."""
    w, d, v, r = tables["warehouses"], tables["drivers"], tables["vehicles"], tables["routes"]
    s, de, f = tables["shipments"], tables["deliveries"], tables["feedback"]
    sdt = pd.to_datetime(s["shipment_dt"], errors="coerce")
    checks = []

    def add(name, n, note):
        checks.append({"check": name, "violations": int(n), "note": note})

    # Orphan foreign keys
    add("shipments.warehouse_id not in warehouses", (~s["warehouse_id"].isin(w["warehouse_id"])).sum(), "FK integrity")
    add("shipments.driver_id not in drivers", (~s["driver_id"].isin(d["driver_id"])).sum(), "FK integrity")
    add("shipments.vehicle_id not in vehicles", (~s["vehicle_id"].isin(v["vehicle_id"])).sum(), "FK integrity")
    add("shipments.route_id not in routes", (~s["route_id"].isin(r["route_id"])).sum(), "FK integrity")
    add("deliveries.shipment_id not in shipments", (~de["shipment_id"].isin(s["shipment_id"])).sum(), "FK integrity")
    add("feedback.delivery_id not in deliveries", (~f["delivery_id"].isin(de["delivery_id"])).sum(), "FK integrity")
    add("shipments with >1 delivery record", de["shipment_id"].duplicated().sum(), "expected 1:1")
    add("deliveries with >1 feedback record", f["delivery_id"].duplicated().sum(), "expected 1:1")

    # Business logic
    m = de.merge(s, on="shipment_id", how="left")
    adt = pd.to_datetime(m["actual_dt"], errors="coerce")
    add("actual_dt earlier than shipment_dt", (adt < pd.to_datetime(m["shipment_dt"], errors="coerce")).sum(), "impossible timeline")
    add("In-Transit/Cancelled rows that carry an actual_dt",
        (m["status"].isin(["In-Transit", "Cancelled"]) & m["actual_dt"].notna()).sum(),
        "not delivered yet / never delivered -> actual_dt is not meaningful")
    add("status 'Delayed' but delay_hours = 0", ((m["status"] == "Delayed") & (m["delay_hours"] <= 0)).sum(), "status vs delay mismatch")
    add("status 'Delivered' but delay_hours > 0", ((m["status"] == "Delivered") & (m["delay_hours"] > 0)).sum(),
        "minor delays still labelled Delivered (within grace) -> is_delayed feature uses delay_hours > 0")
    mv = s.merge(v, on="vehicle_id", how="left")
    add("weight_kg greater than vehicle capacity_kg", (mv["weight_kg"] > mv["capacity_kg"]).sum(), "overloaded vehicle")
    add("shipments assigned to Retired/Maintenance vehicles", mv["status"].isin(["Retired", "Maintenance"]).sum(), "fleet status")
    md = s.merge(d, on="driver_id", how="left")
    add("shipment_dt before the driver's join_date",
        (pd.to_datetime(md["shipment_dt"], errors="coerce") < pd.to_datetime(md["join_date"], errors="coerce")).sum(),
        "driver assigned before joining -> flagged, kept")
    add("routes with origin_city = dest_city", (r["origin_city"] == r["dest_city"]).sum(), "invalid route")
    mf = f.merge(de, on="delivery_id", how="left")
    add("feedback_dt earlier than delivery date",
        (pd.to_datetime(mf["feedback_dt"], errors="coerce") < pd.to_datetime(mf["actual_dt"], errors="coerce").dt.normalize()).sum(),
        "feedback before delivery")
    add("feedback on In-Transit/Cancelled deliveries", mf["status"].isin(["In-Transit", "Cancelled"]).sum(),
        "customers can still rate a cancelled/pending order -> kept")
    add("future shipment dates (after today)", (sdt > pd.Timestamp.today()).sum(), "invalid date")
    return pd.DataFrame(checks)


# --------------------------------------------------------------------------- #
# Step 5: cleaning
# --------------------------------------------------------------------------- #
@dataclass
class CleaningLog:
    entries: list = field(default_factory=list)

    def add(self, table: str, action: str, rows_affected: int):
        self.entries.append({"table": table, "action": action, "rows_affected": int(rows_affected)})

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.entries, columns=["table", "action", "rows_affected"])


def _standardize_text(df: pd.DataFrame, t: str, log: CleaningLog) -> pd.DataFrame:
    """Trim whitespace, collapse inner spaces and fix casing of text columns."""
    for col, kind in SCHEMA[t].items():
        if kind != "str":
            continue
        before = df[col].copy()
        s = df[col].astype("string").str.strip().str.replace(r"\s+", " ", regex=True)
        s = s.replace({"": pd.NA, "nan": pd.NA, "None": pd.NA, "NULL": pd.NA, "N/A": pd.NA})
        if (t, col) in ALLOWED:
            # map case / punctuation variants ("in transit", "IN_TRANSIT") to canonical values
            canon = {a.lower().replace("-", "").replace(" ", "").replace("_", ""): a for a in ALLOWED[(t, col)]}
            key = s.str.lower().str.replace(r"[-_ ]", "", regex=True)
            s = key.map(canon).where(key.notna(), pd.NA).astype("string")
        elif col in ("city", "state", "origin_city", "dest_city", "name"):
            s = s.str.title()
        changed = int((before.astype("string").fillna("<NA>") != s.fillna("<NA>")).sum())
        if changed:
            log.add(t, f"standardised text/casing in '{col}'", changed)
        df[col] = s
    return df


def _coerce_types(df: pd.DataFrame, t: str, log: CleaningLog) -> pd.DataFrame:
    """Convert every column to its documented type; unparsable values become NaN/NaT."""
    for col, kind in SCHEMA[t].items():
        before_na = df[col].isna().sum()
        if kind in ("int", "float"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        elif kind in ("date", "datetime"):
            df[col] = pd.to_datetime(df[col], errors="coerce")
        new_na = df[col].isna().sum() - before_na
        if new_na > 0:
            log.add(t, f"'{col}' had unparsable values -> set to NULL", new_na)
    return df


def _apply_ranges(df: pd.DataFrame, t: str, log: CleaningLog) -> pd.DataFrame:
    """Out-of-range numbers (negative weights, rating 7 ...) become NaN to be imputed/dropped."""
    for (tt, col), (lo, hi) in RANGES.items():
        if tt != t:
            continue
        bad = pd.Series(False, index=df.index)
        if lo is not None:
            bad |= df[col] < lo
        if hi is not None:
            bad |= df[col] > hi
        if bad.any():
            df.loc[bad, col] = np.nan
            log.add(t, f"out-of-range '{col}' set to NULL (valid {lo}..{hi})", bad.sum())
    return df


def _dedupe(df: pd.DataFrame, t: str, log: CleaningLog) -> pd.DataFrame:
    n = len(df)
    df = df.drop_duplicates()
    if n - len(df):
        log.add(t, "removed exact duplicate rows", n - len(df))
    n = len(df)
    df = df.dropna(subset=[PK[t]]).drop_duplicates(subset=[PK[t]], keep="first")
    if n - len(df):
        log.add(t, f"removed rows with missing/duplicate primary key '{PK[t]}'", n - len(df))
    return df


def _impute(df: pd.DataFrame, t: str, log: CleaningLog) -> pd.DataFrame:
    """Impute non-key columns: numeric -> median, categorical -> mode / 'Unknown'."""
    for col, kind in SCHEMA[t].items():
        if col.endswith("_id") or col.endswith("_dt") or kind == "date":
            continue  # keys and dates are not imputed (handled separately)
        n = int(df[col].isna().sum())
        if not n:
            continue
        if kind in ("int", "float"):
            df[col] = df[col].fillna(df[col].median())
            log.add(t, f"imputed missing '{col}' with median", n)
        else:
            fill = df[col].mode().iloc[0] if (t, col) in ALLOWED and df[col].notna().any() else "Unknown"
            df[col] = df[col].fillna(fill)
            log.add(t, f"imputed missing '{col}' with '{fill}'", n)
    return df


def clean_all(raw: dict[str, pd.DataFrame]) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """Clean all 7 tables. Returns (cleaned_tables, cleaning_log)."""
    log = CleaningLog()
    out: dict[str, pd.DataFrame] = {}

    # 1) table-level cleaning
    for t, df in raw.items():
        df = df.copy()
        df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]  # normalise headers
        df = _standardize_text(df, t, log)
        df = _coerce_types(df, t, log)
        df = _dedupe(df, t, log)
        df = _apply_ranges(df, t, log)
        out[t] = df

    # 2) domain-specific rules ------------------------------------------------
    d = out["drivers"]
    # experience must be consistent with join_date: derive it where missing
    miss = d["experience"].isna() & d["join_date"].notna()
    if miss.any():
        d.loc[miss, "experience"] = (pd.Timestamp("2026-01-01").year - d.loc[miss, "join_date"].dt.year)
        log.add("drivers", "derived missing experience from join_date", miss.sum())

    de = out["deliveries"]
    # Not-yet-delivered / cancelled shipments have no real delivery timestamp or delay.
    not_done = de["status"].isin(["In-Transit", "Cancelled"])
    n = int((not_done & de["actual_dt"].notna()).sum())
    if n:
        de.loc[not_done, "actual_dt"] = pd.NaT
        log.add("deliveries", "In-Transit/Cancelled: actual_dt set to NULL (no real delivery event)", n)
    n = int((not_done & de["delay_hours"].notna()).sum())
    if n:
        de.loc[not_done, "delay_hours"] = np.nan
        log.add("deliveries", "In-Transit/Cancelled: delay_hours set to NULL (delay undefined)", n)
    # completed deliveries with missing delay -> 0 for 'Delivered', median for 'Delayed'
    for status, fill in [("Delivered", 0.0), ("Delayed", de.loc[de["status"] == "Delayed", "delay_hours"].median())]:
        m = (de["status"] == status) & de["delay_hours"].isna()
        if m.any():
            de.loc[m, "delay_hours"] = fill
            log.add("deliveries", f"imputed missing delay_hours for '{status}' with {fill}", m.sum())

    # impute remaining non-key, non-date nulls (all tables, except deliveries' delay_hours handled above)
    for t in out:
        if t == "deliveries":
            m = out[t]["status"].isna()
            if m.any():
                out[t] = out[t][~m]
                log.add(t, "dropped deliveries with unknown status", m.sum())
            continue
        out[t] = _impute(out[t], t, log)

    # Mandatory dates: shipments without shipment_dt cannot be analysed in time
    s = out["shipments"]
    m = s["shipment_dt"].isna()
    if m.any():
        out["shipments"] = s[~m]
        log.add("shipments", "dropped shipments with missing shipment_dt", m.sum())

    # Impossible timeline: delivered before shipped -> actual_dt NULL
    sd = out["deliveries"].merge(out["shipments"][["shipment_id", "shipment_dt"]], on="shipment_id", how="left")
    bad = (sd["actual_dt"] < sd["shipment_dt"]).values
    if bad.any():
        out["deliveries"].loc[bad, "actual_dt"] = pd.NaT
        log.add("deliveries", "actual_dt earlier than shipment_dt -> set to NULL", bad.sum())

    # 3) referential integrity (parents first, cascade to children) ----------
    def drop_orphans(child, col, parent, pcol):
        c = out[child]
        m = ~c[col].isin(out[parent][pcol])
        if m.any():
            out[child] = c[~m]
            log.add(child, f"dropped orphan rows ({col} not in {parent})", m.sum())

    for col, parent in [("warehouse_id", "warehouses"), ("driver_id", "drivers"),
                        ("vehicle_id", "vehicles"), ("route_id", "routes")]:
        drop_orphans("shipments", col, parent, col)
    drop_orphans("deliveries", "shipment_id", "shipments", "shipment_id")
    drop_orphans("feedback", "delivery_id", "deliveries", "delivery_id")

    # 4) final dtypes ---------------------------------------------------------
    for t, df in out.items():
        for col, kind in SCHEMA[t].items():
            if kind == "int" and df[col].notna().all():
                df[col] = df[col].round().astype("int64")
            elif kind == "str":
                df[col] = df[col].astype(object)
        out[t] = df[list(SCHEMA[t])].sort_values(PK[t]).reset_index(drop=True)

    log_df = log.to_frame()
    if log_df.empty:
        log_df = pd.DataFrame([{"table": "all", "action": "no changes required", "rows_affected": 0}])
    return out, log_df
