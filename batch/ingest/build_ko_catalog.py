# -*- coding: utf-8 -*-
"""사이트 한국어화 데이터 — 검수본 대조표(md)를 프론트가 읽을 JSON 으로 옮긴다.

왜 파일로 두나
    한국어 상품명·설명·전성분·리뷰는 사람이 검수한 문장이라 코드에서 만들 수 없다.
    검수본은 사람이 읽는 표(20개 md) 형태이므로, 화면이 바로 쓸 수 있게
    **상품 ID·리뷰 ID 를 키로 한 JSON** 으로 한 번 변환해 둔다.

원칙 (docs/localization/…/00_교정_원칙과_검수결과.md, 01_열거값_대조.md)
    - 내부 키(category·highlights·skin type·badge·variant label 의 영문 값)는 그대로 둔다.
      어휘집·이벤트 계약·추천 벡터가 영문 키를 쓰기 때문이다. 화면 라벨만 labels-ko 로 바꾼다.
    - 브랜드명 영문 유지. 가격은 고정 환율 1 USD = 1,340.86 KRW, 100원 반올림.
    - 영문 원문은 바꾸지 않는다 — 이 스크립트가 표의 EN 열을 원본 JSON 과 대조해
      한 글자라도 다르면 실패시킨다. 그래서 표 행이 어느 상품·어느 리뷰인지 확실하다.

입력
    docs/localization/HWABUN_한국어화_검수본_20260909/01_열거값_대조.md
    docs/localization/HWABUN_한국어화_검수본_20260909/02~20_상품_*.md
    frontend/src/mocks/products.sample.json   (영문 원본, 대조용)
    frontend/src/mocks/reviews.sample.json    (영문 원본, review_id 부여용)

산출: contracts/localization/products-ko.json · reviews-ko.json · labels-ko.json
실행: python batch/ingest/build_ko_catalog.py
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
SRC = os.path.join(ROOT, "docs", "localization", "HWABUN_한국어화_검수본_20260909")
PRODUCTS = os.path.join(ROOT, "frontend", "src", "mocks", "products.sample.json")
REVIEWS = os.path.join(ROOT, "frontend", "src", "mocks", "reviews.sample.json")
OUT_DIR = os.path.join(ROOT, "contracts", "localization")

USD_KRW = 1340.86  # 09-09 결정, open.er-api.com 2026-09-09 00:02 UTC

# 표의 항목명 → ProductDescription 필드 (frontend/src/types/product.ts)
DESC_FIELDS = {
    "제품 소개": "what_it_is",
    "사용법": "suggested_usage",
    "추가 정보": "what_else",
    "피부 고민": "concerns_text",
    "주요 성분": "highlighted_ingredients",
    "피부 타입": "skin_type",
    "성분 특징(프리)": "ingredient_callouts",
    "브랜드 스토리": "brand_story",
    "임상 결과": "clinical_results",
}

# 01_열거값_대조.md 의 절 제목 → labels-ko 키
ENUM_SECTIONS = {
    "카테고리": "category",
    "하이라이트 태그": "highlights",
    "피부 고민": "skincare_concerns",
    "적합 피부 타입": "suitable_skin_types",
    "배지": "badges",
    "옵션 라벨": "variant_labels",
}


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def dump(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def logical_rows(text: str) -> list[str]:
    """셀 안에 줄바꿈이 들어간 표 행을 한 줄로 묶는다 (검수 스크립트와 같은 규칙)."""
    lines = text.splitlines()
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("|") and not re.search(r"(?<!\\)\|\s*$", line):
            row = [line]
            i += 1
            while i < len(lines):
                row.append(lines[i])
                if re.search(r"(?<!\\)\|\s*$", lines[i]):
                    break
                i += 1
            out.append("\n".join(row))
        else:
            out.append(line)
        i += 1
    return out


def cells(line: str) -> list[str] | None:
    if not line.startswith("|"):
        return None
    parts = re.split(r"(?<!\\)\|", line)  # 본문 안의 파이프는 \| 로 이스케이프돼 있다
    if len(parts) < 4:
        return None
    return [p.strip().replace("\\|", "|") for p in parts[1:-1]]


def md_to_text(cell: str) -> str | None:
    """표 셀 → 원본 문자열. <br> 은 줄바꿈, 빈 셀은 None."""
    if cell == "":
        return None
    return cell.replace("<br>", "\n")


def norm(s: str | None) -> str:
    """EN 대조용 정규화 — 표로 옮기며 접힌 공백만 무시한다."""
    if s is None:
        return ""
    return re.sub(r"\s+", " ", s).strip()


def bullets(cell: str) -> list[str]:
    """'· a<br>· b' → ['a', 'b']"""
    if not cell:
        return []
    return [b[2:] if b.startswith("· ") else b for b in cell.split("<br>")]


def krw(usd: float) -> int:
    return int(round(usd * USD_KRW / 100.0)) * 100


# --------------------------------------------------------------------------- 열거값
def build_labels() -> dict:
    text = open(os.path.join(SRC, "01_열거값_대조.md"), encoding="utf-8").read()
    labels: dict[str, dict[str, str]] = {}
    section = None
    for line in logical_rows(text):
        if line.startswith("## "):
            title = line[3:].split("—")[0].strip()
            section = next((v for k, v in ENUM_SECTIONS.items() if title.startswith(k)), None)
            if section is None:
                raise SystemExit(f"열거값 절을 모른다: {title}")
            labels[section] = {}
            continue
        c = cells(line)
        if not c or len(c) != 2 or c[0] in ("원문 (EN)", "---"):
            continue
        labels[section][c[0]] = c[1]
    return labels


# --------------------------------------------------------------------------- 상품·리뷰
def parse_product_files():
    """(product_id, 절 이름, 행 셀 목록) 을 순서대로 낸다."""
    files = sorted(f for f in os.listdir(SRC) if re.match(r"\d\d_상품_.*\.md$", f))
    for name in files:
        text = open(os.path.join(SRC, name), encoding="utf-8").read()
        pid = section = None
        for line in logical_rows(text):
            m = re.match(r"`(P\d+)` · ", line)
            if m:
                pid = m.group(1)
                continue
            if line.startswith("### "):
                section = line[4:].split(" (")[0]
                continue
            c = cells(line)
            if not c or c[0] in ("항목", "별점", "---"):
                continue
            yield name, pid, section, c


def main() -> None:
    products = {p["product_id"]: p for p in load(PRODUCTS)}
    reviews_by_pid: dict[str, list[dict]] = {}
    for r in load(REVIEWS):
        reviews_by_pid.setdefault(r["product_id"], []).append(r)

    labels = build_labels()
    out_products: dict[str, dict] = {}
    out_reviews: dict[str, dict] = {}
    review_cursor: Counter = Counter()
    mismatch: list[str] = []
    stats: Counter = Counter()

    for fname, pid, section, c in parse_product_files():
        if pid not in products:
            raise SystemExit(f"{fname}: 원본에 없는 상품 {pid}")
        src = products[pid]
        entry = out_products.setdefault(
            pid,
            {
                "product_name": None,
                "size": None,
                "price_krw": krw(src["price_usd"]),
                "variant_labels": {},
                "description": None,
                "ingredients": None,
            },
        )

        # ---- 리뷰 (10건): 별점 | 리뷰어 | EN | KO — 원본 순서와 같고, EN 본문으로 재확인
        if section == "리뷰":
            if len(c) != 4:
                raise SystemExit(f"{fname} {pid}: 리뷰 행 열 수 {len(c)}")
            idx = review_cursor[pid]
            review_cursor[pid] += 1
            r = reviews_by_pid[pid][idx]
            title = r["review_title"] or ""
            expect = (f"**{title}**\n" if title else "") + (r["review_text"] or "")
            if norm(md_to_text(c[2])) != norm(expect):
                mismatch.append(f"review {r['review_id']} EN≠원본")
                continue
            ko = md_to_text(c[3]) or ""
            ko_title = None
            m = re.match(r"\*\*(.*?)\*\*\n?", ko, re.S)
            if title and m:
                ko_title, ko = m.group(1), ko[m.end():]
            out_reviews[r["review_id"]] = {
                "product_id": pid,
                "review_title": ko_title,
                "review_text": ko,
            }
            stats["review"] += 1
            continue

        if len(c) != 3:
            raise SystemExit(f"{fname} {pid} {section}: 열 수 {len(c)} — {c[0]}")
        field, en, ko = c

        # ---- 기본 정보
        if section == "기본 정보":
            if field == "상품명":
                if en != src["product_name"]:
                    mismatch.append(f"{pid} 상품명 EN≠원본")
                entry["product_name"] = ko
            elif field == "용량":
                if norm(en) != norm(src["size"]):
                    mismatch.append(f"{pid} 용량 EN≠원본")
                entry["size"] = ko or None
            elif field == "옵션":
                en_l, ko_l = bullets(en), bullets(ko)
                if en_l != [v["label"] for v in src["variants"]] or len(en_l) != len(ko_l):
                    mismatch.append(f"{pid} 옵션 EN≠원본")
                entry["variant_labels"] = dict(zip(en_l, ko_l))
            elif field == "카테고리":
                if norm(en) != norm(" > ".join(src["category"])):
                    mismatch.append(f"{pid} 카테고리 EN≠원본")
            elif field in ("하이라이트", "피부 고민", "적합 피부", "배지"):
                key = {
                    "하이라이트": "highlights",
                    "피부 고민": "skincare_concerns",
                    "적합 피부": "suitable_skin_types",
                    "배지": "badges",
                }[field]
                if field == "배지":  # 배지만 쉼표로 이어 적었다
                    en_l = [x.strip() for x in en.split(",") if x.strip()]
                else:
                    en_l = bullets(en) if "<br>" in en or en.startswith("· ") else ([en] if en else [])
                if en_l != list(src.get(key) or []):
                    mismatch.append(f"{pid} {field} EN≠원본")
                # 라벨은 labels-ko 에서 나간다. 표의 KO 가 열거값 대조표와 어긋나면 알린다
                for e, k in zip(en_l, bullets(ko) if "<br>" in ko or ko.startswith("· ") else ([ko] if ko else [])):
                    if labels[key].get(e) not in (None, k):
                        stats[f"label-diverge:{key}"] += 1
            elif field == "가격":
                if en != f"${src['price_usd']:g}":
                    mismatch.append(f"{pid} 가격 EN≠원본 ({en})")
            continue

        # ---- 상품 설명
        if section == "상품 설명":
            key = DESC_FIELDS.get(field)
            if key is None:
                raise SystemExit(f"{pid}: 설명 항목을 모른다 — {field}")
            desc_src = src["description"] or {}
            if entry["description"] is None:
                entry["description"] = {k: None for k in DESC_FIELDS.values()}
                entry["description"]["highlighted_ingredients"] = []
            if key == "highlighted_ingredients":
                en_l = bullets(en)
                if [norm(x) for x in en_l] != [norm(x) for x in desc_src.get(key) or []]:
                    mismatch.append(f"{pid} 주요 성분 EN≠원본")
                entry["description"][key] = bullets(ko)
            else:
                if norm(md_to_text(en)) != norm(desc_src.get(key)):
                    mismatch.append(f"{pid} {field} EN≠원본")
                entry["description"][key] = md_to_text(ko)
            if ko:
                stats["desc"] += 1
            continue

        # ---- 전성분: 원본은 보통 통짜 문자열 1개, 9개 상품은 여러 원소
        if section == "전성분":
            src_l = src["ingredients"]
            joined_candidates = {norm(", ".join(src_l)), norm("\n".join(src_l)), norm(" ".join(src_l))}
            if norm(md_to_text(en)) not in joined_candidates:
                mismatch.append(f"{pid} 전성분 EN≠원본")
            entry["ingredients"] = [md_to_text(ko)] if ko else []
            stats["ingredients"] += bool(ko)
            continue

        raise SystemExit(f"{fname} {pid}: 절을 모른다 — {section}")

    # ---- 검증
    missing = sorted(set(products) - set(out_products))
    if missing:
        mismatch.append(f"검수본에 없는 상품 {len(missing)}개: {missing[:5]}")
    if len(out_reviews) != sum(len(v) for v in reviews_by_pid.values()):
        mismatch.append(f"리뷰 {len(out_reviews)} / 원본 {sum(len(v) for v in reviews_by_pid.values())}")
    no_name = [p for p, e in out_products.items() if not e["product_name"]]
    if no_name:
        mismatch.append(f"상품명 KO 비어 있음 {len(no_name)}개: {no_name[:5]}")

    # 열거값 대조표가 원본의 모든 키를 덮는지
    for key in ("highlights", "skincare_concerns", "suitable_skin_types", "badges"):
        used = {v for p in products.values() for v in (p.get(key) or [])}
        gap = sorted(used - set(labels[key]))
        if gap:
            mismatch.append(f"labels.{key} 누락 {len(gap)}: {gap[:5]}")
    used_cat = {v for p in products.values() for v in p["category"]}
    gap = sorted(used_cat - set(labels["category"]))
    if gap:
        mismatch.append(f"labels.category 누락 {gap}")

    if mismatch:
        print("대조 실패 — 검수본 EN 열이 원본과 다르거나 라벨이 빠졌다:")
        for m in mismatch[:40]:
            print("  ", m)
        print(f"  … 총 {len(mismatch)}건")
        raise SystemExit(1)

    os.makedirs(OUT_DIR, exist_ok=True)
    meta = {
        "source": "docs/localization/HWABUN_한국어화_검수본_20260909",
        "built_by": "batch/ingest/build_ko_catalog.py",
        "usd_krw": USD_KRW,
        "krw_rounding": 100,
        "note": "내부 키(category·highlights·skin type·badge·variant label)는 영문 그대로 두고 화면 라벨만 바꾼다. 브랜드명 영문 유지.",
    }
    dump(os.path.join(OUT_DIR, "labels-ko.json"), {"_meta": meta, **labels})
    dump(os.path.join(OUT_DIR, "products-ko.json"), {"_meta": meta, **out_products})
    dump(os.path.join(OUT_DIR, "reviews-ko.json"), {"_meta": meta, **out_reviews})

    print(f"상품 {len(out_products)}개 · 리뷰 {len(out_reviews)}건 → contracts/localization/")
    print(f"  설명 셀 {stats['desc']} · 전성분 {stats['ingredients']} · 라벨 그룹 {len(labels)}개 "
          f"({sum(len(v) for v in labels.values())}항목)")
    for k, v in sorted(stats.items()):
        if k.startswith("label-diverge"):
            print(f"  주의: 상품표 KO 와 열거값 대조표가 다른 셀 {v} ({k.split(':')[1]}) — labels-ko 가 기준")


if __name__ == "__main__":
    main()
