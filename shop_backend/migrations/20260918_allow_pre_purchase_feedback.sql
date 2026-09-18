-- 구매 전 feedback을 허용한다. 기존 컨테이너와 볼륨에 적용해도 안전한 멱등 migration.
SET @schema_name = DATABASE();

SET @is_nullable = (
  SELECT IS_NULLABLE
  FROM information_schema.columns
  WHERE table_schema = @schema_name
    AND table_name = 'feedback'
    AND column_name = 'order_item_id'
);

SET @sql = IF(@is_nullable = 'NO',
  'ALTER TABLE feedback MODIFY COLUMN order_item_id VARCHAR(64) NULL',
  'SELECT 1'
);
PREPARE statement FROM @sql; EXECUTE statement; DEALLOCATE PREPARE statement;
