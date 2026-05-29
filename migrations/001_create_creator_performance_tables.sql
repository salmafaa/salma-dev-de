-- =============================================================================
-- ENTRO.LY — Creator Data & Performance Database
-- Migration: 001_create_creator_performance_tables
-- =============================================================================
-- Rules:
--   DECIMAL(18,4) for ALL monetary columns
--   TIMESTAMPTZ (UTC) for all timestamps
--   ISO 4217 currency codes via VARCHAR(3)
--   Composite unique constraints prevent duplicate imports
-- =============================================================================

-- Enums
CREATE TYPE creator_status AS ENUM ('ACTIVE', 'INACTIVE');
CREATE TYPE sync_type AS ENUM ('CREATOR_DAILY', 'CREATOR_PRODUCT', 'CREATOR_LIVE', 'CREATOR_VIDEO', 'FULL_SYNC');
CREATE TYPE sync_status AS ENUM ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED');

-- =============================================================================
-- 1. CREATORS
-- =============================================================================
CREATE TABLE creators (
    id              TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
    username        TEXT NOT NULL UNIQUE,
    display_name    TEXT,
    email           TEXT UNIQUE,
    phone           TEXT,
    avatar_url      TEXT,
    bio             TEXT,
    country         VARCHAR(2),               -- ISO 3166-1 alpha-2
    city            TEXT,
    follower_count  INTEGER NOT NULL DEFAULT 0,
    tiktok_verified BOOLEAN NOT NULL DEFAULT FALSE,
    status          creator_status NOT NULL DEFAULT 'ACTIVE',
    joined_at       TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_creators_country ON creators (country);
CREATE INDEX idx_creators_status  ON creators (status);

-- =============================================================================
-- 2. CREATOR DAILY PERFORMANCE
-- One row per creator per day — aggregated totals across all content types
-- =============================================================================
CREATE TABLE creator_daily_performance (
    id                      TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
    creator_id              TEXT NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
    report_date             DATE NOT NULL,
    currency                VARCHAR(3) NOT NULL DEFAULT 'IDR',

    -- GMV
    total_gmv               DECIMAL(18,4) NOT NULL DEFAULT 0,
    affiliate_gmv           DECIMAL(18,4) NOT NULL DEFAULT 0,
    affiliate_live_gmv      DECIMAL(18,4) NOT NULL DEFAULT 0,
    affiliate_video_gmv     DECIMAL(18,4) NOT NULL DEFAULT 0,
    direct_gmv              DECIMAL(18,4) NOT NULL DEFAULT 0,
    live_direct_gmv         DECIMAL(18,4) NOT NULL DEFAULT 0,
    video_direct_gmv        DECIMAL(18,4) NOT NULL DEFAULT 0,

    -- Orders
    total_orders            INTEGER NOT NULL DEFAULT 0,
    affiliate_orders        INTEGER NOT NULL DEFAULT 0,
    affiliate_live_orders   INTEGER NOT NULL DEFAULT 0,
    affiliate_video_orders  INTEGER NOT NULL DEFAULT 0,
    direct_orders           INTEGER NOT NULL DEFAULT 0,
    live_direct_orders      INTEGER NOT NULL DEFAULT 0,
    video_direct_orders     INTEGER NOT NULL DEFAULT 0,

    -- Items & Commission
    items_sold              INTEGER NOT NULL DEFAULT 0,
    estimated_commission    DECIMAL(18,4) NOT NULL DEFAULT 0,
    refund_gmv              DECIMAL(18,4) NOT NULL DEFAULT 0,
    refunded_items          INTEGER NOT NULL DEFAULT 0,

    -- Content Metrics
    total_video_views       BIGINT NOT NULL DEFAULT 0,
    total_likes             BIGINT NOT NULL DEFAULT 0,
    total_shares            INTEGER NOT NULL DEFAULT 0,
    total_comments          INTEGER NOT NULL DEFAULT 0,
    videos_posted           INTEGER NOT NULL DEFAULT 0,
    live_sessions           INTEGER NOT NULL DEFAULT 0,

    -- Follower Snapshot
    follower_count          INTEGER NOT NULL DEFAULT 0,
    follower_growth         INTEGER NOT NULL DEFAULT 0,

    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_creator_daily UNIQUE (creator_id, report_date)
);

CREATE INDEX idx_cdp_report_date       ON creator_daily_performance (report_date);
CREATE INDEX idx_cdp_creator_date      ON creator_daily_performance (creator_id, report_date);

-- =============================================================================
-- 3. CREATOR PRODUCTS
-- One row per creator + product + day
-- Matches all 27 columns from TikTok "Creator Product" report
-- =============================================================================
CREATE TABLE creator_products (
    id                          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
    creator_id                  TEXT NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
    report_date                 DATE NOT NULL,
    currency                    VARCHAR(3) NOT NULL DEFAULT 'IDR',

    -- Product Identity
    product_id                  TEXT NOT NULL,
    product_name                TEXT NOT NULL,

    -- Affiliate Performance
    affiliate_gmv               DECIMAL(18,4) NOT NULL DEFAULT 0,
    affiliate_live_gmv          DECIMAL(18,4) NOT NULL DEFAULT 0,
    affiliate_video_gmv         DECIMAL(18,4) NOT NULL DEFAULT 0,
    affiliate_orders            INTEGER NOT NULL DEFAULT 0,
    affiliate_live_orders       INTEGER NOT NULL DEFAULT 0,
    affiliate_video_orders      INTEGER NOT NULL DEFAULT 0,

    -- Direct Performance
    direct_gmv                  DECIMAL(18,4) NOT NULL DEFAULT 0,
    live_direct_gmv             DECIMAL(18,4) NOT NULL DEFAULT 0,
    video_direct_gmv            DECIMAL(18,4) NOT NULL DEFAULT 0,
    product_card_direct_gmv     DECIMAL(18,4) NOT NULL DEFAULT 0,
    direct_orders               INTEGER NOT NULL DEFAULT 0,
    live_direct_orders          INTEGER NOT NULL DEFAULT 0,
    video_direct_orders         INTEGER NOT NULL DEFAULT 0,
    product_card_orders         INTEGER NOT NULL DEFAULT 0,

    -- Items Sold Breakdown
    items_sold                  INTEGER NOT NULL DEFAULT 0,
    live_products_sold          INTEGER NOT NULL DEFAULT 0,
    video_products_sold         INTEGER NOT NULL DEFAULT 0,
    product_card_products_sold  INTEGER NOT NULL DEFAULT 0,

    -- Refunds
    direct_refund_gmv           DECIMAL(18,4) NOT NULL DEFAULT 0,
    refunded_items              INTEGER NOT NULL DEFAULT 0,

    -- Rates (stored as decimal: 7.27% → 0.0727)
    ctr                         DECIMAL(8,4),
    ctor                        DECIMAL(8,4),

    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_creator_product UNIQUE (creator_id, report_date, product_id)
);

CREATE INDEX idx_cp_report_date   ON creator_products (report_date);
CREATE INDEX idx_cp_creator_date  ON creator_products (creator_id, report_date);
CREATE INDEX idx_cp_product_id    ON creator_products (product_id);

-- =============================================================================
-- 4. CREATOR LIVES
-- One row per creator + live session + day
-- =============================================================================
CREATE TABLE creator_lives (
    id                          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
    creator_id                  TEXT NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
    report_date                 DATE NOT NULL,
    currency                    VARCHAR(3) NOT NULL DEFAULT 'IDR',

    -- Live Identity
    live_session_id             TEXT,
    live_title                  TEXT,

    -- Timing
    start_time                  TIMESTAMPTZ,
    end_time                    TIMESTAMPTZ,
    duration_seconds            INTEGER NOT NULL DEFAULT 0,

    -- Viewership
    peak_viewers                INTEGER NOT NULL DEFAULT 0,
    average_viewers             INTEGER NOT NULL DEFAULT 0,
    total_viewers               INTEGER NOT NULL DEFAULT 0,
    unique_viewers              INTEGER NOT NULL DEFAULT 0,
    new_followers_from_live     INTEGER NOT NULL DEFAULT 0,

    -- Engagement
    likes                       BIGINT NOT NULL DEFAULT 0,
    comments                    INTEGER NOT NULL DEFAULT 0,
    shares                      INTEGER NOT NULL DEFAULT 0,

    -- Commerce
    affiliate_live_gmv          DECIMAL(18,4) NOT NULL DEFAULT 0,
    affiliate_live_orders       INTEGER NOT NULL DEFAULT 0,
    live_direct_gmv             DECIMAL(18,4) NOT NULL DEFAULT 0,
    live_direct_orders          INTEGER NOT NULL DEFAULT 0,
    live_items_sold             INTEGER NOT NULL DEFAULT 0,
    estimated_commission        DECIMAL(18,4) NOT NULL DEFAULT 0,

    -- Rates
    live_click_rate             DECIMAL(8,4),
    live_conversion_rate        DECIMAL(8,4),

    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_creator_live UNIQUE (creator_id, report_date, live_session_id)
);

CREATE INDEX idx_cl_report_date   ON creator_lives (report_date);
CREATE INDEX idx_cl_creator_date  ON creator_lives (creator_id, report_date);

-- =============================================================================
-- 5. CREATOR VIDEOS
-- One row per creator + video + day
-- Matches all 20 columns from TikTok "Creator Video" report
-- =============================================================================
CREATE TABLE creator_videos (
    id                          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
    creator_id                  TEXT NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
    report_date                 DATE NOT NULL,
    currency                    VARCHAR(3) NOT NULL DEFAULT 'IDR',

    -- Video Identity
    video_id                    TEXT NOT NULL,
    video_name                  TEXT,
    post_time                   TIMESTAMPTZ,

    -- Video Metrics
    duration_seconds            INTEGER NOT NULL DEFAULT 0,
    views                       BIGINT NOT NULL DEFAULT 0,
    likes                       BIGINT NOT NULL DEFAULT 0,
    shares                      INTEGER NOT NULL DEFAULT 0,
    comments                    INTEGER NOT NULL DEFAULT 0,

    -- Commerce
    affiliate_video_gmv         DECIMAL(18,4) NOT NULL DEFAULT 0,
    affiliate_video_orders      INTEGER NOT NULL DEFAULT 0,
    direct_gmv                  DECIMAL(18,4) NOT NULL DEFAULT 0,
    items_sold                  INTEGER NOT NULL DEFAULT 0,
    estimated_commission        DECIMAL(18,4) NOT NULL DEFAULT 0,

    -- Rates (stored as decimal: 6.36% → 0.0636)
    video_ctr                   DECIMAL(8,4),
    video_ctor                  DECIMAL(8,4),
    rpm                         DECIMAL(18,4),         -- Revenue per 1K views
    completion_rate             DECIMAL(8,4),

    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_creator_video UNIQUE (creator_id, report_date, video_id)
);

CREATE INDEX idx_cv_report_date   ON creator_videos (report_date);
CREATE INDEX idx_cv_creator_date  ON creator_videos (creator_id, report_date);
CREATE INDEX idx_cv_video_id      ON creator_videos (video_id);

-- =============================================================================
-- 6. DATA SYNC LOGS
-- Track every import/sync operation for auditability
-- =============================================================================
CREATE TABLE data_sync_logs (
    id                TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
    creator_id        TEXT REFERENCES creators(id) ON DELETE SET NULL,
    sync_type         sync_type NOT NULL,
    source            TEXT NOT NULL DEFAULT 'TIKTOK_REPORT',
    report_date_from  DATE,
    report_date_to    DATE,
    rows_processed    INTEGER NOT NULL DEFAULT 0,
    rows_failed       INTEGER NOT NULL DEFAULT 0,
    status            sync_status NOT NULL DEFAULT 'PENDING',
    error_message     TEXT,
    started_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at      TIMESTAMPTZ
);

CREATE INDEX idx_dsl_type_status ON data_sync_logs (sync_type, status);
CREATE INDEX idx_dsl_started     ON data_sync_logs (started_at);

-- =============================================================================
-- AUTO-UPDATE TRIGGER for updated_at columns
-- =============================================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_creators_updated_at
    BEFORE UPDATE ON creators
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_cdp_updated_at
    BEFORE UPDATE ON creator_daily_performance
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_cp_updated_at
    BEFORE UPDATE ON creator_products
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_cl_updated_at
    BEFORE UPDATE ON creator_lives
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_cv_updated_at
    BEFORE UPDATE ON creator_videos
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
