# -*- coding: utf-8 -*-
"""아이템-아이템 동시발생 — CF 가점의 입력 (Jira 174).

무엇을
    "이 상품을 좋게 본 사람이 저것도 좋게 봤다" 를 200x200 유사도로 만든다.
    `recommender.Recommender(cooc=...)` 가 이것을 받아 가점 항을 만든다.

        S[i][j] = 동시발생(i, j) / sqrt(n_i x n_j)

    잠재 요인이 아니라 **아이템-아이템**이라 "이 상품을 산 사람이 저것도 샀다"
    로 설명이 된다. 그래서 `breakdown` 에 항을 하나 더할 수 있다.

⚠️ 누출 차단이 이 파일의 존재 이유다
    CF 는 "이 상품을 산 사람이 다음에 뭘 샀나" 를 쓴다. **평가 대상이 그 통계에
    들어가면 정답을 보고 정답을 맞히는 것**이 된다. 그래서 `simulator/personas/
    data/personas_*.json` 의 `author_id` 를 **전부** 뺀다 — 9,900명·에이전트
    100명뿐 아니라 홀드아웃까지 전부다.

    홀드아웃을 안 빼면 그 홀드아웃으로 잰 수치가 전부 거짓이 된다. 파일이 하나
    늘 때마다 여기를 고쳐야 하므로 **디렉터리를 훑어서** 뺀다.

임계점
    상품별 지지자 수(`supporters`)를 같이 낸다. 지지자가 3명 미만이면 CF 값이
    노이즈라 `recommender` 가 가점을 막는다 (부록 O — 0명 구간은 -0.46%p 손해).

출력
    batch/ingest/data/serving/item_cooc.npz
        S           (200, 200) float32
        product_ids (200,)      순서 = S 의 행/열
        supporters  (200,)      상품별 지지자 수
        n_reviewers ()          동시발생에 기여한 리뷰어 수
        excluded    ()          누출 차단으로 뺀 author_id 수

실행
    SEPHORA_DATASET=... python batch/jobs/build_cooc.py
"""
import argparse
import csv
import glob
import json
import os
import sys
from collections import defaultdict

import numpy as np

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
sys.path.insert(0, BD)

DATA = os.path.join(ROOT, "batch", "ingest", "data")
OUT = os.path.join(DATA, "serving", "item_cooc.npz")
PRODUCTS = os.path.join(DATA, "products_200.json")
PDIR = os.path.join(ROOT, "simulator", "personas", "data")
BASE = os.environ.get("SEPHORA_DATASET")

# 계약 §7.1.1 과 같은 긍정 정의를 쓴다. 여기만 다르면 평가와 학습이 다른
# "좋아함" 을 보게 된다.
POSITIVE, RECOMMEND_MIN = 4, 3


def excluded_authors():
    """페르소나로 쓴 사람 전부. 파일이 늘어도 자동으로 잡히게 훑는다"""
    out = set()
    files = sorted(glob.glob(os.path.join(PDIR, "personas_*.json")))
    for fp in files:
        for r in json.load(open(fp, encoding="utf-8")):
            a = r.get("author_id")
            if a:
                out.add(str(a))
    return out, [os.path.basename(f) for f in files]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=BASE,
                    help="세포라 리뷰 CSV 디렉터리 (SEPHORA_DATASET)")
    a = ap.parse_args()
    if not a.dataset or not os.path.isdir(a.dataset):
        raise SystemExit("리뷰 원본 경로가 필요합니다 — SEPHORA_DATASET 환경변수")

    P = json.load(open(PRODUCTS, encoding="utf-8"))
    index = {p["product_id"]: i for i, p in enumerate(P)}
    N = len(P)
    member = {}
    for p in P:
        member[p["product_id"]] = p["product_id"]
        for m in (p.get("_merged", {}) or {}).get("member_product_ids", []):
            member[m] = p["product_id"]

    exclude, files = excluded_authors()
    print(f"누출 차단 — {len(files)}개 파일에서 author_id {len(exclude):,}개 제외")
    for f in files:
        print(f"    {f}")

    by_user = defaultdict(set)
    n_rows = 0
    for path in sorted(glob.glob(os.path.join(a.dataset, "reviews_*.csv"))):
        with open(path, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                n_rows += 1
                g = member.get(r.get("product_id"))
                au = r.get("author_id")
                if g is None or not au or au in exclude:
                    continue
                try:
                    rating = float(r.get("rating") or 0)
                except ValueError:
                    continue
                rec = str(r.get("is_recommended") or "").strip() in (
                    "1", "1.0", "True", "true")
                if rating >= POSITIVE or (rec and rating >= RECOMMEND_MIN):
                    by_user[au].add(g)

    C = np.zeros((N, N), np.float64)
    cnt = np.zeros(N, np.float64)
    contrib = 0
    for v in by_user.values():
        idx = sorted(index[g] for g in v if g in index)
        for i in idx:
            cnt[i] += 1
        if len(idx) < 2:
            continue          # 상품이 하나뿐이면 동시발생에 기여하지 않는다
        contrib += 1
        for x in range(len(idx)):
            for y in range(x + 1, len(idx)):
                C[idx[x], idx[y]] += 1
                C[idx[y], idx[x]] += 1

    d = np.sqrt(np.outer(np.maximum(cnt, 1.0), np.maximum(cnt, 1.0)))
    S = (C / d).astype(np.float32)
    np.fill_diagonal(S, 0.0)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    np.savez_compressed(
        OUT,
        S=S,
        product_ids=np.array([p["product_id"] for p in P]),
        supporters=cnt.astype(np.int32),
        n_reviewers=np.int64(contrib),
        excluded=np.int64(len(exclude)),
    )
    thin = int((cnt < 3).sum())
    print(f"\n리뷰 {n_rows:,}행 · 긍정 리뷰어 {len(by_user):,}명 "
          f"(동시발생 기여 {contrib:,}명)")
    print(f"동시발생 {N}x{N} · 0 이 아닌 쌍 {int((C > 0).sum() // 2):,}개 · "
          f"상품당 지지자 중앙 {np.median(cnt):,.0f}명")
    print(f"지지자 3명 미만 상품 {thin}개 — 그 상품은 가점이 막힌다")
    print(f"저장: {os.path.relpath(OUT, ROOT)} "
          f"({os.path.getsize(OUT) / 1024:.0f}KB)")
    if thin == 0:
        print("\n⚠️ 지금 카탈로그에는 CF 이력이 없는 상품이 하나도 없다.")
        print("   콜드 스타트는 **여기서 관측되지 않는다** — 신규 등록 상품이")
        print("   들어와야 비로소 임계점이 일을 한다.")


if __name__ == "__main__":
    main()
