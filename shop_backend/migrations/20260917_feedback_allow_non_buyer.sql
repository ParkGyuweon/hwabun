-- 구매하지 않은 사람도 사장님께 의견을 보낼 수 있게 한다.
--
-- `feedback.order_item_id` 가 NOT NULL 이라 구매 기록이 없으면 행을 만들 수조차 없었다. 서버도 그에 맞춰
-- 403 을 돌려줬고, 그래서 미구매자의 의견은 사장님에게 영영 닿지 않았다. 컬럼을 NULL 허용으로 바꾸고
-- 구매 여부는 그 값이 있는지로 읽는다 (있으면 구매자, NULL 이면 미구매자).
--
-- 복합 외래키 (order_item_id, product_id) 는 그대로 둔다. MySQL 은 복합 외래키의 컬럼 중 하나라도
-- NULL 이면 그 행의 참조를 검사하지 않으므로, 구매자 행의 무결성은 지금과 똑같이 지켜진다.
--
-- 기존 shop_backend DB에 적용한다. 재실행에도 안전하도록 멱등 처리한다.
-- 새 DB는 mysql-erd.sql에 이미 반영되어 있다.
SET @schema_name = DATABASE();

SET @nullable = (
  SELECT IS_NULLABLE FROM information_schema.columns
  WHERE table_schema = @schema_name AND table_name = 'feedback' AND column_name = 'order_item_id'
);
SET @sql = IF(@nullable = 'NO',
  'ALTER TABLE feedback MODIFY COLUMN order_item_id VARCHAR(64) NULL',
  'SELECT 1'
);
PREPARE statement FROM @sql; EXECUTE statement; DEALLOCATE PREPARE statement;
