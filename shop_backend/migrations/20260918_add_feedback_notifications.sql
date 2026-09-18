-- 피드백 처리 이력과 인앱 알림을 추가한다.
-- 기존 DB/볼륨에 재실행해도 안전하도록, 모든 DDL은 존재 여부를 확인한 뒤 수행한다.
SET @schema_name = DATABASE();

-- feedback.status(VISIBLE/HIDDEN/DELETED)는 운영 노출 상태다.
-- 업체의 처리 상태는 별도 handling_status로 보관한다.
SET @has_handling_status = (
  SELECT COUNT(*) FROM information_schema.columns
  WHERE table_schema = @schema_name AND table_name = 'feedback'
    AND column_name = 'handling_status'
);
SET @sql = IF(@has_handling_status = 0,
  "ALTER TABLE feedback ADD COLUMN handling_status ENUM('OPEN','ACKNOWLEDGED','IMPLEMENTED') NOT NULL DEFAULT 'OPEN' AFTER status",
  'SELECT 1'
);
PREPARE statement FROM @sql; EXECUTE statement; DEALLOCATE PREPARE statement;

SET @has_last_responded_at = (
  SELECT COUNT(*) FROM information_schema.columns
  WHERE table_schema = @schema_name AND table_name = 'feedback'
    AND column_name = 'last_responded_at'
);
SET @sql = IF(@has_last_responded_at = 0,
  'ALTER TABLE feedback ADD COLUMN last_responded_at DATETIME(6) NULL AFTER handling_status',
  'SELECT 1'
);
PREPARE statement FROM @sql; EXECUTE statement; DEALLOCATE PREPARE statement;

CREATE TABLE IF NOT EXISTS feedback_response (
  feedback_response_id VARCHAR(64) PRIMARY KEY,
  feedback_id VARCHAR(64) NOT NULL,
  seller_account_id VARCHAR(64) NOT NULL,
  action ENUM('ACKNOWLEDGED','REPLIED','IMPLEMENTED') NOT NULL,
  body TEXT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  FOREIGN KEY (feedback_id) REFERENCES feedback(feedback_id) ON DELETE CASCADE,
  FOREIGN KEY (seller_account_id) REFERENCES seller_account(seller_account_id) ON DELETE RESTRICT,
  CHECK (action <> 'REPLIED' OR body IS NOT NULL),
  INDEX ix_feedback_response_feedback_created (feedback_id, created_at)
);

CREATE TABLE IF NOT EXISTS notification (
  notification_id VARCHAR(64) PRIMARY KEY,
  recipient_role ENUM('MEMBER','SELLER') NOT NULL,
  recipient_account_id VARCHAR(64) NOT NULL,
  type ENUM('FEEDBACK_CREATED','FEEDBACK_ACKNOWLEDGED','FEEDBACK_REPLIED','FEEDBACK_IMPLEMENTED') NOT NULL,
  feedback_id VARCHAR(64) NULL,
  title VARCHAR(200) NOT NULL,
  body VARCHAR(1000) NULL,
  payload_json JSON NULL,
  read_at DATETIME(6) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  FOREIGN KEY (feedback_id) REFERENCES feedback(feedback_id) ON DELETE SET NULL,
  INDEX ix_notification_recipient_read_created (recipient_role, recipient_account_id, read_at, created_at)
);
