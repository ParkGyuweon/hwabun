# -*- coding: utf-8 -*-
"""점수 결합을 학습으로 바꾼다 — Learning to Rank 모델 학습 (Jira 192).

무엇을 하나
    (사용자, 후보 상품) 쌍마다 피처 19개를 뽑고 정답=1 / 나머지=0 으로 학습한다.
    후보 199개를 다 쓰면 무거우므로 **음성 표본추출**한다 (정답 1 + 무작위 N).

    학습은 **train 5,954명에서만** 한다. eval_metadata 의 train 분할이고,
    valid/test/holdout 은 한 명도 안 들어간다. 홀드아웃 확인은 별도 스크립트다.

왜 선형을 버렸나
    선형 합은 **조건부 규칙을 표현할 수 없다.** 부록 M 이 정확히 그 벽에 부딪혔다 —
    "브랜드 안에서만 보면 가격이 보인다" 를 찾아 놓고, `+ w_p x 가격근접` 으로
    더하니 브랜드와 무관하게 항상 더해져서 train 에서조차 CI 가 0 을 못 넘었다.
    트리는 "같은 브랜드인가" 로 먼저 가르고 그 안에서 가격을 본다.

⚠ 증강이 필수다
    증강 없이 학습한 모델은 **신규 브랜드 상품 정답을 한 명도 못 맞혔다(0.00%)**.
    학습 카탈로그에 CF 이력이 없는 상품이 하나도 없어 분포 밖이기 때문이다.
    `ltr_features.augment_new_product` 가 학습 행의 25% 를 그 모양으로 만든다.

산출물
    serving/ltr_model.pkl        joblib 로 저장한 모델
    serving/ltr_model_meta.json  피처 이름·학습 조건·순열 중요도

실행: python batch/jobs/train_ltr.py [--neg 30] [--no-importance]
"""
import argparse
import json
import os
import sys
import time

import numpy as np

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
sys.path.insert(0, BD)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from eval_metadata import load as load_metadata          # noqa: E402
from ltr_features import LtrFeatures, augment_new_product  # noqa: E402
from persona_feature import load as load_affinity        # noqa: E402
from product_encoder import Encoder                      # noqa: E402
from recommender import load_cooc                        # noqa: E402

DATA = os.path.join(ROOT, "batch", "ingest", "data")
SERVING = os.path.join(DATA, "serving")
PERSONAS = os.path.join(ROOT, "simulator", "personas", "data", "personas_9900.json")

NEG = 30
AUG_FRAC = 0.25
PARAMS = dict(max_iter=800, learning_rate=0.08, max_leaf_nodes=31,   # 300 → 800 (2026-09-10): 태그 제거 후 300 에 닿아 조기종료가 안 됐다. 800 이면 383 에서 멈춘다
              l2_regularization=1.0, early_stopping=True,
              validation_fraction=0.1, random_state=0)


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def training_rows(index):
    profiles = {p["persona_id"]: p
                for p in json.load(open(PERSONAS, encoding="utf-8"))}
    out = []
    for r in load_metadata(split="train"):
        p = profiles.get(r["persona_id"])
        if p is None:
            continue
        seeds = [index[g] for g in r["seed_product_ids"] if g in index]
        t = r["target_product_id"]
        if seeds and t in index:
            out.append((p, seeds, index[t]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--neg", type=int, default=NEG, help="사람당 음성 표본 수")
    ap.add_argument("--aug", type=float, default=AUG_FRAC,
                    help="신규 상품 모양으로 만들 학습 행 비율")
    ap.add_argument("--out", default=SERVING)
    ap.add_argument("--no-importance", dest="importance", action="store_false",
                    default=True, help="순열 중요도 계산을 건너뛴다 (빠름)")
    ap.add_argument("--max-iter", type=int, default=PARAMS["max_iter"],
                    help="트리 수 상한 (조기종료 기준). 2026-09-10 태그 제거 후 300 에 닿아 올려 본 값을 고른다")
    a = ap.parse_args()
    PARAMS["max_iter"] = a.max_iter

    from sklearn.ensemble import HistGradientBoostingClassifier
    import joblib

    enc = Encoder()
    V = np.asarray(enc.matrix(), np.float32)
    index = {p["product_id"]: i for i, p in enumerate(enc.products)}
    prior = np.asarray(enc.prior(), np.float32)
    affinity = load_affinity(index)

    cooc, supporters = load_cooc()
    if cooc is None:
        raise SystemExit(
            "item_cooc.npz 가 없습니다. CF 순위가 가장 중요한 피처(중요도 0.332)라\n"
            "  이것 없이 학습하면 모델이 통째로 다른 것이 됩니다.\n"
            "  `python batch/jobs/build_cooc.py` 를 먼저 도십시오.")

    F = LtrFeatures(enc, V, prior, affinity, cooc, supporters)
    rows = training_rows(index)
    log(f"train {len(rows):,}명 · 음성 {a.neg}개씩 -> 약 {len(rows)*(a.neg+1):,}행")

    rng = np.random.default_rng(7)
    N = len(V)
    X, y = [], []
    for persona, si, ti in rows:
        M = F.make(persona, si)
        pool = np.setdiff1d(np.arange(N), np.array(si + [ti]))
        neg = rng.choice(pool, size=min(a.neg, len(pool)), replace=False)
        X.append(M[[ti]]); y.append(1)
        X.append(M[neg]);  y.extend([0] * len(neg))
    X = np.vstack(X)
    y = np.array(y, np.int8)

    X, y, n_aug = augment_new_product(X, y, frac=a.aug)
    log(f"증강 후 {len(X):,}행 (신규 상품 모양 {n_aug:,}행 추가)")

    clf = HistGradientBoostingClassifier(**PARAMS)
    clf.fit(X, y)
    log(f"학습 끝 — 트리 {clf.n_iter_}개")

    importance = None
    if a.importance:
        from sklearn.inspection import permutation_importance
        sub = rng.choice(len(X), size=min(40000, len(X)), replace=False)
        log("순열 중요도 계산 중")
        r = permutation_importance(clf, X[sub], y[sub], n_repeats=3,
                                   random_state=0, scoring="average_precision")
        importance = {F.names[i]: round(float(r.importances_mean[i]), 4)
                      for i in np.argsort(-r.importances_mean)}

    os.makedirs(a.out, exist_ok=True)
    model_path = os.path.join(a.out, "ltr_model.pkl")
    joblib.dump(clf, model_path)
    meta = {
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "split": "train",
        "n_persona": len(rows),
        "n_rows": int(len(X)),
        "n_negative_per_persona": a.neg,
        "augment_fraction": a.aug,
        "n_augmented_rows": n_aug,
        "n_trees": int(clf.n_iter_),
        "params": PARAMS,
        "feature_names": F.names,
        "permutation_importance": importance,
        "sklearn_version": __import__("sklearn").__version__,
    }
    with open(os.path.join(a.out, "ltr_model_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    size = os.path.getsize(model_path) / 1024
    print(f"\nserving/ltr_model.pkl        {size:,.0f}KB · 트리 {clf.n_iter_}개")
    print(f"serving/ltr_model_meta.json  피처 {len(F.names)}개")
    if importance:
        print("\n| 피처 | 순열 중요도 |")
        print("|---|---:|")
        for k, v in list(importance.items())[:8]:
            print(f"| {k} | {v:.4f} |")


if __name__ == "__main__":
    main()
