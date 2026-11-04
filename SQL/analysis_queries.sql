-- =============================================================================
-- LogiTrack: analysis_queries.sql
-- Business SQL queries used by the analysis and the Streamlit dashboard.
--
-- Conventions
--   * Every query starts from the CTE "base" over the view vw_logitrack (one
--     row per shipment, 7 tables joined + engineered features).
--   * "/*FILTERS*/" and "/*VFILTERS*/" are placeholders. The dashboard swaps
--     them for parameterised sidebar-filter conditions (AND ... = :param).
--     Run as-is (e.g. in DB Browser / sqlite3), they are plain comments and the
--     queries return results for the full dataset.
--   * Each query is introduced by a line "-- name: <id> | <title>" which the
--     dashboard uses to load the queries from this file (single source of truth).
--
-- KPI rules
--   Total Shipments       = COUNT(shipment_id)
--   Total Deliveries      = completed deliveries, status IN ('Delivered','Delayed')
--   Delivery Success Rate = Delivered / all shipments * 100
--   Average Delay Hours   = AVG(delay_hours) over completed deliveries
--                           (NULL for In-Transit/Cancelled, so AVG ignores them)
--   Average Rating        = AVG(customer_rating) where rating BETWEEN 1 AND 5
--
-- Techniques: SELECT/WHERE/ORDER BY, GROUP BY/HAVING, INNER/LEFT JOIN,
--             subqueries, CTEs, window functions (RANK, LAG, SUM OVER), aggregates
-- =============================================================================


