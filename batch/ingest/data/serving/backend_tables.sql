-- 추천 파생 테이블 (batch/jobs/export_backend_tables.py 가 만든 CSV 적재용)
--
-- vocab_version 이 다른 행을 섞지 마십시오. 차원 순서가 어휘집에 묶여 있어
-- 버전이 다르면 ingredient_id 와 벡터 위치의 대응이 깨집니다.
--
-- product_id 는 상품 테이블의 키를 그대로 씁니다. FK 는 그쪽 스키마에 맞춰
-- 붙이십시오 (여기서는 걸지 않았습니다).

CREATE TABLE feature_block (
  block_name    VARCHAR(32)  NOT NULL,
  block_offset  INT          NOT NULL,   -- 148차원 벡터 안에서의 시작 위치
  dim           INT          NOT NULL,
  block_weight  DECIMAL(4,2) NULL,
  encoding      VARCHAR(32)  NOT NULL,
  vocab_version VARCHAR(8)   NOT NULL,
  PRIMARY KEY (vocab_version, block_name)
);

CREATE TABLE ingredient_vocab (
  ingredient_id INT          NOT NULL,   -- ingredient 블록 안에서의 차원 위치
  ingredient    VARCHAR(64)  NOT NULL,   -- 계약 원문. API 키로 이것을 쓸 것
  label_ko      VARCHAR(64)  NULL,       -- 화면 표시용. 키로 쓰지 말 것
  doc_freq      INT          NOT NULL,   -- 이 성분을 가진 상품 수
  vocab_version VARCHAR(8)   NOT NULL,
  PRIMARY KEY (vocab_version, ingredient_id),
  UNIQUE KEY uk_ingredient (vocab_version, ingredient)
);

CREATE TABLE concern_vocab (
  concern_id    INT          NOT NULL,
  concern       VARCHAR(64)  NOT NULL,
  label_ko      VARCHAR(64)  NULL,
  doc_freq      INT          NOT NULL,
  vocab_version VARCHAR(8)   NOT NULL,
  PRIMARY KEY (vocab_version, concern_id),
  UNIQUE KEY uk_concern (vocab_version, concern)
);

CREATE TABLE product_ingredient (
  product_id      VARCHAR(16)  NOT NULL,
  ingredient_id   INT          NOT NULL,
  ingredient      VARCHAR(64)  NOT NULL,
  position_weight DECIMAL(6,4) NOT NULL,  -- 0~1. 함량이 아니라 배합 순서 기반
  source          VARCHAR(8)   NOT NULL,  -- 'parsed' = 전성분에서 복원. 'tag'(원본 태그) 는 2026-09-10 부터 안 나온다(계약 §3.1), 열은 호환용
  vocab_version   VARCHAR(8)   NOT NULL,
  PRIMARY KEY (vocab_version, product_id, ingredient_id),
  KEY ix_ingredient (vocab_version, ingredient_id)
);

CREATE TABLE product_concern (
  product_id    VARCHAR(16)  NOT NULL,
  concern_rank  TINYINT      NOT NULL,   -- 1 = 리뷰가 가장 많이 말한 고민
  concern_id    INT          NOT NULL,
  concern       VARCHAR(64)  NOT NULL,
  score         DECIMAL(8,4) NOT NULL,
  vocab_version VARCHAR(8)   NOT NULL,
  PRIMARY KEY (vocab_version, product_id, concern_rank)
);

CREATE TABLE ingredient_skin_affinity (
  skin_type     VARCHAR(16)  NOT NULL,   -- combination | dry | normal | oily
  ingredient_id INT          NOT NULL,
  ingredient    VARCHAR(64)  NOT NULL,
  share         DECIMAL(8,5) NOT NULL,   -- 그 피부타입 안에서의 비중 (합 1.0)
  n_products    INT          NOT NULL,   -- 근거가 된 상품 수. 작으면 인용 주의
  vocab_version VARCHAR(8)   NOT NULL,
  PRIMARY KEY (vocab_version, skin_type, ingredient_id)
);
