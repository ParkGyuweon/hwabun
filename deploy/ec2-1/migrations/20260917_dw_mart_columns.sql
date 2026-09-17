-- Existing MySQL dw installations only. Fresh installations use contracts/dw/schema.sql.
-- These new counters have no truthful backfill from old serving rows, so refuse
-- a partially migrated database if any affected table already contains data.
-- Run with the MySQL CLI as a privileged account; DELIMITER is a CLI directive.

DROP PROCEDURE IF EXISTS dw.migrate_20260917_mart_columns;
DELIMITER //
CREATE PROCEDURE dw.migrate_20260917_mart_columns()
BEGIN
  DECLARE present_count INT DEFAULT 0;

  SELECT COUNT(*) INTO present_count
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = 'dw' AND (
    (TABLE_NAME = 'product_daily_kpi' AND COLUMN_NAME IN (
      'recommendation_impression_count', 'banner_impression_count',
      'wishlist_count', 'impression_count'))
    OR (TABLE_NAME = 'funnel_daily_kpi' AND COLUMN_NAME = 'click_through_detail_sessions')
    OR (TABLE_NAME = 'content_daily_kpi' AND COLUMN_NAME = 'co_visible_le2_dwell_ms_sum')
  );

  IF present_count < 6 THEN
    IF EXISTS (SELECT 1 FROM dw.product_daily_kpi LIMIT 1)
       OR EXISTS (SELECT 1 FROM dw.funnel_daily_kpi LIMIT 1)
       OR EXISTS (SELECT 1 FROM dw.content_daily_kpi LIMIT 1) THEN
      SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'DW migration requires empty affected tables; preserve and rebuild populated marts first';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS
                   WHERE TABLE_SCHEMA = 'dw' AND TABLE_NAME = 'content_daily_kpi'
                     AND COLUMN_NAME = 'co_visible_le2_dwell_ms_sum') THEN
      ALTER TABLE dw.content_daily_kpi
        ADD COLUMN co_visible_le2_dwell_ms_sum BIGINT NOT NULL AFTER dwell_ms_sum;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS
                   WHERE TABLE_SCHEMA = 'dw' AND TABLE_NAME = 'funnel_daily_kpi'
                     AND COLUMN_NAME = 'click_through_detail_sessions') THEN
      ALTER TABLE dw.funnel_daily_kpi
        ADD COLUMN click_through_detail_sessions BIGINT NOT NULL AFTER direct_click_cart_sessions;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS
                   WHERE TABLE_SCHEMA = 'dw' AND TABLE_NAME = 'product_daily_kpi'
                     AND COLUMN_NAME = 'recommendation_impression_count') THEN
      ALTER TABLE dw.product_daily_kpi
        ADD COLUMN recommendation_impression_count BIGINT NOT NULL AFTER product_impression_count;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS
                   WHERE TABLE_SCHEMA = 'dw' AND TABLE_NAME = 'product_daily_kpi'
                     AND COLUMN_NAME = 'banner_impression_count') THEN
      ALTER TABLE dw.product_daily_kpi
        ADD COLUMN banner_impression_count BIGINT NOT NULL AFTER recommendation_impression_count;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS
                   WHERE TABLE_SCHEMA = 'dw' AND TABLE_NAME = 'product_daily_kpi'
                     AND COLUMN_NAME = 'wishlist_count') THEN
      ALTER TABLE dw.product_daily_kpi
        ADD COLUMN wishlist_count BIGINT NOT NULL AFTER variant_select_count;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS
                   WHERE TABLE_SCHEMA = 'dw' AND TABLE_NAME = 'product_daily_kpi'
                     AND COLUMN_NAME = 'impression_count') THEN
      ALTER TABLE dw.product_daily_kpi
        ADD COLUMN impression_count BIGINT NOT NULL AFTER product_interest_score;
    END IF;
  END IF;
END//
DELIMITER ;

CALL dw.migrate_20260917_mart_columns();
DROP PROCEDURE dw.migrate_20260917_mart_columns;
