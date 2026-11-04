-- =============================================================================
-- LogiTrack: Supply Chain & Logistics Performance Analytics
-- schema.sql  -  database schema (SQLite dialect; MySQL notes inline)
--
-- 7 core tables from the ER diagram + 1 engineered-feature table + 1 view.
-- Primary keys and foreign keys are enforced (SQLite: PRAGMA foreign_keys = ON).
--   warehouses 1--* shipments *--1 drivers
--   vehicles   1--* shipments *--1 routes
--   shipments  1--1 deliveries 1--1 feedback
-- =============================================================================

DROP VIEW  IF EXISTS vw_logitrack;
DROP TABLE IF EXISTS shipment_features;
DROP TABLE IF EXISTS feedback;
DROP TABLE IF EXISTS deliveries;
DROP TABLE IF EXISTS shipments;
DROP TABLE IF EXISTS routes;
DROP TABLE IF EXISTS vehicles;
DROP TABLE IF EXISTS drivers;
DROP TABLE IF EXISTS warehouses;

-- Table 1: warehouses ---------------------------------------------------------
CREATE TABLE warehouses (
    warehouse_id   INTEGER      NOT NULL PRIMARY KEY,
    name           VARCHAR(100) NOT NULL,
    city           VARCHAR(100) NOT NULL,
    state          VARCHAR(100) NOT NULL,
    capacity       INTEGER      NOT NULL CHECK (capacity > 0)
);

-- Table 2: drivers ------------------------------------------------------------
CREATE TABLE drivers (
    driver_id      INTEGER      NOT NULL PRIMARY KEY,
    name           VARCHAR(100) NOT NULL,
    experience     INTEGER      NOT NULL CHECK (experience >= 0),
    rating         FLOAT        NOT NULL CHECK (rating BETWEEN 1 AND 5),
    join_date      DATE
);

-- Table 3: vehicles -----------------------------------------------------------
CREATE TABLE vehicles (
    vehicle_id     INTEGER      NOT NULL PRIMARY KEY,
    vehicle_type   VARCHAR(20)  NOT NULL CHECK (vehicle_type IN ('Truck','Van','Bike')),
    capacity_kg    INTEGER      NOT NULL CHECK (capacity_kg > 0),
    fuel_type      VARCHAR(20)  NOT NULL CHECK (fuel_type IN ('Diesel','Petrol','Electric')),
    status         VARCHAR(20)  NOT NULL CHECK (status IN ('Active','Maintenance','Retired'))
);

-- Table 4: routes -------------------------------------------------------------
CREATE TABLE routes (
    route_id       INTEGER      NOT NULL PRIMARY KEY,
    origin_city    VARCHAR(100) NOT NULL,
    dest_city      VARCHAR(100) NOT NULL,
    distance_km    FLOAT        NOT NULL CHECK (distance_km > 0),
    route_type     VARCHAR(20)  NOT NULL CHECK (route_type IN ('Express','Standard','Economy'))
);

-- Table 5: shipments ----------------------------------------------------------
CREATE TABLE shipments (
    shipment_id    INTEGER      NOT NULL PRIMARY KEY,
    warehouse_id   INTEGER      NOT NULL,
    driver_id      INTEGER      NOT NULL,
    vehicle_id     INTEGER      NOT NULL,
    route_id       INTEGER      NOT NULL,
    shipment_dt    DATETIME     NOT NULL,
    weight_kg      FLOAT        NOT NULL CHECK (weight_kg > 0),
    priority       VARCHAR(10)  NOT NULL CHECK (priority IN ('High','Medium','Low')),
    FOREIGN KEY (warehouse_id) REFERENCES warehouses(warehouse_id),
    FOREIGN KEY (driver_id)    REFERENCES drivers(driver_id),
    FOREIGN KEY (vehicle_id)   REFERENCES vehicles(vehicle_id),
    FOREIGN KEY (route_id)     REFERENCES routes(route_id)
);

-- Table 6: deliveries ---------------------------------------------------------
-- actual_dt / delay_hours are NULL for In-Transit and Cancelled shipments.
CREATE TABLE deliveries (
    delivery_id    INTEGER      NOT NULL PRIMARY KEY,
    shipment_id    INTEGER      NOT NULL UNIQUE,
    actual_dt      DATETIME,
    status         VARCHAR(20)  NOT NULL CHECK (status IN ('Delivered','Delayed','In-Transit','Cancelled')),
    delay_hours    FLOAT        CHECK (delay_hours IS NULL OR delay_hours >= 0),
    FOREIGN KEY (shipment_id) REFERENCES shipments(shipment_id)
);

