-- 회원가입 동의 기록을 member 에 추가한다.
-- 필수(이용약관·개인정보 수집·이용)는 동의 시각, 선택(피부 정보·둘러본 기록 연결)은 동의했을 때만 시각을 남긴다.
-- consent_version 은 가입 때 보여 준 약관 판이다. 기존 회원(시드·PA 페르소나)은 전부 NULL 로 남는다.
-- 기존 DB/볼륨에 재실행해도 안전하도록, 모든 DDL은 존재 여부를 확인한 뒤 수행한다.
SET @schema_name = DATABASE();

SET @has_col = (
  SELECT COUNT(*) FROM information_schema.columns
  WHERE table_schema = @schema_name AND table_name = 'member'
    AND column_name = 'terms_agreed_at'
);
SET @sql = IF(@has_col = 0,
  'ALTER TABLE member ADD COLUMN terms_agreed_at DATETIME(6) NULL AFTER eye_color_code',
  'SELECT 1'
);
PREPARE statement FROM @sql; EXECUTE statement; DEALLOCATE PREPARE statement;

SET @has_col = (
  SELECT COUNT(*) FROM information_schema.columns
  WHERE table_schema = @schema_name AND table_name = 'member'
    AND column_name = 'privacy_agreed_at'
);
SET @sql = IF(@has_col = 0,
  'ALTER TABLE member ADD COLUMN privacy_agreed_at DATETIME(6) NULL AFTER terms_agreed_at',
  'SELECT 1'
);
PREPARE statement FROM @sql; EXECUTE statement; DEALLOCATE PREPARE statement;

SET @has_col = (
  SELECT COUNT(*) FROM information_schema.columns
  WHERE table_schema = @schema_name AND table_name = 'member'
    AND column_name = 'skin_info_agreed_at'
);
SET @sql = IF(@has_col = 0,
  'ALTER TABLE member ADD COLUMN skin_info_agreed_at DATETIME(6) NULL AFTER privacy_agreed_at',
  'SELECT 1'
);
PREPARE statement FROM @sql; EXECUTE statement; DEALLOCATE PREPARE statement;

SET @has_col = (
  SELECT COUNT(*) FROM information_schema.columns
  WHERE table_schema = @schema_name AND table_name = 'member'
    AND column_name = 'behavior_link_agreed_at'
);
SET @sql = IF(@has_col = 0,
  'ALTER TABLE member ADD COLUMN behavior_link_agreed_at DATETIME(6) NULL AFTER skin_info_agreed_at',
  'SELECT 1'
);
PREPARE statement FROM @sql; EXECUTE statement; DEALLOCATE PREPARE statement;

SET @has_col = (
  SELECT COUNT(*) FROM information_schema.columns
  WHERE table_schema = @schema_name AND table_name = 'member'
    AND column_name = 'consent_version'
);
SET @sql = IF(@has_col = 0,
  'ALTER TABLE member ADD COLUMN consent_version VARCHAR(32) NULL AFTER behavior_link_agreed_at',
  'SELECT 1'
);
PREPARE statement FROM @sql; EXECUTE statement; DEALLOCATE PREPARE statement;
