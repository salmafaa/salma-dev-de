-- Q1.1 — Top 10 Active Creators by GMV (January 2025)
SELECT
    c.username,
    c.display_name,
    SUM(p.total_gmv)            AS total_gmv,
    SUM(p.affiliate_gmv)        AS affiliate_gmv,
    SUM(p.affiliate_live_gmv)   AS live_gmv,
    SUM(p.affiliate_video_gmv)  AS video_gmv,
    DENSE_RANK() OVER (ORDER BY SUM(p.total_gmv) DESC) AS rank
FROM creators c
JOIN creator_daily_performance p ON c.id = p.creator_id
WHERE c.status = 'ACTIVE'
  AND p.report_date >= '2025-01-01'
  AND p.report_date <  '2025-02-01'
GROUP BY c.id, c.username, c.display_name
ORDER BY total_gmv DESC
LIMIT 10;


-- Q1.2 — 7-Day Rolling GMV (Q1 2025)
SELECT
    p.creator_id,
    c.username,
    p.report_date,
    p.total_gmv                                        AS daily_gmv,
    SUM(p.total_gmv) OVER (
        PARTITION BY p.creator_id
        ORDER BY p.report_date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    )                                                  AS rolling_7d_gmv
FROM creator_daily_performance p
JOIN creators c ON c.id = p.creator_id
WHERE p.report_date >= '2025-01-01'
  AND p.report_date <  '2025-04-01'
ORDER BY p.creator_id, p.report_date;


-- Q1.3 — Live vs Video Attribution (last 30 days)
WITH product_agg AS (
    SELECT
        cp.product_id,
        cp.product_name,
        COUNT(DISTINCT cp.creator_id)       AS creator_count,
        SUM(cp.affiliate_live_gmv)          AS total_live_gmv,
        SUM(cp.affiliate_video_gmv)         AS total_video_gmv,
        SUM(cp.affiliate_live_gmv + cp.affiliate_video_gmv) AS total_affiliate_gmv
    FROM creator_products cp
    WHERE cp.report_date >= CURRENT_DATE - INTERVAL '30 days'
    GROUP BY cp.product_id, cp.product_name
)
SELECT
    product_id,
    product_name,
    creator_count,
    total_live_gmv,
    total_video_gmv,
    CASE
        WHEN total_live_gmv >= total_video_gmv THEN 'LIVE'
        ELSE 'VIDEO'
    END AS dominant_channel
FROM product_agg
WHERE creator_count >= 3
  AND total_affiliate_gmv > 10000000
ORDER BY total_affiliate_gmv DESC;


-- Q1.4 — Creator Tier Promotion
WITH gmv_last_30 AS (
    SELECT
        creator_id,
        SUM(total_gmv) AS gmv_last_30d
    FROM creator_daily_performance
    WHERE report_date >= CURRENT_DATE - INTERVAL '30 days'
    GROUP BY creator_id
),
tier_mapping AS (
    SELECT
        c.id           AS creator_id,
        c.username,
        c.sales_power  AS current_tier,
        COALESCE(g.gmv_last_30d, 0) AS gmv_last_30d,
        CASE
            WHEN COALESCE(g.gmv_last_30d, 0) >= 100000000 THEN 'Platinum'
            WHEN COALESCE(g.gmv_last_30d, 0) >= 50000000  THEN 'Gold'
            WHEN COALESCE(g.gmv_last_30d, 0) >= 10000000  THEN 'Silver'
            ELSE 'Bronze'
        END AS qualified_tier
    FROM creators c
    LEFT JOIN gmv_last_30 g ON g.creator_id = c.id
)
SELECT
    creator_id,
    username,
    current_tier,
    gmv_last_30d,
    qualified_tier,
    (
        ARRAY_POSITION(ARRAY['Bronze','Silver','Gold','Platinum'], qualified_tier)
        >
        ARRAY_POSITION(ARRAY['Bronze','Silver','Gold','Platinum'], current_tier)
    ) AS promotion_flag
FROM tier_mapping
ORDER BY gmv_last_30d DESC;


-- Q1.5 — Materialized View Design

-- 1. CREATE MATERIALIZED VIEW
CREATE MATERIALIZED VIEW mv_weekly_gmv_by_tier AS
SELECT
    DATE_TRUNC('week', p.report_date)::DATE  AS week_start,  -- ISO Monday
    c.sales_power,
    COUNT(DISTINCT c.id)                      AS creator_count,
    SUM(p.total_gmv)                          AS total_gmv,
    SUM(p.affiliate_live_gmv)                 AS total_live_gmv,
    SUM(p.total_orders)                       AS total_orders
FROM creators c
JOIN creator_daily_performance p ON p.creator_id = c.id
GROUP BY DATE_TRUNC('week', p.report_date), c.sales_power
WITH DATA;

-- 2. Index wajib untuk CONCURRENTLY refresh (butuh unique index)
CREATE UNIQUE INDEX idx_mv_weekly_gmv_tier_pk
    ON mv_weekly_gmv_by_tier (week_start, sales_power);

-- Refresh statement
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_weekly_gmv_by_tier;

-- 3. Kapan trigger refresh di Airflow:
-- Tambahkan task `refresh_matview` di akhir DAG ingestion harian,
-- setelah `load_to_postgres` sukses — sehingga view selalu fresh
-- setiap pagi sebelum tim buka dashboard.