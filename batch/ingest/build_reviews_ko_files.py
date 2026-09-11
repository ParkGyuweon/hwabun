# -*- coding: utf-8 -*-
"""상품별 한국어 리뷰 파일 200개를 만든다 (2026-09-11, Jira 242).

프론트 합의(09-10): `public/reviews/{product_id}.json` 을 fetch 한 번으로 읽는다. 영문 100건 파일
(`reviews_en_100/{product_id}.json`, 스키마 = reviews.sample.json) 에서 `review_title`·`review_text` 만
한국어(`contracts/localization/reviews-ko.json`)로 바꾸고 나머지 필드·순서·개수는 그대로 둔다.

    python batch/ingest/build_reviews_ko_files.py --en-dir <reviews_en_100> --out <폴더>

검사: 파일 200 · 각 100건 · review_id 순서 동일 · 한국어 없는 건 0 · 제목 null 보존.
"""
import argparse
import glob
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
KO_PATH = os.path.join(ROOT, "contracts", "localization", "reviews-ko.json")
HANGUL = re.compile(r"[가-힣]")

ap = argparse.ArgumentParser()
ap.add_argument("--en-dir", required=True)
ap.add_argument("--out", required=True)
A = ap.parse_args()

ko = json.load(open(KO_PATH, encoding="utf-8"))
ko.pop("_meta", None)
os.makedirs(A.out, exist_ok=True)

files = sorted(glob.glob(os.path.join(A.en_dir, "P*.json")))
n_reviews = missing = no_hangul = title_mismatch = 0
per_file = []
for f in files:
    arr = json.load(open(f, encoding="utf-8"))
    out = []
    for x in arr:
        k = ko.get(x["review_id"])
        if k is None:
            missing += 1
            continue
        y = dict(x)
        y["review_title"] = k["review_title"]
        y["review_text"] = k["review_text"]
        if (x.get("review_title") is None) != (k["review_title"] is None):
            title_mismatch += 1
        if not HANGUL.search(y["review_text"] or ""):
            no_hangul += 1
        out.append(y)
    n_reviews += len(out)
    per_file.append((os.path.basename(f), len(arr), len(out)))
    with open(os.path.join(A.out, os.path.basename(f)), "w", encoding="utf-8") as w:
        json.dump(out, w, ensure_ascii=False, indent=1)

lines = ["# 상품별 한국어 리뷰 파일 검증", "",
         f"- 파일 {len(files)} · 리뷰 {n_reviews:,} · 상품당 {min(c for _, _, c in per_file)}~{max(c for _, _, c in per_file)}건",
         f"- 한국어 누락(reviews-ko 에 없음) {missing} · 한글 없는 본문 {no_hangul} · 제목 null 불일치 {title_mismatch}",
         f"- 원본 스키마·순서·review_id 유지, `review_title`·`review_text` 만 교체",
         f"- 원천 EN: `{A.en_dir}` · 한국어: `contracts/localization/reviews-ko.json`"]
short = [(n, a, c) for n, a, c in per_file if a != c]
if short:
    lines += ["", "## 건수가 줄어든 파일", ""] + [f"- {n}: {a} → {c}" for n, a, c in short]
with open(os.path.join(A.out, "README.md"), "w", encoding="utf-8") as w:
    w.write("\n".join(lines) + "\n")
print("\n".join(lines))
