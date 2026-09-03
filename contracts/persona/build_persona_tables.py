# -*- coding: utf-8 -*-
"""중첩 페르소나 JSON 을 계약이 정의한 평탄 테이블 8종으로 만든다.

    simulator/personas/data/personas_*.json      사람 1명 + reviews[] 배열
        |
        v
    contracts/persona/data/<sample>/<table>.jsonl    grain 별 평탄 테이블

계약 원본은 `contracts/persona-schema.md` 다. 컬럼·타입·nullable 은 이 파일의
TABLE_SPECS 에 그대로 옮겨 두었고, `validate_persona_tables.py` 가 같은 표를 읽어
산출물을 검사한다. 표를 두 벌 두면 조용히 갈라지므로 원본은 여기 하나다.

왜 평탄화가 필요한가
    페르소나 JSON 은 사람 하나에 리뷰가 매달린 중첩 구조다. 계약은 grain 별
    테이블을 정의한다. DW 의 dim_persona_segment 도, Processed 의 persona join 도
    평탄 테이블을 전제한다. 지금까지 이 변환이 없어서 계약이 실제로 산출
    가능한지 확인된 적이 없었다.

만들지 않는 것
    simulation_run · scenario (계약 §10) 는 생성기 **실행** 산출물이라 페르소나
    평탄화 단계에 원천이 없다.

실행
    py contracts/persona/build_persona_tables.py --sample PA:10
    py contracts/persona/build_persona_tables.py --sample PC:100 --out contracts/persona/data
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import OrderedDict
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "batch", "jobs"))

import holdout_rule as hr                                    # noqa: E402
from persona_split import SPLIT_VERSION, split_of            # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

AGENT_PERSONAS = os.path.join(ROOT, "simulator", "personas", "data", "personas_100_agent.json")
BATCH_PERSONAS = os.path.join(ROOT, "simulator", "personas", "data", "personas_9900.json")
PRODUCTS = os.path.join(ROOT, "batch", "ingest", "data", "products_200.json")
DEFAULT_OUT = os.path.join(HERE, "data")

SOURCE_FILES = {"PA": AGENT_PERSONAS, "PC": BATCH_PERSONAS}

# 계약 §7.4 — split_of() 가 쓰는 결정론적 규칙. 별도 파일 없이 재현된다.
SPLIT_RULE = "md5(split_version|persona_id)[:8] % 10 -> 0-5:train, 6-7:valid, 8-9:test"

# 계약 §8.1 — Persona segment 로 허용되는 6종. generator_type·concern 은 아니다.
SEGMENT_TYPES = ("skin_type", "skin_tone", "hair_color", "eye_color",
                 "review_bucket", "persona_source")

# 계약 §8.2 — 속성별 Affinity 가중치. combination 은 skin_type 을 쓰지 않는다.
AFFINITY_WEIGHTS = {"skin_type": 0.40, "skin_tone": 0.40, "hair_color": 0.10, "eye_color": 0.10}
AFFINITY_WEIGHTS_COMBINATION = {"skin_type": 0.00, "skin_tone": 0.80, "hair_color": 0.10, "eye_color": 0.10}

S, N = "string", False          # nullable=N
Y = True                        # nullable=Y

# (column, type, nullable) — contracts/persona-schema.md 의 표를 그대로 옮긴 것
TABLE_SPECS = OrderedDict([
    ("persona_profile", {
        "contract": "§4",
        "grain": ["persona_id"],
        "columns": [
            ("persona_id", S, N), ("author_id", S, Y), ("user_id", S, N),
            ("persona_source", S, N), ("skin_type", S, N), ("skin_tone", S, N),
            ("eye_color", S, Y), ("hair_color", S, Y), ("stratum", S, N),
            ("review_bucket", S, N), ("n_reviews", "int", N), ("n_products", "int", N),
            ("n_positive", "int", N), ("n_negative", "int", N), ("n_neutral", "int", N),
            ("avg_rating", "double", Y), ("profile_version", S, N),
            ("profile_scope", S, N), ("created_at", "timestamp", N),
            ("updated_at", "timestamp", N),
        ],
    }),
    ("persona_profile_eval", {
        "contract": "§5",
        "grain": ["persona_id"],
        "columns": [
            ("persona_id", S, N), ("profile_scope", S, N), ("skin_type", S, N),
            ("skin_tone", S, N), ("eye_color", S, Y), ("hair_color", S, Y),
            ("n_reviews_seed", "int", N), ("n_products_seed", "int", N),
            ("avg_rating_seed", "double", Y), ("profile_version", S, N),
            ("split_version", S, N),
        ],
    }),
    ("persona_review_history", {
        "contract": "§6",
        "grain": ["persona_id", "review_id"],
        "columns": [
            ("persona_id", S, N), ("review_id", S, N), ("author_id", S, Y),
            ("source_product_id", S, N), ("group_id", S, Y),
            ("canonical_product_id", S, N), ("product_name", S, Y),
            ("brand_name", S, Y), ("rating", "int", Y), ("is_recommended", "boolean", Y),
            ("review_title", S, Y), ("review_text", S, Y), ("submission_time", "date", Y),
            ("helpfulness", "double", Y), ("total_feedback_count", "int", Y),
            ("total_pos_feedback_count", "int", Y), ("total_neg_feedback_count", "int", Y),
            ("skin_type", S, Y), ("skin_tone", S, Y), ("skin_tone_raw", S, Y),
            ("eye_color", S, Y), ("hair_color", S, Y), ("product_rank", "int", Y),
            ("evaluation_role", S, N), ("is_simulation_context", "boolean", N),
        ],
    }),
    ("persona_seed_product", {
        "contract": "§7.2",
        "grain": ["persona_id", "canonical_product_id"],
        "columns": [
            ("persona_id", S, N), ("canonical_product_id", S, N), ("product_id", S, N),
            ("source_review_ids", "array<string>", N), ("last_reviewed_at", "date", Y),
            ("avg_seed_rating", "double", Y), ("is_positive_seed", "boolean", Y),
            ("initial_event_weight", "double", Y), ("is_seen", "boolean", N),
        ],
    }),
    ("persona_holdout_target", {
        "contract": "§7.3",
        "grain": ["persona_id", "target_canonical_product_id"],
        "columns": [
            ("persona_id", S, N), ("target_canonical_product_id", S, N),
            ("target_product_id", S, N), ("target_source_product_id", S, Y),
            ("target_review_id", S, N), ("target_rating", "int", Y),
            ("target_is_recommended", "boolean", Y), ("target_submission_time", "date", Y),
            ("target_label", S, N), ("is_holdout_eligible", "boolean", N),
        ],
    }),
    ("persona_evaluation_split", {
        "contract": "§7.4",
        "grain": ["persona_id"],
        "columns": [
            ("persona_id", S, N), ("evaluation_split", S, N),
            ("split_rule", S, N), ("split_version", S, N),
        ],
    }),
    ("bridge_persona_segment", {
        "contract": "§8.1",
        "grain": ["persona_id", "segment_type", "segment_value"],
        "columns": [
            ("persona_id", S, N), ("segment_type", S, N), ("segment_value", S, N),
            ("valid_from", "date", Y), ("valid_to", "date", Y),
            ("updated_at", "timestamp", Y),
        ],
    }),
    ("persona_attribute_affinity_input", {
        "contract": "§8.2",
        "grain": ["persona_id"],
        "columns": [
            ("persona_id", S, N), ("skin_type", S, N), ("skin_tone", S, N),
            ("hair_color", S, Y), ("eye_color", S, Y),
            ("skin_type_weight", "double", N), ("skin_tone_weight", "double", N),
            ("hair_color_weight", "double", N), ("eye_color_weight", "double", N),
        ],
    }),
])


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _row(spec, values):
    """계약이 정의한 컬럼 순서대로만 내보낸다. 없는 값은 명시적 None 이다."""
    return OrderedDict((col, values.get(col)) for col, _, _ in spec["columns"])


def build_profile(persona):
    return _row(TABLE_SPECS["persona_profile"], persona)


def build_review_history(persona, roles, product_ids):
    spec = TABLE_SPECS["persona_review_history"]
    rows = []
    for review in persona.get("reviews", []):
        role = roles.get(review["review_id"], hr.SEED)
        values = dict(review)
        values.update({
            "persona_id": persona["persona_id"],
            "author_id": persona.get("author_id"),
            "source_product_id": review.get("product_id"),
            "canonical_product_id": hr.canonical_product_id(review),
            "evaluation_role": role,
            "is_simulation_context": hr.is_simulation_context(role),
        })
        rows.append(_row(spec, values))
    return rows


def build_seed_product(persona, roles):
    """seed 리뷰를 canonical 상품으로 묶는다.

    같은 상품에 리뷰를 두 번 이상 쓴 사람이 있어 (원천의 59%) 상품 단위로
    합쳐야 grain 이 맞는다.
    """
    spec = TABLE_SPECS["persona_seed_product"]
    grouped = OrderedDict()
    for review in hr.order_by_recency(persona.get("reviews", [])):
        if roles.get(review["review_id"]) != hr.SEED:
            continue
        canonical = hr.canonical_product_id(review)
        bucket = grouped.setdefault(canonical, {"review_ids": [], "ratings": [], "dates": []})
        bucket["review_ids"].append(review["review_id"])
        if review.get("rating") is not None:
            bucket["ratings"].append(review["rating"])
        if review.get("submission_time") is not None:
            bucket["dates"].append(str(review["submission_time"]))

    rows = []
    for canonical, bucket in grouped.items():
        ratings = bucket["ratings"]
        avg = round(sum(ratings) / len(ratings), 4) if ratings else None
        rows.append(_row(spec, {
            "persona_id": persona["persona_id"],
            "canonical_product_id": canonical,
            "product_id": canonical,
            "source_review_ids": sorted(bucket["review_ids"]),
            "last_reviewed_at": max(bucket["dates"]) if bucket["dates"] else None,
            "avg_seed_rating": avg,
            "is_positive_seed": (avg >= hr.POSITIVE_RATING_MIN) if avg is not None else None,
            # 산식이 recommendation-io-spec.md 에 없다. 지어내지 않고 비운다.
            "initial_event_weight": None,
            # persona-design.md §6 — seed 상품은 추천 후보에서 하드 제외한다
            "is_seen": True,
        }))
    return rows


def build_holdout_target(persona, decision):
    if decision is None or decision["role"] != hr.HOLDOUT_TARGET:
        return []
    review = decision["review"]
    return [_row(TABLE_SPECS["persona_holdout_target"], {
        "persona_id": persona["persona_id"],
        "target_canonical_product_id": decision["canonical_product_id"],
        "target_product_id": decision["canonical_product_id"],
        "target_source_product_id": review.get("product_id"),
        "target_review_id": review["review_id"],
        "target_rating": review.get("rating"),
        "target_is_recommended": review.get("is_recommended"),
        "target_submission_time": review.get("submission_time"),
        "target_label": decision["label"],
        "is_holdout_eligible": decision["is_holdout_eligible"],
    })]


def build_profile_eval(persona, roles):
    """holdout 을 뺀 seed 만으로 Profile 을 다시 만든다.

    속성은 **최신 seed 리뷰** 값을 쓴다. full Profile 값을 그대로 가져오면
    숨긴 리뷰의 값이 평가에 새어든다.
    """
    seeds = hr.seed_reviews(persona.get("reviews", []), roles)
    attrs = {}
    for key in ("skin_type", "skin_tone", "eye_color", "hair_color"):
        attrs[key] = next((r.get(key) for r in seeds if r.get(key) is not None), None)

    ratings = [r["rating"] for r in seeds if r.get("rating") is not None]
    products = {hr.canonical_product_id(r) for r in seeds}
    return _row(TABLE_SPECS["persona_profile_eval"], {
        "persona_id": persona["persona_id"],
        "profile_scope": "eval",
        "n_reviews_seed": len(seeds),
        "n_products_seed": len(products),
        "avg_rating_seed": round(sum(ratings) / len(ratings), 4) if ratings else None,
        "profile_version": persona.get("profile_version"),
        "split_version": SPLIT_VERSION,
        **attrs,
    })


def build_evaluation_split(persona):
    return _row(TABLE_SPECS["persona_evaluation_split"], {
        "persona_id": persona["persona_id"],
        "evaluation_split": split_of(persona["persona_id"]),
        "split_rule": SPLIT_RULE,
        "split_version": SPLIT_VERSION,
    })


def build_segments(persona):
    spec = TABLE_SPECS["bridge_persona_segment"]
    rows = []
    for segment_type in SEGMENT_TYPES:
        value = persona.get(segment_type)
        if value is None:                       # segment_value 는 nullable=N 이다
            continue
        rows.append(_row(spec, {
            "persona_id": persona["persona_id"],
            "segment_type": segment_type,
            "segment_value": value,
            "valid_from": None,
            "valid_to": None,
            "updated_at": persona.get("updated_at"),
        }))
    return rows


def build_affinity_input(persona):
    base = (AFFINITY_WEIGHTS_COMBINATION if persona.get("skin_type") == "combination"
            else AFFINITY_WEIGHTS)
    weights = {k: (v if persona.get(k) is not None else 0.0) for k, v in base.items()}
    total = sum(weights.values())
    if total and abs(total - 1.0) > 1e-9:       # NULL 속성이 있으면 합 1.0 로 되돌린다
        weights = {k: round(v / total, 6) for k, v in weights.items()}
    return _row(TABLE_SPECS["persona_attribute_affinity_input"], {
        "persona_id": persona["persona_id"],
        "skin_type": persona.get("skin_type"),
        "skin_tone": persona.get("skin_tone"),
        "hair_color": persona.get("hair_color"),
        "eye_color": persona.get("eye_color"),
        "skin_type_weight": weights["skin_type"],
        "skin_tone_weight": weights["skin_tone"],
        "hair_color_weight": weights["hair_color"],
        "eye_color_weight": weights["eye_color"],
    })


def build(personas, product_ids):
    """페르소나 목록 -> {table: [row, ...]}"""
    tables = {name: [] for name in TABLE_SPECS}
    for persona in personas:
        reviews = persona.get("reviews", [])
        roles, decision = hr.classify(reviews, product_ids)

        tables["persona_profile"].append(build_profile(persona))
        tables["persona_profile_eval"].append(build_profile_eval(persona, roles))
        tables["persona_review_history"].extend(build_review_history(persona, roles, product_ids))
        tables["persona_seed_product"].extend(build_seed_product(persona, roles))
        tables["persona_holdout_target"].extend(build_holdout_target(persona, decision))
        tables["persona_evaluation_split"].append(build_evaluation_split(persona))
        tables["bridge_persona_segment"].extend(build_segments(persona))
        tables["persona_attribute_affinity_input"].append(build_affinity_input(persona))
    return tables


def parse_sample(text):
    """'PA:10' -> ('PA', 10). 'PC:all' -> ('PC', None)"""
    band, _, size = text.partition(":")
    band = band.upper()
    if band not in SOURCE_FILES:
        raise ValueError(f"알 수 없는 대역: {band} (PA|PC)")
    if size in ("", "all"):
        return band, None
    return band, int(size)


def sample_id(band, size):
    return f"{band.lower()}{'all' if size is None else f'{size:03d}'}"


def write_tables(tables, out_dir, manifest):
    os.makedirs(out_dir, exist_ok=True)
    for name, rows in tables.items():
        path = os.path.join(out_dir, f"{name}.jsonl")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    with open(os.path.join(out_dir, "_manifest.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write("\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description="페르소나 JSON -> 계약 평탄 테이블")
    ap.add_argument("--sample", default="PA:10",
                    help="대역:인원. 예 PA:10 · PA:100 · PC:100 · PC:all")
    ap.add_argument("--out", default=DEFAULT_OUT, help="산출 루트 디렉터리")
    args = ap.parse_args(argv)

    band, size = parse_sample(args.sample)
    personas = _load(SOURCE_FILES[band])
    personas.sort(key=lambda p: p["persona_id"])
    if size is not None:
        personas = personas[:size]

    product_ids = {p["product_id"] for p in _load(PRODUCTS)}
    tables = build(personas, product_ids)

    sid = sample_id(band, size)
    out_dir = os.path.join(args.out, sid)
    manifest = {
        "sample_id": sid,
        "persona_band": band,
        "persona_count": len(personas),
        "persona_source_file": os.path.relpath(SOURCE_FILES[band], ROOT).replace("\\", "/"),
        "product_catalog": os.path.relpath(PRODUCTS, ROOT).replace("\\", "/"),
        "product_count": len(product_ids),
        "contract": "contracts/persona-schema.md",
        "holdout_rule": "contract-7.1",
        "split_version": SPLIT_VERSION,
        "profile_versions": sorted({p.get("profile_version") for p in personas}),
        "row_counts": {name: len(rows) for name, rows in tables.items()},
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    write_tables(tables, out_dir, manifest)

    print(f"[{sid}] 페르소나 {len(personas):,}명 -> {os.path.relpath(out_dir, ROOT)}")
    for name, rows in tables.items():
        print(f"  {name:<34} {len(rows):>7,}행  ({TABLE_SPECS[name]['contract']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
