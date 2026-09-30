-- 회원 탈퇴를 기록할 자리를 만든다 (2026-09-29).
--
-- 탈퇴는 행을 지우지 않는다(soft delete). 주문·결제·정산·리뷰·의견이 member_id 로 묶여 있고(FK RESTRICT)
-- 거래·이용 기록은 5년 보존하기 때문이다. 대신 status 를 WITHDRAWN 으로 바꾸고, 이메일·닉네임·피부 프로필·
-- 비밀번호 해시를 지운다 (MemberWithdrawalService). 여기서는 그 두 칸만 더한다.
--   1) member.status ENUM 에 'WITHDRAWN'
--   2) member.withdrawn_at DATETIME(6) NULL — 탈퇴 시각. 보존 기간(5년) 계산의 기준이 된다
--
-- member 만 건드린다. seller_account·admin_account 의 status ENUM 은 그대로 둔다.
-- 기존 shop_backend DB에 적용한다. 재실행에도 안전하도록 멱등 처리한다.
-- 새 DB는 mysql-erd.sql에 이미 반영되어 있다. 앱(ddl-auto: validate)보다 먼저 적용해야 한다.
SET @schema_name = DATABASE();

SET @status_type = (
  SELECT COLUMN_TYPE FROM information_schema.columns
  WHERE table_schema = @schema_name AND table_name = 'member' AND column_name = 'status'
);
SET @sql = IF(@status_type NOT LIKE '%''WITHDRAWN''%',
  'ALTER TABLE member MODIFY COLUMN status ENUM(''ACTIVE'',''INACTIVE'',''LOCKED'',''WITHDRAWN'') NOT NULL DEFAULT ''ACTIVE''',
  'SELECT 1'
);
PREPARE statement FROM @sql; EXECUTE statement; DEALLOCATE PREPARE statement;

SET @has_withdrawn_at = (
  SELECT COUNT(*) FROM information_schema.columns
  WHERE table_schema = @schema_name AND table_name = 'member' AND column_name = 'withdrawn_at'
);
SET @sql = IF(@has_withdrawn_at = 0,
  'ALTER TABLE member ADD COLUMN withdrawn_at DATETIME(6) NULL AFTER status',
  'SELECT 1'
);
PREPARE statement FROM @sql; EXECUTE statement; DEALLOCATE PREPARE statement;
