-- Runs automatically on first container start via /docker-entrypoint-initdb.d.
-- Creates the ohlcv_bars hypertable that app/marketdata/models.py's OHLCVBar maps to.

CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS ohlcv_bars (
    symbol      VARCHAR(16)          NOT NULL,
    timeframe   VARCHAR(4)           NOT NULL,
    "timestamp" TIMESTAMPTZ          NOT NULL,
    open        NUMERIC(18, 6)       NOT NULL,
    high        NUMERIC(18, 6)       NOT NULL,
    low         NUMERIC(18, 6)       NOT NULL,
    close       NUMERIC(18, 6)       NOT NULL,
    volume      NUMERIC(18, 2)       DEFAULT 0,
    source      VARCHAR(32)          NOT NULL,
    PRIMARY KEY (symbol, timeframe, "timestamp")
);

-- Partition on time (Timescale requirement); chunk interval tuned for intraday forex
-- data volume — 1 week per chunk keeps chunk count reasonable for years of 1m bars.
SELECT create_hypertable(
    'ohlcv_bars', 'timestamp',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS ix_ohlcv_symbol_timeframe_ts
    ON ohlcv_bars (symbol, timeframe, "timestamp" DESC);

-- Compress chunks older than 30 days to cut storage cost for backtesting history.
ALTER TABLE ohlcv_bars SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'symbol, timeframe'
);

SELECT add_compression_policy('ohlcv_bars', INTERVAL '30 days', if_not_exists => TRUE);

-- Raw tick table for scalping-grade backtesting/replay (higher volume, shorter retention).
CREATE TABLE IF NOT EXISTS ticks (
    symbol      VARCHAR(16)  NOT NULL,
    "timestamp" TIMESTAMPTZ  NOT NULL,
    bid         NUMERIC(18, 6) NOT NULL,
    ask         NUMERIC(18, 6) NOT NULL,
    source      VARCHAR(32)  NOT NULL
);

SELECT create_hypertable(
    'ticks', 'timestamp',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS ix_ticks_symbol_ts ON ticks (symbol, "timestamp" DESC);

SELECT add_retention_policy('ticks', INTERVAL '90 days', if_not_exists => TRUE);
