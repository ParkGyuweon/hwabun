# -*- coding: utf-8 -*-
"""Mart Parquet 스키마 -> MySQL ``dw`` DDL.

    data/<run>/marts/<mart>/            Spark 가 쓴 Parquet
        |
        v
    contracts/dw/schema.sql             조회 테이블 + staging 템플릿

왜 생성하나
    Mart 14종 280 컬럼을 손으로 옮기면 Mart 가 바뀔 때 조용히 갈라진다. 실제
    스키마에서 만들면 갈라질 수 없고, Mart 를 고친 뒤 다시 돌려 차이를 본다.

규칙은 어디에 있나
    타입 매핑 · VARCHAR 길이 · NULL 정책 · PRIMARY KEY 순서는 계약
    ``contracts/dw-schema.md`` §7 이 정본이다. 이 파일은 그 표를 코드로 옮긴
    것이고, 숫자를 여기서 바꾸면 계약과 갈라진다. 계약을 먼저 고친다.

    NULL 은 **데이터로 판정하지 않는다** (§7.5). Parquet 은 전부 nullable 로
    적히고, 지금 데이터에 NULL 이 없다는 것과 그 컬럼이 NULL 일 수 없다는 것은
    다르다. ``price_bin`` 이 그 예다 — 설계상 NULL 을 허용하는데 현재 카탈로그에
    가격 결측이 0개다.

실행
    py contracts/dw/build_ddl.py --marts data/e2e-235/marts
    py contracts/dw/build_ddl.py --marts data/e2e-235/marts --check
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
DEFAULT_OUT = os.path.join(HERE, "schema.sql")
DEFAULT_MARTS = os.path.join(ROOT, "data", "e2e-235", "marts")

SCHEMA = "dw"
CHARSET = "utf8mb4"
COLLATION = "utf8mb4_0900_ai_ci"


# ── §7.3 타입 매핑 ──────────────────────────────────────────────────────────
TYPE_MAP = {
    "date": "DATE",
    # TIMESTAMP 는 2038년 상한과 자동 갱신이 있다. 집계 시각에 둘 다 필요 없다.
    "timestamp": "DATETIME(3)",
    "bigint": "BIGINT",
    "int": "INT",
    "double": "DOUBLE",
    "decimal(18,2)": "DECIMAL(18,2)",
    # MySQL 에 boolean 이 없다.
    "boolean": "TINYINT(1)",
}

# ── §7.4 VARCHAR 길이 ──────────────────────────────────────────────────────
# 컬럼 이름이 같으면 어느 Mart 에 있든 길이가 같아야 한다. 다르면 조인과 적재에서
# 잘린다. 값은 재생 데이터 실측 최댓값에 여유를 둔 것이다.
VARCHAR = {
    "brand_id": 64,               # UUID 36자
    "destination_brand_id": 64,
    "product_id": 64,
    "user_id": 64,
    "category_id": 64,
    "ingredient": 128,
    "label_ko": 128,
    "banner_value": 128,          # 어휘집 원문. 실데이터 미실측
    "metric_name": 64,
    "cohort_key": 64,               # "{product_count_band}|{price_bin}"
    "product_count_band": 32,
    "brand_hash": 64,               # sha256 앞 16자
    "secondary_category": 64,
    "section_id": 64,
    "entry_source": 64,
    "last_content_kind": 64,
    "skin_type": 64,
    "content_kind": 64,
    "event_name": 64,
    "segment_type": 64,
    "segment_value": 64,          # 교차 축 "dry|fair"
    "algorithm": 64,
    "reference_source": 64,
    "generator_type": 64,
    "scenario_id": 64,
    "simulation_run_id": 64,
    "reason": 64,
    "policy_version": 32,
    "trait_policy_version": 32,
    "baseline_policy_version": 32,
    "vocab_version": 32,
    "trait": 32,
    "banner_type": 32,
    "trait_source": 32,
    "actor_type": 32,
    "source": 32,
    "price_bin": 32,
    "identity_scope": 32,
    "currency": 32,
}
VARCHAR_DEFAULT = 64

# ── §7.5 NULL 정책 ─────────────────────────────────────────────────────────
# grain key 인데도 NULL 을 허용하는 축. 근거는 계약에 있다.
NULLABLE_KEYS = {
    "generator_type",       # §2.2 Web 은 NULL
    "scenario_id",          # §2.2
    "simulation_run_id",    # §2.2
    "brand_id",             # §2.2 상품 미귀속 Mart
    "destination_brand_id",
    "price_bin",            # §4.6-1 가격 결측 보존
    "reason",               # §4.17 건너뛴 응답은 NULL
    "section_id",           # §4.4 섹션을 모르는 콘텐츠 Event 가 있다
    "content_kind",         # §4.4
}
# 이름만으로는 판정할 수 없는 예외. 같은 `brand_id` 라도 Fact 파생 Mart 에서는
# 상품 미귀속 때문에 NULL 이 가능하지만, 브랜드 Dimension 의 grain 이면 NULL 일 수
# 없다. 이 표에 있는 Mart 는 대리키 없이 PRIMARY KEY 를 그대로 쓴다.
NOT_NULL_KEYS_BY_MART = {
    "brand_cohort_dim": {"brand_id"},   # §3.7 grain/key = brand_id
}

# 비 key 인데도 NOT NULL 인 컬럼.
#   numerator·denominator 는 분모를 나중에 다시 검증하려고 저장하는 값이라
#   비어 있으면 저장할 이유가 없다 (§4.13).
#   banner_value_is_valid 는 Mart 가 매 행에 계산해 넣는 판정이다 (§4.10).
#   is_sample_sufficient 도 같다 (§4.9).
NOT_NULL_VALUES = {
    "mart_processed_at",
    "numerator",
    "denominator",
    "banner_value_is_valid",
    "is_sample_sufficient",
    "window_days",
    "min_sample_size",
    # 체류 합. 0 은 "머물지 않았다" 이지 "모른다" 가 아니다 (§4.4)
    "dwell_ms_sum",
    # 겹침 제외 체류 합. 같은 이유로 0 이지 NULL 이 아니다. 이름이 _count·
    # _sessions 로 끝나지 않아 기본 규칙(:329)이 NULL 로 판정하므로 여기 적는다 (§4.4)
    "co_visible_le2_dwell_ms_sum",
    # 세그먼트 체류 총합. dwell_ms_sum 의 합이라 항상 값이 있다 (§4.25)
    "segment_dwell_ms_sum",
    # 코호트 억제 판정과 임계값. Mart 가 매 행에 계산해 넣는다 (§4.18)
    "is_dominated",
    "is_suppressed",
    "dominance_ratio",
    "min_brand_count",
    "window_start_date",
    "window_end_date",
    # 코호트 배정표의 값 (§3.7)
    "brand_hash",
    "product_count_band",
    "commons_participating",
}
# 이름으로 판정할 수 없어 계약에서 직접 가져오는 것.
NULLABLE_VALUES = {
    "category_id",          # Dimension 스냅샷. 매칭되지 않을 수 있다
    "currency",
    "banner_value",         # new_brand 배너만 NULL
    "label_ko",
}


# ── projection 대상 ─────────────────────────────────────────────────────────
# 현재 MySQL projection 대상은 이 파일의 GRAINS 22종이다 (§7.2).
# EC2-2 Compose의 기본 실행과 적재 Job의 allowlist·DDL은 전체 GRAINS를
# 지원한다. Parquet 전용 Mart는 아래
# PARQUET_ONLY에 명시한다.
#
# grain 은 §4 그대로이고 인덱스 선두만 §7.6 의 접근 방식에 따라 바꾼다.
GRAINS = {
    "product_daily_kpi": [
        "brand_id", "event_date_kst", "product_id",
        "actor_type", "source", "generator_type",
        "scenario_id", "simulation_run_id",
    ],
    "brand_daily_kpi": [
        "brand_id", "event_date_kst",
        "actor_type", "source", "generator_type",
        "scenario_id", "simulation_run_id",
    ],
    "funnel_daily_kpi": [
        "brand_id", "funnel_date_kst", "product_id",
        "actor_type", "source", "generator_type",
        "scenario_id", "simulation_run_id",
    ],
    "persona_segment_daily_kpi": [
        "brand_id", "event_date_kst", "segment_type", "segment_value",
        "actor_type", "source", "generator_type",
        "scenario_id", "simulation_run_id",
    ],
    "brand_price_band_daily_kpi": [
        "brand_id", "event_date_kst", "price_bin", "currency",
        "actor_type", "source", "generator_type",
        "scenario_id", "simulation_run_id",
    ],
    "product_repurchase_daily": [
        "brand_id", "snapshot_date_kst", "product_id",
        "actor_type", "source", "generator_type",
        "scenario_id", "simulation_run_id",
    ],
    "brand_repurchase_daily": [
        "brand_id", "snapshot_date_kst",
        "actor_type", "source", "generator_type",
        "scenario_id", "simulation_run_id",
    ],
    "purchase_reason_daily": [
        "brand_id", "event_date_kst", "reason",
        "actor_type", "source", "generator_type",
        "scenario_id", "simulation_run_id",
    ],
    "ingredient_weekly_interest": [
        "interest_week_kst", "ingredient_id",
        "actor_type", "source", "generator_type",
        "scenario_id", "simulation_run_id",
    ],
    "product_exit_daily": [
        "brand_id", "event_date_kst", "product_id", "last_content_kind",
        "actor_type", "source", "generator_type",
        "scenario_id", "simulation_run_id",
    ],
    "segment_content_daily": [
        "brand_id", "event_date_kst", "skin_type", "content_kind",
        "actor_type", "source", "generator_type",
        "scenario_id", "simulation_run_id",
    ],
    "friction_daily": [
        "brand_id", "event_date_kst", "product_id", "section_id", "content_kind",
        "event_name",
        "actor_type", "source", "generator_type",
        "scenario_id", "simulation_run_id",
    ],
    "exit_daily": [
        "brand_id", "event_date_kst", "product_id",
        "actor_type", "source", "generator_type",
        "scenario_id", "simulation_run_id",
    ],
    "entry_source_daily": [
        "brand_id", "event_date_kst", "entry_source",
        "actor_type", "source", "generator_type",
        "scenario_id", "simulation_run_id",
    ],
    "content_daily_kpi": [
        "brand_id", "event_date_kst", "product_id", "section_id", "content_kind",
        "actor_type", "source", "generator_type",
        "scenario_id", "simulation_run_id",
    ],
    "content_conversion_daily": [
        "brand_id", "event_date_kst", "product_id", "content_kind",
        "actor_type", "source", "generator_type",
        "scenario_id", "simulation_run_id",
    ],
    "behavior_conversion_daily": [
        "brand_id", "event_date_kst", "product_id", "event_name",
        "actor_type", "source", "generator_type",
        "scenario_id", "simulation_run_id",
    ],
    "event_daily": [
        "brand_id", "event_date_kst", "event_name",
        "actor_type", "source", "generator_type",
        "scenario_id", "simulation_run_id",
    ],
    "segment_price_band_daily_kpi": [
        "brand_id", "event_date_kst", "segment_type", "segment_value",
        "price_bin", "currency",
        "actor_type", "source", "generator_type",
        "scenario_id", "simulation_run_id",
    ],
    "brand_cohort_dim": ["brand_id"],
    "commons_cohort_weekly": [
        "cohort_key", "snapshot_week_kst", "metric_name",
        "actor_type", "source", "generator_type",
        "scenario_id", "simulation_run_id",
    ],
    "user_trait_daily": [
        "user_id", "trait_date_kst", "trait", "identity_scope",
        "actor_type", "source", "scenario_id", "simulation_run_id",
    ],
}


# Mart 에는 있지만 projection 에서 빼는 컬럼 (§6-2 "API 조회에 불필요한 상세
# 컬럼을 생략할 수 있지만 key 와 KPI 의미를 바꾸지 않는다").
#
# 비율 컬럼은 빼지 않는다. 분모 규칙이 계약에만 있어서, 소비자가 count 에서 다시
# 나누면 분모를 틀릴 수 있다. 실제로 그 실수가 났다 — product_daily_kpi 의
# add_to_cart_rate 가 1,248행 중 323행에서 1.0 을 넘었고 원인이 분모였다.
# 값으로 실어 보내는 것이 규칙을 전달하는 방법이다.
EXCLUDED_COLUMNS = {
    ("product_daily_kpi", "revenue_amount"):
        "행동 로그 기반 금액이다. 계약 §6-4 가 매출·정산 합산을 금지한다",
    ("product_daily_kpi", "currency"):
        "revenue_amount 의 단위라 함께 뺀다",
}


# 의도적으로 MySQL 에 두지 않는 Mart. **"빠뜨린 것"과 구분하려고 적어 둔다.**
# 여기에도 GRAINS 에도 없는 Mart 가 나오면 생성기가 실패한다 — 새 Mart 가 생겼는데
# projection 여부를 아무도 판단하지 않은 상태이기 때문이다.
PARQUET_ONLY = {
    "banner_daily": "읽는 엔드포인트가 없다. 배너 성과는 Q5 검증과 기준선 대조에만 쓴다",
    "cross_brand_daily": "읽는 엔드포인트가 없다",
    "category_price_reference": "카탈로그 파생 참조표다. Event 를 읽지 않고 브랜드 축도 없다",
    "analytics_baseline": "배너 도입 전후를 비교하는 정책 스냅샷이다. 브랜드별 기간 조회가 아니다",
}

# MySQL 은 PRIMARY KEY 에 NULL 을 허용하지 않는다. NULL 이 가능한 축이 grain 에
# 있는 Mart는 UNIQUE KEY로 둘 수 없어(NULL은 중복으로 보지 않는다) 대리키를 쓴다.
# brand_cohort_dim처럼 grain이 NOT NULL인 Dimension은 직접 PRIMARY KEY를 쓴다.
# 중복 검사는 적재 Job이 §7.1 검증에서 수행한다.
SURROGATE_KEY = "dw_row_id"


def mysql_type(name: str, spark_type: str) -> str:
    if spark_type == "string":
        return f"VARCHAR({VARCHAR.get(name, VARCHAR_DEFAULT)})"
    if spark_type not in TYPE_MAP:
        raise ValueError(f"매핑 없는 타입: {name} {spark_type} (계약 §7.3 을 먼저 고친다)")
    return TYPE_MAP[spark_type]


def is_nullable(name: str, grain: list[str], mart: str | None = None) -> bool:
    if name in NOT_NULL_VALUES:
        return False
    if name in NULLABLE_VALUES:
        return True
    if name in grain:
        if name in NOT_NULL_KEYS_BY_MART.get(mart or "", ()):
            return False
        return name in NULLABLE_KEYS
    # count 는 0 이 "없음"이지 "모름"이 아니다. 비율·점수는 분모 0 이면 NULL 이다.
    return not name.endswith("_count") and not name.endswith("_sessions")


def render_table(mart: str, columns: list[tuple[str, str, bool]]) -> str:
    grain = GRAINS[mart]
    names = [name for name, _, _ in columns]
    missing = [column for column in grain if column not in names]
    if missing:
        raise ValueError(f"{mart}: grain 컬럼이 Mart 에 없다 {missing}")

    # grain 은 NULLABLE_KEYS 만 본다. NULLABLE_VALUES(예: currency)는 값 컬럼
    # 규칙이라 grain 판정에 섞이면 안 된다.
    needs_surrogate = any(
        column in NULLABLE_KEYS
        and column not in NOT_NULL_KEYS_BY_MART.get(mart, ())
        for column in grain
    )
    lines = [f"CREATE TABLE `{SCHEMA}`.`{mart}` ("]
    if needs_surrogate:
        lines.append(f"  `{SURROGATE_KEY}` BIGINT NOT NULL AUTO_INCREMENT,")
    # grain 을 앞에, 값 컬럼을 뒤에 둔다. 읽는 사람이 키를 먼저 본다.
    ordered = grain + [
        name for name in names
        if name not in grain and (mart, name) not in EXCLUDED_COLUMNS
    ]
    for name in ordered:
        spark_type = next(t for n, t, _ in columns if n == name)
        null = "NULL" if is_nullable(name, grain, mart) else "NOT NULL"
        lines.append(f"  `{name}` {mysql_type(name, spark_type)} {null},")
    if needs_surrogate:
        lines.append(f"  PRIMARY KEY (`{SURROGATE_KEY}`),")
        key = ", ".join(f"`{column}`" for column in grain)
        lines.append(f"  KEY `ix_{mart}__grain` ({key})")
    else:
        key = ", ".join(f"`{column}`" for column in grain)
        lines.append(f"  PRIMARY KEY ({key})")
    lines.append(f") ENGINE=InnoDB DEFAULT CHARSET={CHARSET} COLLATE={COLLATION};")
    return "\n".join(lines)


def build(schemas: dict) -> str:
    out = [
        "-- MySQL `dw` projection 스키마",
        "--",
        "-- 생성물이다. 직접 고치지 않는다.",
        "--   py contracts/dw/build_ddl.py --marts <실행 루트>/marts",
        "--",
        "-- 타입 매핑 · VARCHAR 길이 · NULL 정책 · PRIMARY KEY 순서의 정본은",
        "-- contracts/dw-schema.md §7 이다. 값을 바꾸려면 계약을 먼저 고친다.",
        "--",
        "-- 적재는 조회 테이블을 직접 지우지 않는다. 실행별 staging 에 넣고",
        "-- 건수·키 중복·필수값을 검증한 뒤 RENAME TABLE 로 교체한다 (§7.1).",
        "",
        f"CREATE DATABASE IF NOT EXISTS `{SCHEMA}`",
        f"  DEFAULT CHARACTER SET {CHARSET} COLLATE {COLLATION};",
        "",
    ]
    unclassified = sorted(set(schemas) - set(GRAINS) - set(PARQUET_ONLY))
    if unclassified:
        raise ValueError(
            "projection 여부가 정해지지 않은 Mart 가 있다: "
            f"{unclassified}. 소비자가 있으면 GRAINS 에, 없으면 PARQUET_ONLY 에 적는다"
        )
    for mart in sorted(GRAINS):
        if mart not in schemas:
            raise ValueError(f"{mart}: GRAINS 에 있는데 Mart 산출물이 없다")
        rows = schemas[mart]["rows"]
        note = "  -- 실데이터 미검증 (재생에서 0행)" if rows == 0 else ""
        out.append(f"-- {mart}{note}")
        out.append(render_table(mart, schemas[mart]["cols"]))
        out.append("")

    out.append("-- MySQL 로 옮기지 않는 Mart — Parquet 에만 둔다 (§7.2)")
    for mart in sorted(PARQUET_ONLY):
        out.append(f"--   {mart}: {PARQUET_ONLY[mart]}")
    out.append("")
    return "\n".join(out)


def load_schemas(marts_dir: str, schemas_json: str | None = None) -> dict:
    """Mart 스키마를 읽는다.

    기본은 Parquet 을 직접 읽는 것이고 pyspark 가 필요하다. Spark 이미지 밖에서
    돌릴 때는 ``--schemas`` 로 덤프한 JSON 을 준다 — 경로를 인자로 받는 이유는
    숨은 캐시가 조용히 낡는 것을 막기 위해서다.
    """

    if schemas_json:
        with open(schemas_json, encoding="utf-8") as stream:
            return json.load(stream)

    try:
        from pyspark.sql import SparkSession
    except ImportError:
        raise SystemExit(
            "pyspark 가 없다. Spark 이미지에서 돌리거나 --schemas 로 스키마 JSON 을 준다."
        )

    spark = (
        SparkSession.builder.master("local[2]")
        .appName("dw-ddl")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )
    try:
        schemas = {}
        for mart in sorted(os.listdir(marts_dir)):
            frame = spark.read.option("mergeSchema", "true").parquet(
                os.path.join(marts_dir, mart)
            )
            schemas[mart] = {
                "rows": frame.count(),
                "cols": [
                    (f.name, f.dataType.simpleString(), f.nullable)
                    for f in frame.schema.fields
                ],
            }
        return schemas
    finally:
        spark.stop()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Mart Parquet -> MySQL dw DDL")
    parser.add_argument("--marts", default=DEFAULT_MARTS, help="Mart Parquet 루트")
    parser.add_argument(
        "--schemas",
        help="Parquet 대신 읽을 스키마 JSON. Spark 이미지 밖에서 돌릴 때만 쓴다",
    )
    parser.add_argument("--out", default=DEFAULT_OUT, help="산출 SQL 경로")
    parser.add_argument(
        "--check",
        action="store_true",
        help="쓰지 않고 기존 파일과 다른지만 본다. 다르면 1로 종료",
    )
    args = parser.parse_args(argv)

    ddl = build(load_schemas(args.marts, args.schemas))
    if args.check:
        if not os.path.exists(args.out):
            print(f"{args.out} 없음 — 먼저 생성한다", file=sys.stderr)
            return 1
        with open(args.out, encoding="utf-8") as stream:
            if stream.read() == ddl:
                print("DDL 이 Mart 스키마와 일치한다")
                return 0
        print(f"{args.out} 이 Mart 스키마와 다르다 — 다시 생성한다", file=sys.stderr)
        return 1

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(ddl)
    print(f"{args.out} 생성 — 테이블 {len(GRAINS)}종")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
