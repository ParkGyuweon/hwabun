-- 기존 shop_backend DB에 적용한다. 재배포·Jenkins 재실행에도 안전하도록 각 변경을 멱등 처리한다.
-- 새 DB는 mysql-erd.sql에 이미 반영되어 있다.
SET @schema_name = DATABASE();

CREATE TABLE IF NOT EXISTS payment (
 payment_id VARCHAR(64) PRIMARY KEY, order_id VARCHAR(64) NOT NULL UNIQUE,
 provider VARCHAR(32) NOT NULL, provider_transaction_id VARCHAR(128) NULL,
 status ENUM('PAID','CANCELLED','FAILED') NOT NULL, amount DECIMAL(18,0) NOT NULL,
 currency CHAR(3) NOT NULL, paid_at DATETIME(6) NULL, verified_at DATETIME(6) NOT NULL,
 raw_status VARCHAR(32) NOT NULL,
 FOREIGN KEY(order_id) REFERENCES shop_order(order_id) ON DELETE RESTRICT,
 CHECK(amount >= 0)
);

SET @exists = (
  SELECT COUNT(*) FROM information_schema.columns
  WHERE table_schema = @schema_name AND table_name = 'shop_order' AND column_name = 'payment_id'
);
SET @sql = IF(@exists = 0,
  'ALTER TABLE shop_order ADD COLUMN payment_id VARCHAR(64) NULL AFTER paid_at',
  'SELECT 1'
);
PREPARE statement FROM @sql; EXECUTE statement; DEALLOCATE PREPARE statement;

SET @exists = (
  SELECT COUNT(*) FROM information_schema.columns
  WHERE table_schema = @schema_name AND table_name = 'shop_order' AND column_name = 'payment_provider'
);
SET @sql = IF(@exists = 0,
  'ALTER TABLE shop_order ADD COLUMN payment_provider VARCHAR(32) NULL AFTER payment_id',
  'SELECT 1'
);
PREPARE statement FROM @sql; EXECUTE statement; DEALLOCATE PREPARE statement;

SET @exists = (
  SELECT COUNT(*) FROM information_schema.columns
  WHERE table_schema = @schema_name AND table_name = 'shop_order' AND column_name = 'paid_amount'
);
SET @sql = IF(@exists = 0,
  'ALTER TABLE shop_order ADD COLUMN paid_amount DECIMAL(18,0) NULL AFTER payment_provider',
  'SELECT 1'
);
PREPARE statement FROM @sql; EXECUTE statement; DEALLOCATE PREPARE statement;

SET @exists = (
  SELECT COUNT(*) FROM information_schema.statistics
  WHERE table_schema = @schema_name AND table_name = 'shop_order' AND index_name = 'uq_order_payment'
);
SET @sql = IF(@exists = 0,
  'ALTER TABLE shop_order ADD UNIQUE KEY uq_order_payment (payment_id)',
  'SELECT 1'
);
PREPARE statement FROM @sql; EXECUTE statement; DEALLOCATE PREPARE statement;
