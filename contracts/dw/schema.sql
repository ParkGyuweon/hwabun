-- MySQL `dw` projection 스키마
--
-- 생성물이다. 직접 고치지 않는다.
--   py contracts/dw/build_ddl.py --marts <실행 루트>/marts
--
-- 타입 매핑 · VARCHAR 길이 · NULL 정책 · PRIMARY KEY 순서의 정본은
-- contracts/dw-schema.md §7 이다. 값을 바꾸려면 계약을 먼저 고친다.
--
-- 적재는 조회 테이블을 직접 지우지 않는다. 실행별 staging 에 넣고
-- 건수·키 중복·필수값을 검증한 뒤 RENAME TABLE 로 교체한다 (§7.1).

CREATE DATABASE IF NOT EXISTS `dw`
  DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- behavior_conversion_daily
CREATE TABLE `dw`.`behavior_conversion_daily` (
  `dw_row_id` BIGINT NOT NULL AUTO_INCREMENT,
  `brand_id` VARCHAR(64) NULL,
  `event_date_kst` DATE NOT NULL,
  `product_id` VARCHAR(64) NOT NULL,
  `event_name` VARCHAR(64) NOT NULL,
  `actor_type` VARCHAR(32) NOT NULL,
  `source` VARCHAR(32) NOT NULL,
  `generator_type` VARCHAR(64) NULL,
  `scenario_id` VARCHAR(64) NULL,
  `simulation_run_id` VARCHAR(64) NULL,
  `done_sessions` BIGINT NOT NULL,
  `done_cart_sessions` BIGINT NOT NULL,
  `not_done_sessions` BIGINT NOT NULL,
  `not_done_cart_sessions` BIGINT NOT NULL,
  `mart_processed_at` DATETIME(3) NOT NULL,
  `done_cart_rate` DOUBLE NULL,
  `not_done_cart_rate` DOUBLE NULL,
  PRIMARY KEY (`dw_row_id`),
  KEY `ix_behavior_conversion_daily__grain` (`brand_id`, `event_date_kst`, `product_id`, `event_name`, `actor_type`, `source`, `generator_type`, `scenario_id`, `simulation_run_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- brand_cohort_dim
CREATE TABLE `dw`.`brand_cohort_dim` (
  `brand_id` VARCHAR(64) NOT NULL,
  `brand_hash` VARCHAR(64) NOT NULL,
  `product_count` BIGINT NOT NULL,
  `product_count_band` VARCHAR(32) NOT NULL,
  `dominant_price_bin` VARCHAR(64) NULL,
  `dominant_secondary_category` VARCHAR(64) NULL,
  `cohort_key` VARCHAR(64) NULL,
  `commons_participating` TINYINT(1) NOT NULL,
  `mart_processed_at` DATETIME(3) NOT NULL,
  PRIMARY KEY (`brand_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- brand_daily_kpi
CREATE TABLE `dw`.`brand_daily_kpi` (
  `dw_row_id` BIGINT NOT NULL AUTO_INCREMENT,
  `brand_id` VARCHAR(64) NULL,
  `event_date_kst` DATE NOT NULL,
  `actor_type` VARCHAR(32) NOT NULL,
  `source` VARCHAR(32) NOT NULL,
  `generator_type` VARCHAR(64) NULL,
  `scenario_id` VARCHAR(64) NULL,
  `simulation_run_id` VARCHAR(64) NULL,
  `impression_sessions` BIGINT NOT NULL,
  `click_sessions` BIGINT NOT NULL,
  `quick_look_sessions` BIGINT NOT NULL,
  `detail_view_sessions` BIGINT NOT NULL,
  `product_view_sessions` BIGINT NOT NULL,
  `information_view_sessions` BIGINT NOT NULL,
  `add_to_cart_sessions` BIGINT NOT NULL,
  `unique_user_count` BIGINT NOT NULL,
  `product_count_viewed` BIGINT NULL,
  `mart_processed_at` DATETIME(3) NOT NULL,
  `detail_entry_rate` DOUBLE NULL,
  `information_view_rate` DOUBLE NULL,
  `view_to_cart_rate` DOUBLE NULL,
  PRIMARY KEY (`dw_row_id`),
  KEY `ix_brand_daily_kpi__grain` (`brand_id`, `event_date_kst`, `actor_type`, `source`, `generator_type`, `scenario_id`, `simulation_run_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- brand_price_band_daily_kpi
CREATE TABLE `dw`.`brand_price_band_daily_kpi` (
  `dw_row_id` BIGINT NOT NULL AUTO_INCREMENT,
  `brand_id` VARCHAR(64) NULL,
  `event_date_kst` DATE NOT NULL,
  `price_bin` VARCHAR(32) NULL,
  `currency` VARCHAR(32) NULL,
  `actor_type` VARCHAR(32) NOT NULL,
  `source` VARCHAR(32) NOT NULL,
  `generator_type` VARCHAR(64) NULL,
  `scenario_id` VARCHAR(64) NULL,
  `simulation_run_id` VARCHAR(64) NULL,
  `session_count` BIGINT NOT NULL,
  `unique_user_count` BIGINT NOT NULL,
  `impression_sessions` BIGINT NOT NULL,
  `quick_look_sessions` BIGINT NOT NULL,
  `product_view_sessions` BIGINT NOT NULL,
  `detail_view_sessions` BIGINT NOT NULL,
  `add_to_cart_sessions` BIGINT NOT NULL,
  `purchase_sessions` BIGINT NOT NULL,
  `product_count` BIGINT NOT NULL,
  `mart_processed_at` DATETIME(3) NOT NULL,
  `detail_entry_rate` DOUBLE NULL,
  `view_to_cart_rate` DOUBLE NULL,
  `view_to_purchase_rate` DOUBLE NULL,
  PRIMARY KEY (`dw_row_id`),
  KEY `ix_brand_price_band_daily_kpi__grain` (`brand_id`, `event_date_kst`, `price_bin`, `currency`, `actor_type`, `source`, `generator_type`, `scenario_id`, `simulation_run_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- brand_repurchase_daily
CREATE TABLE `dw`.`brand_repurchase_daily` (
  `dw_row_id` BIGINT NOT NULL AUTO_INCREMENT,
  `brand_id` VARCHAR(64) NULL,
  `snapshot_date_kst` DATE NOT NULL,
  `actor_type` VARCHAR(32) NOT NULL,
  `source` VARCHAR(32) NOT NULL,
  `generator_type` VARCHAR(64) NULL,
  `scenario_id` VARCHAR(64) NULL,
  `simulation_run_id` VARCHAR(64) NULL,
  `buyer_count` BIGINT NOT NULL,
  `repeat_buyer_count` BIGINT NOT NULL,
  `purchase_order_count` BIGINT NOT NULL,
  `median_days_between_purchases` DOUBLE NULL,
  `mart_processed_at` DATETIME(3) NOT NULL,
  `repurchase_rate` DOUBLE NULL,
  `window_days` INT NOT NULL,
  `window_start_date` DATE NOT NULL,
  `window_end_date` DATE NOT NULL,
  `backend_order_count` BIGINT NOT NULL,
  `local_order_count` BIGINT NOT NULL,
  `kakaopay_order_count` BIGINT NOT NULL,
  `card_order_count` BIGINT NOT NULL,
  `test_order_count` BIGINT NOT NULL,
  `backend_paid_value` DECIMAL(18,2) NULL,
  `declared_restock_order_count` BIGINT NOT NULL,
  PRIMARY KEY (`dw_row_id`),
  KEY `ix_brand_repurchase_daily__grain` (`brand_id`, `snapshot_date_kst`, `actor_type`, `source`, `generator_type`, `scenario_id`, `simulation_run_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- category_price_reference
CREATE TABLE `dw`.`category_price_reference` (
  `secondary_category` VARCHAR(64) NOT NULL,
  `currency` VARCHAR(32) NOT NULL,
  `product_count` BIGINT NOT NULL,
  `observed_median_price` DECIMAL(18,2) NOT NULL,
  `global_product_count` BIGINT NOT NULL,
  `global_median_price` DECIMAL(18,2) NOT NULL,
  `is_sample_sufficient` TINYINT(1) NOT NULL,
  `reference_median_price` DECIMAL(18,2) NOT NULL,
  `reference_source` VARCHAR(64) NOT NULL,
  `min_sample_size` INT NOT NULL,
  `mart_processed_at` DATETIME(3) NOT NULL,
  PRIMARY KEY (`secondary_category`, `currency`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- commons_cohort_weekly
CREATE TABLE `dw`.`commons_cohort_weekly` (
  `dw_row_id` BIGINT NOT NULL AUTO_INCREMENT,
  `cohort_key` VARCHAR(64) NOT NULL,
  `snapshot_week_kst` DATE NOT NULL,
  `metric_name` VARCHAR(64) NOT NULL,
  `actor_type` VARCHAR(32) NOT NULL,
  `source` VARCHAR(32) NOT NULL,
  `generator_type` VARCHAR(64) NULL,
  `scenario_id` VARCHAR(64) NULL,
  `simulation_run_id` VARCHAR(64) NULL,
  `window_start_date` DATE NOT NULL,
  `window_end_date` DATE NOT NULL,
  `brand_count` BIGINT NOT NULL,
  `mart_processed_at` DATETIME(3) NOT NULL,
  `is_dominated` TINYINT(1) NOT NULL,
  `is_suppressed` TINYINT(1) NOT NULL,
  `is_sample_sufficient` TINYINT(1) NOT NULL,
  `p25` DOUBLE NULL,
  `p50` DOUBLE NULL,
  `p75` DOUBLE NULL,
  `min_brand_count` INT NOT NULL,
  `min_sample_size` INT NOT NULL,
  `dominance_ratio` DOUBLE NOT NULL,
  PRIMARY KEY (`dw_row_id`),
  KEY `ix_commons_cohort_weekly__grain` (`cohort_key`, `snapshot_week_kst`, `metric_name`, `actor_type`, `source`, `generator_type`, `scenario_id`, `simulation_run_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- content_conversion_daily
CREATE TABLE `dw`.`content_conversion_daily` (
  `dw_row_id` BIGINT NOT NULL AUTO_INCREMENT,
  `brand_id` VARCHAR(64) NULL,
  `event_date_kst` DATE NOT NULL,
  `product_id` VARCHAR(64) NOT NULL,
  `content_kind` VARCHAR(64) NULL,
  `actor_type` VARCHAR(32) NOT NULL,
  `source` VARCHAR(32) NOT NULL,
  `generator_type` VARCHAR(64) NULL,
  `scenario_id` VARCHAR(64) NULL,
  `simulation_run_id` VARCHAR(64) NULL,
  `category_id` VARCHAR(64) NULL,
  `viewed_sessions` BIGINT NOT NULL,
  `viewed_cart_sessions` BIGINT NOT NULL,
  `mart_processed_at` DATETIME(3) NOT NULL,
  `viewed_cart_rate` DOUBLE NULL,
  PRIMARY KEY (`dw_row_id`),
  KEY `ix_content_conversion_daily__grain` (`brand_id`, `event_date_kst`, `product_id`, `content_kind`, `actor_type`, `source`, `generator_type`, `scenario_id`, `simulation_run_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- content_daily_kpi
CREATE TABLE `dw`.`content_daily_kpi` (
  `dw_row_id` BIGINT NOT NULL AUTO_INCREMENT,
  `brand_id` VARCHAR(64) NULL,
  `event_date_kst` DATE NOT NULL,
  `product_id` VARCHAR(64) NOT NULL,
  `section_id` VARCHAR(64) NULL,
  `content_kind` VARCHAR(64) NULL,
  `actor_type` VARCHAR(32) NOT NULL,
  `source` VARCHAR(32) NOT NULL,
  `generator_type` VARCHAR(64) NULL,
  `scenario_id` VARCHAR(64) NULL,
  `simulation_run_id` VARCHAR(64) NULL,
  `category_id` VARCHAR(64) NULL,
  `section_view_count` BIGINT NOT NULL,
  `section_view_sessions` BIGINT NOT NULL,
  `dwell_ms_sum` BIGINT NOT NULL,
  `co_visible_le2_dwell_ms_sum` BIGINT NOT NULL,
  `accordion_expand_count` BIGINT NOT NULL,
  `text_selection_count` BIGINT NOT NULL,
  `text_copy_count` BIGINT NOT NULL,
  `matched_ingredient_count` BIGINT NOT NULL,
  `content_interest_score` DOUBLE NULL,
  `product_view_sessions` BIGINT NOT NULL,
  `ingredient_view_sessions` BIGINT NOT NULL,
  `review_view_sessions` BIGINT NOT NULL,
  `avg_dwell_ms_per_session` DOUBLE NULL,
  `ingredient_view_rate` DOUBLE NULL,
  `review_view_rate` DOUBLE NULL,
  `mart_processed_at` DATETIME(3) NOT NULL,
  PRIMARY KEY (`dw_row_id`),
  KEY `ix_content_daily_kpi__grain` (`brand_id`, `event_date_kst`, `product_id`, `section_id`, `content_kind`, `actor_type`, `source`, `generator_type`, `scenario_id`, `simulation_run_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- cross_brand_daily
CREATE TABLE `dw`.`cross_brand_daily` (
  `dw_row_id` BIGINT NOT NULL AUTO_INCREMENT,
  `destination_brand_id` VARCHAR(64) NOT NULL,
  `event_date_kst` DATE NOT NULL,
  `actor_type` VARCHAR(32) NOT NULL,
  `source` VARCHAR(32) NOT NULL,
  `generator_type` VARCHAR(64) NULL,
  `scenario_id` VARCHAR(64) NULL,
  `simulation_run_id` VARCHAR(64) NULL,
  `brand_view_sessions` BIGINT NOT NULL,
  `cross_brand_entry_sessions` BIGINT NOT NULL,
  `recommendation_cross_brand_entry_sessions` BIGINT NOT NULL,
  `banner_cross_brand_entry_sessions` BIGINT NOT NULL,
  `mart_processed_at` DATETIME(3) NOT NULL,
  `cross_brand_entry_rate` DOUBLE NULL,
  `recommendation_cross_brand_entry_rate` DOUBLE NULL,
  `banner_cross_brand_entry_rate` DOUBLE NULL,
  `recommendation_share_of_cross_brand_entries` DOUBLE NULL,
  `banner_share_of_cross_brand_entries` DOUBLE NULL,
  PRIMARY KEY (`dw_row_id`),
  KEY `ix_cross_brand_daily__grain` (`destination_brand_id`, `event_date_kst`, `actor_type`, `source`, `generator_type`, `scenario_id`, `simulation_run_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- entry_source_daily
CREATE TABLE `dw`.`entry_source_daily` (
  `dw_row_id` BIGINT NOT NULL AUTO_INCREMENT,
  `brand_id` VARCHAR(64) NULL,
  `event_date_kst` DATE NOT NULL,
  `entry_source` VARCHAR(64) NOT NULL,
  `actor_type` VARCHAR(32) NOT NULL,
  `source` VARCHAR(32) NOT NULL,
  `generator_type` VARCHAR(64) NULL,
  `scenario_id` VARCHAR(64) NULL,
  `simulation_run_id` VARCHAR(64) NULL,
  `product_view_sessions` BIGINT NOT NULL,
  `detail_view_sessions` BIGINT NOT NULL,
  `add_to_cart_sessions` BIGINT NOT NULL,
  `mart_processed_at` DATETIME(3) NOT NULL,
  `view_to_cart_rate` DOUBLE NULL,
  PRIMARY KEY (`dw_row_id`),
  KEY `ix_entry_source_daily__grain` (`brand_id`, `event_date_kst`, `entry_source`, `actor_type`, `source`, `generator_type`, `scenario_id`, `simulation_run_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- event_daily
CREATE TABLE `dw`.`event_daily` (
  `dw_row_id` BIGINT NOT NULL AUTO_INCREMENT,
  `brand_id` VARCHAR(64) NULL,
  `event_date_kst` DATE NOT NULL,
  `event_name` VARCHAR(64) NOT NULL,
  `actor_type` VARCHAR(32) NOT NULL,
  `source` VARCHAR(32) NOT NULL,
  `generator_type` VARCHAR(64) NULL,
  `scenario_id` VARCHAR(64) NULL,
  `simulation_run_id` VARCHAR(64) NULL,
  `event_count` BIGINT NOT NULL,
  `unique_session_count` BIGINT NOT NULL,
  `unique_user_count` BIGINT NOT NULL,
  `mart_processed_at` DATETIME(3) NOT NULL,
  PRIMARY KEY (`dw_row_id`),
  KEY `ix_event_daily__grain` (`brand_id`, `event_date_kst`, `event_name`, `actor_type`, `source`, `generator_type`, `scenario_id`, `simulation_run_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- exit_daily
CREATE TABLE `dw`.`exit_daily` (
  `dw_row_id` BIGINT NOT NULL AUTO_INCREMENT,
  `brand_id` VARCHAR(64) NULL,
  `event_date_kst` DATE NOT NULL,
  `product_id` VARCHAR(64) NOT NULL,
  `actor_type` VARCHAR(32) NOT NULL,
  `source` VARCHAR(32) NOT NULL,
  `generator_type` VARCHAR(64) NULL,
  `scenario_id` VARCHAR(64) NULL,
  `simulation_run_id` VARCHAR(64) NULL,
  `detail_view_sessions` BIGINT NOT NULL,
  `exit_summary_sessions` BIGINT NOT NULL,
  `quick_exit_sessions` BIGINT NOT NULL,
  `mart_processed_at` DATETIME(3) NOT NULL,
  `quick_exit_rate` DOUBLE NULL,
  PRIMARY KEY (`dw_row_id`),
  KEY `ix_exit_daily__grain` (`brand_id`, `event_date_kst`, `product_id`, `actor_type`, `source`, `generator_type`, `scenario_id`, `simulation_run_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- friction_daily
CREATE TABLE `dw`.`friction_daily` (
  `dw_row_id` BIGINT NOT NULL AUTO_INCREMENT,
  `brand_id` VARCHAR(64) NULL,
  `event_date_kst` DATE NOT NULL,
  `product_id` VARCHAR(64) NOT NULL,
  `section_id` VARCHAR(64) NULL,
  `content_kind` VARCHAR(64) NULL,
  `event_name` VARCHAR(64) NOT NULL,
  `actor_type` VARCHAR(32) NOT NULL,
  `source` VARCHAR(32) NOT NULL,
  `generator_type` VARCHAR(64) NULL,
  `scenario_id` VARCHAR(64) NULL,
  `simulation_run_id` VARCHAR(64) NULL,
  `event_count` BIGINT NOT NULL,
  `friction_sessions` BIGINT NOT NULL,
  `detail_view_sessions` BIGINT NOT NULL,
  `friction_rate` DOUBLE NULL,
  `mart_processed_at` DATETIME(3) NOT NULL,
  PRIMARY KEY (`dw_row_id`),
  KEY `ix_friction_daily__grain` (`brand_id`, `event_date_kst`, `product_id`, `section_id`, `content_kind`, `event_name`, `actor_type`, `source`, `generator_type`, `scenario_id`, `simulation_run_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- funnel_daily_kpi
CREATE TABLE `dw`.`funnel_daily_kpi` (
  `dw_row_id` BIGINT NOT NULL AUTO_INCREMENT,
  `brand_id` VARCHAR(64) NULL,
  `funnel_date_kst` DATE NOT NULL,
  `product_id` VARCHAR(64) NOT NULL,
  `actor_type` VARCHAR(32) NOT NULL,
  `source` VARCHAR(32) NOT NULL,
  `generator_type` VARCHAR(64) NULL,
  `scenario_id` VARCHAR(64) NULL,
  `simulation_run_id` VARCHAR(64) NULL,
  `category_id` VARCHAR(64) NULL,
  `impression_sessions` BIGINT NOT NULL,
  `click_sessions` BIGINT NOT NULL,
  `quick_look_sessions` BIGINT NOT NULL,
  `quick_look_cart_sessions` BIGINT NOT NULL,
  `direct_click_sessions` BIGINT NOT NULL,
  `direct_click_cart_sessions` BIGINT NOT NULL,
  `click_through_detail_sessions` BIGINT NOT NULL,
  `detail_view_sessions` BIGINT NOT NULL,
  `product_view_sessions` BIGINT NOT NULL,
  `information_view_sessions` BIGINT NOT NULL,
  `add_to_cart_sessions` BIGINT NOT NULL,
  `checkout_sessions` BIGINT NOT NULL,
  `purchase_sessions` BIGINT NOT NULL,
  `mart_processed_at` DATETIME(3) NOT NULL,
  `impression_to_click_rate` DOUBLE NULL,
  `click_to_view_rate` DOUBLE NULL,
  `view_to_information_rate` DOUBLE NULL,
  `view_to_cart_rate` DOUBLE NULL,
  `cart_to_purchase_rate` DOUBLE NULL,
  `view_to_purchase_rate` DOUBLE NULL,
  `dropoff_after_impression_rate` DOUBLE NULL,
  `dropoff_after_view_rate` DOUBLE NULL,
  `dropoff_after_cart_rate` DOUBLE NULL,
  PRIMARY KEY (`dw_row_id`),
  KEY `ix_funnel_daily_kpi__grain` (`brand_id`, `funnel_date_kst`, `product_id`, `actor_type`, `source`, `generator_type`, `scenario_id`, `simulation_run_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ingredient_weekly_interest
CREATE TABLE `dw`.`ingredient_weekly_interest` (
  `dw_row_id` BIGINT NOT NULL AUTO_INCREMENT,
  `interest_week_kst` DATE NOT NULL,
  `ingredient_id` INT NOT NULL,
  `actor_type` VARCHAR(32) NOT NULL,
  `source` VARCHAR(32) NOT NULL,
  `generator_type` VARCHAR(64) NULL,
  `scenario_id` VARCHAR(64) NULL,
  `simulation_run_id` VARCHAR(64) NULL,
  `ingredient` VARCHAR(128) NULL,
  `label_ko` VARCHAR(128) NULL,
  `vocab_version` VARCHAR(32) NULL,
  `ingredient_interest_score` DOUBLE NULL,
  `direct_match_score` DOUBLE NULL,
  `product_attributed_score` DOUBLE NULL,
  `contributing_event_count` BIGINT NOT NULL,
  `ingredient_interest_share` DOUBLE NULL,
  `mart_processed_at` DATETIME(3) NOT NULL,
  PRIMARY KEY (`dw_row_id`),
  KEY `ix_ingredient_weekly_interest__grain` (`interest_week_kst`, `ingredient_id`, `actor_type`, `source`, `generator_type`, `scenario_id`, `simulation_run_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- persona_segment_daily_kpi
CREATE TABLE `dw`.`persona_segment_daily_kpi` (
  `dw_row_id` BIGINT NOT NULL AUTO_INCREMENT,
  `brand_id` VARCHAR(64) NULL,
  `event_date_kst` DATE NOT NULL,
  `segment_type` VARCHAR(64) NOT NULL,
  `segment_value` VARCHAR(64) NOT NULL,
  `actor_type` VARCHAR(32) NOT NULL,
  `source` VARCHAR(32) NOT NULL,
  `generator_type` VARCHAR(64) NULL,
  `scenario_id` VARCHAR(64) NULL,
  `simulation_run_id` VARCHAR(64) NULL,
  `segment_user_count` BIGINT NOT NULL,
  `session_count` BIGINT NOT NULL,
  `impression_sessions` BIGINT NOT NULL,
  `quick_look_sessions` BIGINT NOT NULL,
  `product_view_sessions` BIGINT NOT NULL,
  `detail_view_sessions` BIGINT NOT NULL,
  `add_to_cart_sessions` BIGINT NOT NULL,
  `purchase_sessions` BIGINT NOT NULL,
  `product_count_viewed` BIGINT NULL,
  `mart_processed_at` DATETIME(3) NOT NULL,
  `view_to_cart_rate` DOUBLE NULL,
  `view_to_purchase_rate` DOUBLE NULL,
  `detail_entry_rate` DOUBLE NULL,
  `avg_interest_score` DOUBLE NULL,
  PRIMARY KEY (`dw_row_id`),
  KEY `ix_persona_segment_daily_kpi__grain` (`brand_id`, `event_date_kst`, `segment_type`, `segment_value`, `actor_type`, `source`, `generator_type`, `scenario_id`, `simulation_run_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- product_daily_kpi
CREATE TABLE `dw`.`product_daily_kpi` (
  `dw_row_id` BIGINT NOT NULL AUTO_INCREMENT,
  `brand_id` VARCHAR(64) NULL,
  `event_date_kst` DATE NOT NULL,
  `product_id` VARCHAR(64) NOT NULL,
  `actor_type` VARCHAR(32) NOT NULL,
  `source` VARCHAR(32) NOT NULL,
  `generator_type` VARCHAR(64) NULL,
  `scenario_id` VARCHAR(64) NULL,
  `simulation_run_id` VARCHAR(64) NULL,
  `category_id` VARCHAR(64) NULL,
  `product_impression_count` BIGINT NOT NULL,
  `recommendation_impression_count` BIGINT NOT NULL,
  `banner_impression_count` BIGINT NOT NULL,
  `product_click_count` BIGINT NOT NULL,
  `quick_look_count` BIGINT NOT NULL,
  `product_view_count` BIGINT NOT NULL,
  `add_to_cart_count` BIGINT NOT NULL,
  `remove_from_cart_count` BIGINT NOT NULL,
  `purchase_count` BIGINT NOT NULL,
  `variant_select_count` BIGINT NOT NULL,
  `wishlist_count` BIGINT NOT NULL,
  `quick_look_close_open_detail_count` BIGINT NOT NULL,
  `purchase_quantity` BIGINT NULL,
  `quick_look_sessions` BIGINT NOT NULL,
  `product_view_sessions` BIGINT NOT NULL,
  `detail_view_sessions` BIGINT NOT NULL,
  `add_to_cart_sessions` BIGINT NOT NULL,
  `remove_from_cart_sessions` BIGINT NOT NULL,
  `purchase_sessions` BIGINT NOT NULL,
  `unique_user_count` BIGINT NOT NULL,
  `session_count` BIGINT NOT NULL,
  `mart_processed_at` DATETIME(3) NOT NULL,
  `product_interest_score` DOUBLE NULL,
  `impression_count` BIGINT NOT NULL,
  `product_ctr` DOUBLE NULL,
  `detail_entry_rate` DOUBLE NULL,
  `add_to_cart_rate` DOUBLE NULL,
  `purchase_rate` DOUBLE NULL,
  PRIMARY KEY (`dw_row_id`),
  KEY `ix_product_daily_kpi__grain` (`brand_id`, `event_date_kst`, `product_id`, `actor_type`, `source`, `generator_type`, `scenario_id`, `simulation_run_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- product_exit_daily
CREATE TABLE `dw`.`product_exit_daily` (
  `dw_row_id` BIGINT NOT NULL AUTO_INCREMENT,
  `brand_id` VARCHAR(64) NULL,
  `event_date_kst` DATE NOT NULL,
  `product_id` VARCHAR(64) NOT NULL,
  `last_content_kind` VARCHAR(64) NOT NULL,
  `actor_type` VARCHAR(32) NOT NULL,
  `source` VARCHAR(32) NOT NULL,
  `generator_type` VARCHAR(64) NULL,
  `scenario_id` VARCHAR(64) NULL,
  `simulation_run_id` VARCHAR(64) NULL,
  `exit_sessions` BIGINT NOT NULL,
  `mart_processed_at` DATETIME(3) NOT NULL,
  PRIMARY KEY (`dw_row_id`),
  KEY `ix_product_exit_daily__grain` (`brand_id`, `event_date_kst`, `product_id`, `last_content_kind`, `actor_type`, `source`, `generator_type`, `scenario_id`, `simulation_run_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- product_repurchase_daily
CREATE TABLE `dw`.`product_repurchase_daily` (
  `dw_row_id` BIGINT NOT NULL AUTO_INCREMENT,
  `brand_id` VARCHAR(64) NULL,
  `snapshot_date_kst` DATE NOT NULL,
  `product_id` VARCHAR(64) NOT NULL,
  `actor_type` VARCHAR(32) NOT NULL,
  `source` VARCHAR(32) NOT NULL,
  `generator_type` VARCHAR(64) NULL,
  `scenario_id` VARCHAR(64) NULL,
  `simulation_run_id` VARCHAR(64) NULL,
  `buyer_count` BIGINT NOT NULL,
  `repeat_buyer_count` BIGINT NOT NULL,
  `purchase_order_count` BIGINT NOT NULL,
  `median_days_between_purchases` DOUBLE NULL,
  `mart_processed_at` DATETIME(3) NOT NULL,
  `repurchase_rate` DOUBLE NULL,
  `window_days` INT NOT NULL,
  `window_start_date` DATE NOT NULL,
  `window_end_date` DATE NOT NULL,
  `backend_order_count` BIGINT NOT NULL,
  `local_order_count` BIGINT NOT NULL,
  `kakaopay_order_count` BIGINT NOT NULL,
  `card_order_count` BIGINT NOT NULL,
  `test_order_count` BIGINT NOT NULL,
  `backend_paid_value` DECIMAL(18,2) NULL,
  PRIMARY KEY (`dw_row_id`),
  KEY `ix_product_repurchase_daily__grain` (`brand_id`, `snapshot_date_kst`, `product_id`, `actor_type`, `source`, `generator_type`, `scenario_id`, `simulation_run_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- purchase_reason_daily
CREATE TABLE `dw`.`purchase_reason_daily` (
  `dw_row_id` BIGINT NOT NULL AUTO_INCREMENT,
  `brand_id` VARCHAR(64) NULL,
  `event_date_kst` DATE NOT NULL,
  `reason` VARCHAR(64) NULL,
  `actor_type` VARCHAR(32) NOT NULL,
  `source` VARCHAR(32) NOT NULL,
  `generator_type` VARCHAR(64) NULL,
  `scenario_id` VARCHAR(64) NULL,
  `simulation_run_id` VARCHAR(64) NULL,
  `order_count` BIGINT NOT NULL,
  `primary_order_count` BIGINT NOT NULL,
  `skipped_order_count` BIGINT NOT NULL,
  `trait_compared_order_count` BIGINT NOT NULL,
  `trait_matched_order_count` BIGINT NOT NULL,
  `mart_processed_at` DATETIME(3) NOT NULL,
  `reason_share` DOUBLE NULL,
  `trait_match_rate` DOUBLE NULL,
  PRIMARY KEY (`dw_row_id`),
  KEY `ix_purchase_reason_daily__grain` (`brand_id`, `event_date_kst`, `reason`, `actor_type`, `source`, `generator_type`, `scenario_id`, `simulation_run_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- segment_content_daily
CREATE TABLE `dw`.`segment_content_daily` (
  `dw_row_id` BIGINT NOT NULL AUTO_INCREMENT,
  `brand_id` VARCHAR(64) NULL,
  `event_date_kst` DATE NOT NULL,
  `skin_type` VARCHAR(64) NOT NULL,
  `content_kind` VARCHAR(64) NULL,
  `actor_type` VARCHAR(32) NOT NULL,
  `source` VARCHAR(32) NOT NULL,
  `generator_type` VARCHAR(64) NULL,
  `scenario_id` VARCHAR(64) NULL,
  `simulation_run_id` VARCHAR(64) NULL,
  `dwell_ms_sum` BIGINT NOT NULL,
  `dwell_sessions` BIGINT NOT NULL,
  `segment_dwell_ms_sum` BIGINT NOT NULL,
  `dwell_share` DOUBLE NULL,
  `mart_processed_at` DATETIME(3) NOT NULL,
  PRIMARY KEY (`dw_row_id`),
  KEY `ix_segment_content_daily__grain` (`brand_id`, `event_date_kst`, `skin_type`, `content_kind`, `actor_type`, `source`, `generator_type`, `scenario_id`, `simulation_run_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- segment_price_band_daily_kpi
CREATE TABLE `dw`.`segment_price_band_daily_kpi` (
  `dw_row_id` BIGINT NOT NULL AUTO_INCREMENT,
  `brand_id` VARCHAR(64) NULL,
  `event_date_kst` DATE NOT NULL,
  `segment_type` VARCHAR(64) NOT NULL,
  `segment_value` VARCHAR(64) NOT NULL,
  `price_bin` VARCHAR(32) NULL,
  `currency` VARCHAR(32) NULL,
  `actor_type` VARCHAR(32) NOT NULL,
  `source` VARCHAR(32) NOT NULL,
  `generator_type` VARCHAR(64) NULL,
  `scenario_id` VARCHAR(64) NULL,
  `simulation_run_id` VARCHAR(64) NULL,
  `segment_user_count` BIGINT NOT NULL,
  `session_count` BIGINT NOT NULL,
  `product_view_sessions` BIGINT NOT NULL,
  `detail_view_sessions` BIGINT NOT NULL,
  `add_to_cart_sessions` BIGINT NOT NULL,
  `purchase_sessions` BIGINT NOT NULL,
  `product_count` BIGINT NOT NULL,
  `mart_processed_at` DATETIME(3) NOT NULL,
  `view_to_cart_rate` DOUBLE NULL,
  `view_to_purchase_rate` DOUBLE NULL,
  PRIMARY KEY (`dw_row_id`),
  KEY `ix_segment_price_band_daily_kpi__grain` (`brand_id`, `event_date_kst`, `segment_type`, `segment_value`, `price_bin`, `currency`, `actor_type`, `source`, `generator_type`, `scenario_id`, `simulation_run_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- user_trait_daily
CREATE TABLE `dw`.`user_trait_daily` (
  `dw_row_id` BIGINT NOT NULL AUTO_INCREMENT,
  `user_id` VARCHAR(64) NOT NULL,
  `trait_date_kst` DATE NOT NULL,
  `trait` VARCHAR(32) NOT NULL,
  `identity_scope` VARCHAR(32) NOT NULL,
  `actor_type` VARCHAR(32) NOT NULL,
  `source` VARCHAR(32) NOT NULL,
  `scenario_id` VARCHAR(64) NULL,
  `simulation_run_id` VARCHAR(64) NULL,
  `trait_score` DOUBLE NULL,
  `contributing_event_count` BIGINT NOT NULL,
  `trait_rank` INT NULL,
  `is_primary_trait` TINYINT(1) NULL,
  `window_start_date` DATE NOT NULL,
  `window_end_date` DATE NOT NULL,
  `trait_policy_version` VARCHAR(32) NULL,
  `mart_processed_at` DATETIME(3) NOT NULL,
  PRIMARY KEY (`dw_row_id`),
  KEY `ix_user_trait_daily__grain` (`user_id`, `trait_date_kst`, `trait`, `identity_scope`, `actor_type`, `source`, `scenario_id`, `simulation_run_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- MySQL 로 옮기지 않는 Mart — Parquet 에만 둔다 (§7.2)
--   analytics_baseline: 배너 도입 전후를 비교하는 정책 스냅샷이다. 브랜드별 기간 조회가 아니다
--   banner_daily: 읽는 엔드포인트가 없다. 배너 성과는 Q5 검증과 기준선 대조에만 쓴다