-- Table 7: feedback -----------------------------------------------------------
CREATE TABLE feedback (
    feedback_id    INTEGER      NOT NULL PRIMARY KEY,
    delivery_id    INTEGER      NOT NULL,
    rating         INTEGER      NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment        TEXT,
    feedback_dt    DATE,
    FOREIGN KEY (delivery_id) REFERENCES deliveries(delivery_id)
);

-- Engineered features (Step 7), 1 row per shipment ----------------------------
CREATE TABLE shipment_features (
    shipment_id              INTEGER NOT NULL PRIMARY KEY,
    delivery_id              INTEGER,
    feedback_id              INTEGER,
    delivery_hours           FLOAT,
    delivery_days            FLOAT,
    is_completed             INTEGER,
    is_success               INTEGER,
    is_cancelled             INTEGER,
    is_delayed               INTEGER,
    delay_severity           VARCHAR(30),
    weight_category          VARCHAR(20),
    distance_category        VARCHAR(20),
    experience_level         VARCHAR(20),
    rating_category          VARCHAR(20),
    delivery_month           VARCHAR(7),
    delivery_day_of_week     VARCHAR(10),
    delivery_hour            INTEGER,
    shipment_month           VARCHAR(7),
    shipment_month_name      VARCHAR(10),
    shipment_quarter         VARCHAR(2),
    shipment_year            INTEGER,
    shipment_day_of_week     VARCHAR(10),
    shipment_hour            INTEGER,
    is_weekend               INTEGER,
    capacity_utilization_pct FLOAT,
    speed_kmph               FLOAT,
    feedback_lag_days        INTEGER,
    driver_join_conflict     INTEGER,
    FOREIGN KEY (shipment_id) REFERENCES shipments(shipment_id),
    FOREIGN KEY (delivery_id) REFERENCES deliveries(delivery_id),
    FOREIGN KEY (feedback_id) REFERENCES feedback(feedback_id)
);

-- Helpful indexes for joins / dashboard filters
CREATE INDEX idx_ship_wh     ON shipments(warehouse_id);
CREATE INDEX idx_ship_driver ON shipments(driver_id);
CREATE INDEX idx_ship_veh    ON shipments(vehicle_id);
CREATE INDEX idx_ship_route  ON shipments(route_id);
CREATE INDEX idx_ship_dt     ON shipments(shipment_dt);
CREATE INDEX idx_fb_delivery ON feedback(delivery_id);

-- Analytical view used by the Streamlit dashboard: one row per shipment -------
CREATE VIEW vw_logitrack AS
SELECT
    s.shipment_id, s.shipment_dt, s.weight_kg, s.priority,
    w.warehouse_id, w.name AS warehouse_name, w.city AS warehouse_city, w.state AS warehouse_state,
    d.driver_id, d.name AS driver_name, d.experience AS driver_experience, d.rating AS driver_rating,
    v.vehicle_id, v.vehicle_type, v.capacity_kg, v.fuel_type, v.status AS vehicle_status,
    r.route_id, r.origin_city, r.dest_city, r.origin_city || ' -> ' || r.dest_city AS route_name,
    r.distance_km, r.route_type,
    de.delivery_id, de.actual_dt, de.status AS delivery_status, de.delay_hours,
    f.feedback_id, f.rating AS customer_rating, f.comment AS feedback_comment, f.feedback_dt,
    sf.delivery_hours, sf.delivery_days, sf.is_completed, sf.is_success, sf.is_delayed,
    sf.delay_severity, sf.weight_category, sf.distance_category, sf.experience_level,
    sf.rating_category, sf.shipment_month, sf.shipment_quarter, sf.shipment_day_of_week,
    sf.shipment_hour, sf.delivery_day_of_week, sf.capacity_utilization_pct, sf.speed_kmph
FROM shipments s
INNER JOIN warehouses w       ON w.warehouse_id = s.warehouse_id
INNER JOIN drivers d          ON d.driver_id    = s.driver_id
INNER JOIN vehicles v         ON v.vehicle_id   = s.vehicle_id
INNER JOIN routes r           ON r.route_id     = s.route_id
LEFT JOIN  deliveries de      ON de.shipment_id = s.shipment_id
LEFT JOIN  feedback f         ON f.delivery_id  = de.delivery_id
LEFT JOIN  shipment_features sf ON sf.shipment_id = s.shipment_id;
