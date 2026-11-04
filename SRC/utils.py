"""
utils.py
--------
Shared helpers for the LogiTrack project:
  * project paths (raw / cleaned data, SQL folder, figures)
  * database connection (SQLAlchemy engine, configured through an environment
    variable so no credentials are hard-coded)
  * schema creation + loading cleaned data into SQL with PK / FK constraints
  * small reporting helpers used by notebooks
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
CLEANED_DIR = DATA_DIR / "cleaned"
SQL_DIR = PROJECT_ROOT / "sql"
FIGURES_DIR = PROJECT_ROOT / "reports" / "figures"

# Table names in load order (parents before children so FKs are satisfied)
TABLES = ["warehouses", "drivers", "vehicles", "routes", "shipments", "deliveries", "feedback"]

# Primary key of every table
PRIMARY_KEYS = {
    "warehouses": "warehouse_id",
    "drivers": "driver_id",
    "vehicles": "vehicle_id",
    "routes": "route_id",
    "shipments": "shipment_id",
    "deliveries": "delivery_id",
    "feedback": "feedback_id",
}

# Foreign keys: child table -> list of (column, parent table, parent column)
FOREIGN_KEYS = {
    "shipments": [
        ("warehouse_id", "warehouses", "warehouse_id"),
        ("driver_id", "drivers", "driver_id"),
        ("vehicle_id", "vehicles", "vehicle_id"),
        ("route_id", "routes", "route_id"),
    ],
    "deliveries": [("shipment_id", "shipments", "shipment_id")],
    "feedback": [("delivery_id", "deliveries", "delivery_id")],
}

# --------------------------------------------------------------------------- #
# Database connection
# --------------------------------------------------------------------------- #
DEFAULT_DB_PATH = DATA_DIR / "logitrack.db"


def get_db_url() -> str:
    """
    Return the database URL.

    The URL is read from the LOGITRACK_DB_URL environment variable so that
    credentials are never hard-coded (e.g. a MySQL URL like
    mysql+pymysql://user:password@host/logitrack can be supplied via a .env /
    shell export). If it is not set we fall back to a local SQLite file, which
    needs no credentials at all.
    """
    return os.getenv("LOGITRACK_DB_URL", f"sqlite:///{DEFAULT_DB_PATH}")


def get_engine(echo: bool = False) -> Engine:
    """Create a SQLAlchemy engine. For SQLite, FK enforcement is switched on."""
    engine = create_engine(get_db_url(), echo=echo, future=True)
    if engine.dialect.name == "sqlite":
        from sqlalchemy import event

        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _):  # pragma: no cover - simple pragma
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys = ON;")
            cur.close()
    return engine


def run_query(sql: str, params: dict | None = None, engine: Engine | None = None) -> pd.DataFrame:
    """Run a SELECT query and return a DataFrame."""
    engine = engine or get_engine()
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params or {})


# --------------------------------------------------------------------------- #
# Schema creation and data loading
# --------------------------------------------------------------------------- #
def create_schema(engine: Engine | None = None, schema_file: Path | None = None) -> None:
    """
    Execute sql/schema.sql (DROP + CREATE TABLE statements with PK/FK
    constraints + analytical view). Written for SQLite; statements are split
    on ';' so they can also be run through SQLAlchemy on other engines.
    """
    engine = engine or get_engine()
    schema_file = schema_file or SQL_DIR / "schema.sql"
    sql_script = schema_file.read_text(encoding="utf-8")
    if engine.dialect.name == "sqlite":
        # executescript handles comments and multiple statements natively
        raw = engine.raw_connection()
        try:
            raw.execute("PRAGMA foreign_keys = OFF;")  # allow drops in any order
            raw.executescript(sql_script)
            raw.execute("PRAGMA foreign_keys = ON;")
            raw.commit()
        finally:
            raw.close()
    else:
        with engine.begin() as conn:
            for stmt in [s.strip() for s in sql_script.split(";") if s.strip()]:
                conn.execute(text(stmt))


def load_table(df: pd.DataFrame, table: str, engine: Engine | None = None) -> int:
    """
    Append a cleaned DataFrame into an *existing* table (created by
    schema.sql, so PK/FK constraints are kept). Datetimes are written as
    ISO strings so they sort/filter correctly in SQLite.
    """
    engine = engine or get_engine()
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[col]):
            fmt = "%Y-%m-%d" if col.endswith("_date") or col == "feedback_dt" else "%Y-%m-%d %H:%M:%S"
            out[col] = out[col].dt.strftime(fmt)
        elif pd.api.types.is_bool_dtype(out[col]):
            out[col] = out[col].astype(int)
    out = out.astype(object).where(pd.notna(out), None)
    with engine.begin() as conn:
        out.to_sql(table, conn, if_exists="append", index=False, method="multi", chunksize=500)
    return len(out)


def verify_database(engine: Engine | None = None) -> pd.DataFrame:
    """Row counts per table + FK integrity check (should report 0 violations)."""
    engine = engine or get_engine()
    rows = []
    for t in TABLES:
        n = run_query(f"SELECT COUNT(*) AS n FROM {t}", engine=engine)["n"].iloc[0]
        rows.append({"table": t, "rows_in_db": int(n)})
    report = pd.DataFrame(rows)
    if engine.dialect.name == "sqlite":
        fk = run_query("PRAGMA foreign_key_check;", engine=engine)
        report.attrs["fk_violations"] = len(fk)
    return report


# --------------------------------------------------------------------------- #
# Misc helpers
# --------------------------------------------------------------------------- #
def read_raw(table: str) -> pd.DataFrame:
    """Read one raw CSV (data/raw/logitrack_<table>.csv)."""
    return pd.read_csv(RAW_DIR / f"logitrack_{table}.csv")


def read_cleaned(table: str) -> pd.DataFrame:
    """Read one cleaned CSV (data/cleaned/<table>_cleaned.csv) with dates parsed."""
    df = pd.read_csv(CLEANED_DIR / f"{table}_cleaned.csv")
    for col in df.columns:
        if col.endswith("_dt") or col.endswith("_date"):
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def save_fig(fig, name: str) -> Path:
    """Save a matplotlib figure into reports/figures/<name>.png."""
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    path = FIGURES_DIR / f"{name}.png"
    fig.savefig(path, dpi=120, bbox_inches="tight")
    return path


def data_overview(df: pd.DataFrame, name: str) -> pd.DataFrame:
    """One-row-per-column structure summary: dtype, nulls, uniques, example."""
    return pd.DataFrame(
        {
            "table": name,
            "column": df.columns,
            "dtype": [str(t) for t in df.dtypes],
            "non_null": df.notna().sum().values,
            "nulls": df.isna().sum().values,
            "unique": df.nunique().values,
            "example": [df[c].dropna().iloc[0] if df[c].notna().any() else None for c in df.columns],
        }
    )