-- name: q01 | 1. Overall delivery performance
-- Techniques: CTE, conditional aggregation (CASE), NULL handling
WITH base AS (SELECT * FROM vw_logitrack WHERE 1=1 /*FILTERS*/)
SELECT
    COUNT(*)                                                             AS total_shipments,
    SUM(CASE WHEN delivery_status IN ('Delivered','Delayed') THEN 1 ELSE 0 END) AS total_deliveries,
    SUM(CASE WHEN delivery_status = 'Delivered'  THEN 1 ELSE 0 END)      AS delivered,
    SUM(CASE WHEN delivery_status = 'Delayed'    THEN 1 ELSE 0 END)      AS delayed,
    SUM(CASE WHEN delivery_status = 'In-Transit' THEN 1 ELSE 0 END)      AS in_transit,
    SUM(CASE WHEN delivery_status = 'Cancelled'  THEN 1 ELSE 0 END)      AS cancelled,
    ROUND(100.0 * SUM(CASE WHEN delivery_status = 'Delivered' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) AS success_rate_pct,
    ROUND(100.0 * SUM(CASE WHEN delay_hours = 0 THEN 1 ELSE 0 END) / NULLIF(COUNT(delay_hours), 0), 2)     AS on_time_pct_of_completed,
    ROUND(AVG(delay_hours), 2)                                           AS avg_delay_hours,
    ROUND(AVG(CASE WHEN customer_rating BETWEEN 1 AND 5 THEN customer_rating END), 2) AS avg_rating,
    ROUND(AVG(delivery_days), 2)                                         AS avg_delivery_days
FROM base;


-- name: q02 | 2. Average delay by route type
-- Techniques: GROUP BY, HAVING, aggregates, ORDER BY
WITH base AS (SELECT * FROM vw_logitrack WHERE 1=1 /*FILTERS*/)
SELECT
    route_type,
    COUNT(*)                                               AS shipments,
    COUNT(delay_hours)                                     AS completed_deliveries,
    ROUND(AVG(delay_hours), 2)                             AS avg_delay_hours,
    ROUND(MAX(delay_hours), 2)                             AS max_delay_hours,
    ROUND(100.0 * SUM(CASE WHEN delivery_status = 'Delayed' THEN 1 ELSE 0 END) / COUNT(*), 2) AS delayed_status_pct,
    ROUND(AVG(distance_km), 0)                             AS avg_distance_km
FROM base
GROUP BY route_type
HAVING COUNT(delay_hours) > 0
ORDER BY avg_delay_hours DESC;


-- name: q03 | 3. Top performing drivers
-- Techniques: CTE, HAVING (minimum volume), window function RANK()
WITH base AS (SELECT * FROM vw_logitrack WHERE 1=1 /*FILTERS*/),
driver_stats AS (
    SELECT
        driver_id, driver_name, driver_experience, experience_level, driver_rating,
        COUNT(*)                                     AS shipments,
        ROUND(AVG(customer_rating), 2)               AS avg_customer_rating,
        ROUND(AVG(delay_hours), 2)                   AS avg_delay_hours,
        ROUND(100.0 * SUM(is_success) / COUNT(*), 1) AS success_rate_pct
    FROM base
    GROUP BY driver_id, driver_name, driver_experience, experience_level, driver_rating
    HAVING COUNT(*) >= 5
)
SELECT *,
       RANK() OVER (ORDER BY avg_customer_rating DESC, avg_delay_hours ASC) AS rating_rank
FROM driver_stats
ORDER BY rating_rank
LIMIT 10;


-- name: q04 | 4. Delivery performance by warehouse
-- Techniques: INNER JOIN (warehouses -> base), GROUP BY, window RANK()
WITH base AS (SELECT * FROM vw_logitrack WHERE 1=1 /*FILTERS*/)
SELECT
    w.warehouse_id, w.name AS warehouse_name, w.city, w.state, w.capacity,
    COUNT(b.shipment_id)                                    AS shipments,
    ROUND(100.0 * SUM(b.is_success) / COUNT(b.shipment_id), 2) AS success_rate_pct,
    ROUND(AVG(b.delay_hours), 2)                            AS avg_delay_hours,
    ROUND(AVG(b.customer_rating), 2)                        AS avg_rating,
    RANK() OVER (ORDER BY 1.0 * SUM(b.is_success) / COUNT(b.shipment_id) DESC) AS success_rank
FROM warehouses w
INNER JOIN base b ON b.warehouse_id = w.warehouse_id
GROUP BY w.warehouse_id, w.name, w.city, w.state, w.capacity
ORDER BY success_rank;


-- name: q05 | 5. Monthly delivery trends
-- Techniques: CTE, GROUP BY month, window functions LAG() and running SUM() OVER
WITH base AS (SELECT * FROM vw_logitrack WHERE 1=1 /*FILTERS*/),
monthly AS (
    SELECT
        shipment_month                                   AS month,
        COUNT(*)                                         AS shipments,
        SUM(CASE WHEN delivery_status = 'Delivered' THEN 1 ELSE 0 END) AS delivered,
        SUM(CASE WHEN delivery_status = 'Delayed'   THEN 1 ELSE 0 END) AS delayed,
        ROUND(100.0 * SUM(is_success) / COUNT(*), 2)     AS success_rate_pct,
        ROUND(AVG(delay_hours), 2)                       AS avg_delay_hours,
        ROUND(AVG(customer_rating), 2)                   AS avg_rating
    FROM base
    GROUP BY shipment_month
)
SELECT *,
       ROUND(avg_delay_hours - LAG(avg_delay_hours) OVER (ORDER BY month), 2) AS delay_change_vs_prev_month,
       SUM(shipments) OVER (ORDER BY month ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumulative_shipments
FROM monthly
ORDER BY month;


-- name: q06 | 6. Vehicle utilization
-- Techniques: LEFT JOIN (vehicles without shipments still appear), COALESCE, GROUP BY
WITH base AS (SELECT * FROM vw_logitrack WHERE 1=1 /*FILTERS*/),
per_vehicle AS (
    SELECT
        v.vehicle_id, v.vehicle_type, v.fuel_type, v.status, v.capacity_kg,
        COUNT(b.shipment_id)                       AS shipments,
        COALESCE(SUM(b.weight_kg), 0)              AS total_weight_kg,
        AVG(b.capacity_utilization_pct)            AS avg_utilization_pct,
        AVG(b.delay_hours)                         AS avg_delay_hours
    FROM vehicles v
    LEFT JOIN base b ON b.vehicle_id = v.vehicle_id
    WHERE 1=1 /*VFILTERS*/
    GROUP BY v.vehicle_id, v.vehicle_type, v.fuel_type, v.status, v.capacity_kg
)
SELECT
    vehicle_type,
    COUNT(*)                                       AS vehicles,
    SUM(CASE WHEN status = 'Active' THEN 1 ELSE 0 END) AS active_vehicles,
    SUM(CASE WHEN shipments = 0 THEN 1 ELSE 0 END) AS idle_vehicles,
    SUM(shipments)                                 AS shipments,
    ROUND(1.0 * SUM(shipments) / COUNT(*), 1)      AS shipments_per_vehicle,
    ROUND(SUM(total_weight_kg), 0)                 AS total_weight_kg,
    ROUND(AVG(avg_utilization_pct), 2)             AS avg_capacity_utilization_pct,
    ROUND(AVG(avg_delay_hours), 2)                 AS avg_delay_hours
FROM per_vehicle
GROUP BY vehicle_type
ORDER BY avg_capacity_utilization_pct DESC;


-- name: q07 | 7. Rating by delivery status
-- Techniques: GROUP BY, conditional aggregation, subquery for share of total
WITH base AS (SELECT * FROM vw_logitrack WHERE 1=1 /*FILTERS*/)
SELECT
    delivery_status,
    COUNT(customer_rating)                                          AS feedback_count,
    ROUND(AVG(customer_rating), 2)                                  AS avg_rating,
    ROUND(100.0 * SUM(CASE WHEN customer_rating >= 4 THEN 1 ELSE 0 END) / COUNT(customer_rating), 1) AS positive_pct,
    ROUND(100.0 * SUM(CASE WHEN customer_rating <= 2 THEN 1 ELSE 0 END) / COUNT(customer_rating), 1) AS negative_pct,
    ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM base), 1)        AS share_of_shipments_pct
FROM base
WHERE customer_rating BETWEEN 1 AND 5
GROUP BY delivery_status
ORDER BY avg_rating DESC;


-- name: q08 | 8. Delay analysis by distance category
-- Techniques: GROUP BY on engineered feature, CASE for custom sort order
WITH base AS (SELECT * FROM vw_logitrack WHERE 1=1 /*FILTERS*/)
SELECT
    distance_category,
    COUNT(*)                                   AS shipments,
    ROUND(MIN(distance_km), 0)                 AS min_km,
    ROUND(MAX(distance_km), 0)                 AS max_km,
    ROUND(AVG(delay_hours), 2)                 AS avg_delay_hours,
    ROUND(100.0 * AVG(is_delayed), 2)          AS delayed_pct_of_completed,
    ROUND(AVG(delivery_hours), 1)              AS avg_transit_hours,
    ROUND(AVG(customer_rating), 2)             AS avg_rating
FROM base
GROUP BY distance_category
ORDER BY CASE distance_category WHEN 'Short' THEN 1 WHEN 'Medium' THEN 2 WHEN 'Long' THEN 3 ELSE 4 END;


-- name: q09 | 9. Driver performance by experience level
-- Techniques: subquery in FROM (per-driver aggregates), GROUP BY, ORDER BY CASE
SELECT
    experience_level,
    COUNT(*)                                   AS drivers,
    ROUND(AVG(experience_years), 1)            AS avg_experience_years,
    SUM(shipments)                             AS shipments,
    ROUND(AVG(shipments), 1)                   AS avg_shipments_per_driver,
    ROUND(AVG(avg_delay), 2)                   AS avg_delay_hours,
    ROUND(AVG(success_rate), 2)                AS avg_success_rate_pct,
    ROUND(AVG(avg_rating), 2)                  AS avg_customer_rating
FROM (
    SELECT driver_id, experience_level,
           MAX(driver_experience)                     AS experience_years,
           COUNT(*)                                   AS shipments,
           AVG(delay_hours)                           AS avg_delay,
           100.0 * SUM(is_success) / COUNT(*)         AS success_rate,
           AVG(customer_rating)                       AS avg_rating
    FROM vw_logitrack
    WHERE 1=1 /*FILTERS*/
    GROUP BY driver_id, experience_level
) AS per_driver
GROUP BY experience_level
ORDER BY CASE experience_level WHEN 'Junior' THEN 1 WHEN 'Mid' THEN 2 WHEN 'Senior' THEN 3 ELSE 4 END;


-- name: q10 | 10. Day of week analysis
-- Techniques: GROUP BY, window function (share of total via SUM() OVER ()), ORDER BY CASE
WITH base AS (SELECT * FROM vw_logitrack WHERE 1=1 /*FILTERS*/)
SELECT
    shipment_day_of_week                                 AS day_of_week,
    COUNT(*)                                             AS shipments,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1)   AS share_pct,
    ROUND(AVG(delay_hours), 2)                           AS avg_delay_hours,
    ROUND(100.0 * SUM(is_success) / COUNT(*), 2)         AS success_rate_pct,
    ROUND(AVG(customer_rating), 2)                       AS avg_rating
FROM base
GROUP BY shipment_day_of_week
ORDER BY CASE shipment_day_of_week WHEN 'Monday' THEN 1 WHEN 'Tuesday' THEN 2 WHEN 'Wednesday' THEN 3
         WHEN 'Thursday' THEN 4 WHEN 'Friday' THEN 5 WHEN 'Saturday' THEN 6 ELSE 7 END;


-- =============================================================================
-- Supporting queries used by individual dashboard charts
-- =============================================================================

-- name: s01 | Delivery status distribution
WITH base AS (SELECT * FROM vw_logitrack WHERE 1=1 /*FILTERS*/)
SELECT delivery_status, COUNT(*) AS shipments
FROM base GROUP BY delivery_status ORDER BY shipments DESC;


-- name: s02 | Route performance comparison (lanes)
WITH base AS (SELECT * FROM vw_logitrack WHERE 1=1 /*FILTERS*/)
SELECT route_id, route_name, route_type, distance_km,
       COUNT(*)                                     AS shipments,
       ROUND(AVG(delay_hours), 2)                   AS avg_delay_hours,
       ROUND(100.0 * SUM(is_success) / COUNT(*), 1) AS success_rate_pct,
       ROUND(AVG(customer_rating), 2)               AS avg_rating
FROM base
GROUP BY route_id, route_name, route_type, distance_km
HAVING COUNT(*) >= 5
ORDER BY avg_delay_hours DESC;


-- name: s03 | Driver workload distribution
WITH base AS (SELECT * FROM vw_logitrack WHERE 1=1 /*FILTERS*/)
SELECT driver_id, driver_name, experience_level, driver_experience,
       COUNT(*)                           AS shipments,
       ROUND(SUM(weight_kg), 0)           AS total_weight_kg,
       ROUND(SUM(distance_km), 0)         AS total_distance_km,
       ROUND(AVG(delay_hours), 2)         AS avg_delay_hours,
       ROUND(AVG(customer_rating), 2)     AS avg_rating,
       ROUND(100.0 * SUM(is_success) / COUNT(*), 1) AS success_rate_pct
FROM base
GROUP BY driver_id, driver_name, experience_level, driver_experience
ORDER BY shipments DESC;


-- name: s04 | Distance vs delay (shipment level, completed deliveries)
WITH base AS (SELECT * FROM vw_logitrack WHERE 1=1 /*FILTERS*/)
SELECT shipment_id, distance_km, delay_hours, route_type, delivery_status, distance_category
FROM base
WHERE delay_hours IS NOT NULL;


-- name: s05 | Rating distribution
WITH base AS (SELECT * FROM vw_logitrack WHERE 1=1 /*FILTERS*/)
SELECT customer_rating AS rating, COUNT(*) AS feedback_count
FROM base
WHERE customer_rating BETWEEN 1 AND 5
GROUP BY customer_rating ORDER BY customer_rating;


-- name: s06 | Rating trends over time
WITH base AS (SELECT * FROM vw_logitrack WHERE 1=1 /*FILTERS*/)
SELECT shipment_month AS month,
       ROUND(AVG(customer_rating), 3) AS avg_rating,
       ROUND(100.0 * SUM(CASE WHEN customer_rating >= 4 THEN 1 ELSE 0 END) / COUNT(customer_rating), 1) AS positive_pct,
       ROUND(100.0 * SUM(CASE WHEN customer_rating <= 2 THEN 1 ELSE 0 END) / COUNT(customer_rating), 1) AS negative_pct
FROM base
WHERE customer_rating IS NOT NULL
GROUP BY shipment_month ORDER BY month;


-- name: s07 | Rating by delay severity
WITH base AS (SELECT * FROM vw_logitrack WHERE 1=1 /*FILTERS*/)
SELECT delay_severity, COUNT(*) AS deliveries, ROUND(AVG(customer_rating), 2) AS avg_rating
FROM base
WHERE delay_severity IS NOT NULL
GROUP BY delay_severity
ORDER BY CASE delay_severity WHEN 'On-time' THEN 1 WHEN 'Minor (<=6h)' THEN 2 WHEN 'Moderate (6-24h)' THEN 3 ELSE 4 END;


-- name: s08 | Delay by warehouse and quarter (heatmap)
WITH base AS (SELECT * FROM vw_logitrack WHERE 1=1 /*FILTERS*/)
SELECT warehouse_name || ' (' || warehouse_city || ')' AS warehouse, shipment_quarter, ROUND(AVG(delay_hours), 2) AS avg_delay_hours
FROM base
GROUP BY warehouse, shipment_quarter;
