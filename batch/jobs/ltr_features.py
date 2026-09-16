# -*- coding: utf-8 -*-
"""(사용자, 후보 상품) 쌍의 피처 19개 — 학습과 서빙이 **같은 코드**를 쓴다 (Jira 192).

왜 한 파일인가
    학습 쪽과 서빙 쪽이 피처를 따로 구현하면 **에러가 안 나고 순위만 조금씩
    틀린다.** 블록 경계를 한 칸 잘못 자르거나 `cf_rank` 를 후보 밖까지 넣어
    매겨도 아무 신호가 없다. 그래서 여기 하나만 두고 양쪽이 이것을 부른다.

피처
     0 cos_all      전체 코사인 (시드 평균 벡터 대비)
     1 affinity     속성 친화도
     2 prior        인기도 (log 정규화)
     3 cf           CF 점수 — **후보 안에서** 정규화
     4 supporters   그 상품 지지자 수 log1p/10
     5 same_brand   시드 브랜드와 같은가
     6 price_prox   시드 가격 중앙값과 가까운가 (log2 거리)
     7 n_seed       시드 개수 /10
     8 pop_rank     인기 순위 0~1
     9 cf_rank      **후보 안에서** CF 를 정렬한 등수 0~1
    10~18 블록별 코사인 9개 (ORDER 순서 그대로)

    9번이 가장 중요한 피처다 (순열 중요도 0.332 · 2위의 3.7배). 사람마다 CF
    점수 분포가 달라 원값은 서로 비교가 안 되고, 순위는 같은 척도가 된다.

⚠ `cf` 와 `cf_rank` 는 **후보 집합에 의존한다.** 사이트가 자기 상품만 판다면
   그 안에서 다시 매겨야 한다. `make(..., cand=)` 로 후보를 넘긴다.
"""
import json
import os

import numpy as np

from product_encoder import ORDER, brand_key

SERVING = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "ingest", "data", "serving")


def load_ltr(path=None):
    """학습 결합 모델을 읽는다. 없으면 None — 선형으로 돈다.

    조용히 None 을 돌려주지 않는다. 부르는 쪽이 경고를 찍어야 한다 —
    조용히 꺼지면 "LTR 로 잰 수치" 가 사실은 선형 값이 된다.
    """
    base = path or os.environ.get("LTR_MODEL_DIR") or SERVING     # 실험 모델은 LTR_MODEL_DIR (Jira 322)
    model = os.path.join(base, "ltr_model.pkl")
    meta = os.path.join(base, "ltr_model_meta.json")
    if not (os.path.exists(model) and os.path.exists(meta)):
        return None
    import joblib
    return joblib.load(model), json.load(open(meta, encoding="utf-8"))

NAMES = (["cos_all", "affinity", "prior", "cf", "supporters",
          "same_brand", "price_prox", "n_seed", "pop_rank", "cf_rank"]
         + [f"cos_{nm}" for nm in ORDER])

# 증강이 지우는 열 — "오늘 등록된 상품" 모양
I_CF, I_SUP, I_CF_RANK = 3, 4, 9
I_COS_BRAND = NAMES.index("cos_brand")

# ── 가중 평균 코사인 (Jira 322 실험) ──────────────────────────────────────
# cos_all 은 시드의 **단순 평균**이라 이벤트 가중치(3.0/8.0)가 순위에 닿지 않는다 (09-16 실측).
# 가중 평균 벡터와의 코사인을 피처 하나로 더 싣는다. 학습 데이터(리뷰 이력)에는 이벤트가 없어
# 평점을 강도로 삼는다 — 5점 = purchase, 4점 = add_to_cart, 그 아래 = product_view (log.ts 가중치).
WEIGHTED_NAME = "cos_seed_w"
RATING_EVENT = {5: "purchase", 4: "add_to_cart"}
_RATING_W = None


def rating_weights(persona, seed_ids):
    """시드 상품별 가중치 — 그 사람이 그 상품에 남긴 최고 평점을 이벤트 가중치로. 리뷰가 없으면 add_to_cart."""
    global _RATING_W
    if _RATING_W is None:
        import behavior_weights as BW
        ev = BW.load()["event"]
        _RATING_W = {r: float(ev.get(n, 1.0)) for r, n in RATING_EVENT.items()}
        _RATING_W["default"] = float(ev.get("add_to_cart", 3.0))
        _RATING_W["low"] = float(ev.get("product_view", 1.0))
    best = {}
    for r in (persona or {}).get("reviews") or ():
        g = r.get("group_id")
        if g in seed_ids:
            best[g] = max(best.get(g, 0), int(r.get("rating") or 0))
    out = []
    for g in seed_ids:
        rt = best.get(g)
        out.append(_RATING_W["default"] if rt is None else _RATING_W.get(rt, _RATING_W["low"]))
    return out


def weighted_from_meta(meta) -> bool:
    return bool(meta) and WEIGHTED_NAME in (meta.get("feature_names") or ())


def block_matrices(enc, V):
    """148차원을 블록 경계로 자르고 블록마다 L2 정규화한다"""
    out, off = {}, 0
    for nm in ORDER:
        w = 1 if nm == "rating" else len(enc.blk[nm]["vocab"])
        b = np.asarray(V[:, off:off + w], np.float32).copy()
        n = np.linalg.norm(b, axis=1, keepdims=True)
        n[n == 0] = 1.0
        out[nm] = b / n
        off += w
    if off != V.shape[1]:
        raise ValueError(f"블록 폭 합 {off} != 벡터 차원 {V.shape[1]}")
    return out


def pop_rank_of(products, n_ref=None):
    """리뷰 수 순위를 0~1 로. 상수라 한 번만 만든다.

    n_ref: 분모. 기본은 상품 수. **서빙에서 등록 상품이 붙어 카탈로그가 늘어도**
    학습 때의 분모(원천 200)를 그대로 쓰면 기존 상품의 피처가 한 자리도 안 바뀐다 —
    r/200 이 r/208 로 바뀌는 것만으로 트리 모델이 순위를 뒤집었다 (Jira 216 실측:
    P454018 0.257 → 0.142). 등록 상품은 리뷰 0 이라 맨 뒤에 서고 1.0 에서 잘린다"""
    n = len(products)
    d = float(n_ref or n)
    order = sorted(range(n), key=lambda i: -products[i]["_review_stats"]["review_count"])
    out = np.zeros(n, np.float32)
    for r, i in enumerate(order):
        out[i] = min(r / d, 1.0)
    return out


class LtrFeatures:
    def __init__(self, enc, V, prior, affinity, cooc, supporters, n_ref=None, weighted=False):
        """n_ref: 순위 피처(pop_rank·cf_rank)의 분모. 학습 때는 상품 수와 같다.
        서빙에서 등록 상품을 붙일 때 원천 카탈로그 크기를 넘기면 기존 상품 피처가 보존된다"""
        self.V = np.asarray(V, np.float32)
        self.prior = np.asarray(prior, np.float32)
        self.affinity = affinity
        self.N = len(self.V)
        self.n_ref = float(n_ref or self.N)
        self.cooc = None if cooc is None else np.asarray(cooc, np.float32)
        self.supporters = (np.zeros(self.N, np.float32) if supporters is None
                           else np.asarray(supporters, np.float32))
        P = enc.products
        self.brand_of = np.array([brand_key(p) for p in P])          # same_brand 도 brand_id 로 (Jira 247)
        self.price = np.array([float(p.get("price_usd") or 0) for p in P], np.float32)
        self.pop_rank = pop_rank_of(P, self.n_ref)
        self.BM = block_matrices(enc, self.V)
        self.weighted = bool(weighted)
        self.names = list(NAMES) + ([WEIGHTED_NAME] if self.weighted else [])

    def make(self, persona, seed_rows, cand=None, seed_weights=None):
        """seed_rows: 시드 상품의 행 번호. cand: 후보 불리언 마스크 (없으면 전체).
        seed_weights: 시드별 강도(이벤트 가중치). weighted 모델일 때만 쓰고, 없으면 cos_all 과 같다"""
        V, N = self.V, self.N
        si = list(seed_rows)
        mask = np.ones(N, bool) if cand is None else np.asarray(cand, bool)

        u = V[si].mean(0)
        nrm = np.linalg.norm(u)
        cos = V @ (u / nrm) if nrm > 1e-9 else np.zeros(N, np.float32)
        cos_w = cos
        if self.weighted and seed_weights is not None and len(seed_weights) == len(si):
            w = np.asarray(seed_weights, np.float32)
            if w.sum() > 0 and np.ptp(w) > 0:               # 전부 같으면 단순 평균과 같다
                uw = (V[si] * (w / w.sum())[:, None]).sum(0)
                nw = np.linalg.norm(uw)
                cos_w = V @ (uw / nw) if nw > 1e-9 else cos

        at = (self.affinity(persona) if (self.affinity is not None and persona is not None)
              else np.zeros(N, np.float32))

        if self.cooc is not None:
            raw = self.cooc[si].sum(axis=0)
            hi = float(raw[mask].max()) if mask.any() else 0.0
            cfn = raw / hi if hi > 0 else np.zeros(N, np.float32)
        else:
            cfn = np.zeros(N, np.float32)
        # 순위는 후보 안에서만 매긴다. 후보 밖 상품이 등수를 밀면 척도가 달라진다
        cfr = np.ones(N, np.float32)
        if mask.any():
            rows = np.flatnonzero(mask)
            r = np.argsort(np.argsort(-cfn[rows]))
            # 분모는 후보 수가 아니라 학습 카탈로그 크기(n_ref) 기준 — 후보가 전체일 때
            # 학습과 같고, 등록 상품이 붙어도 기존 상품의 값이 보존된다. 후보를 좁혔을 때는
            # 후보 수를 쓴다 (학습·평가에서 cand 를 쓰는 경로 유지)
            denom = self.n_ref if len(rows) >= self.n_ref else max(len(rows), 1)
            cfr[rows] = np.minimum(r / denom, 1.0)

        sb = np.isin(self.brand_of, [self.brand_of[i] for i in si]).astype(np.float32)
        ref = float(np.median([self.price[i] for i in si])) or 1.0
        prox = 1.0 - np.minimum(1.0, np.abs(np.log(np.maximum(self.price, 0.01) / ref))
                                / np.log(2))

        cols = [cos, at, self.prior, cfn, np.log1p(self.supporters) / 10.0,
                sb, prox, np.full(N, len(si) / 10.0, np.float32), self.pop_rank, cfr]
        for nm in ORDER:
            b = self.BM[nm][si].mean(0)
            n = np.linalg.norm(b)
            cols.append(self.BM[nm] @ (b / n) if n > 1e-9 else np.zeros(N, np.float32))
        if self.weighted:
            cols.append(np.asarray(cos_w, np.float32))
        return np.column_stack(cols).astype(np.float32)


def augment_new_product(X, y, frac=0.25, seed=17):
    """학습 행의 일부를 "오늘 등록된 상품" 모양으로 만들어 덧붙인다.

    문제는 train 카탈로그에 `cf = 0` 인 상품이 **하나도 없다**는 것이다. 모델이
    "이력 없음" 을 본 적이 없으니 그런 상품이 오면 분포 밖이라 일괄 바닥을 준다.
    증강 없이 학습한 모델은 신규 브랜드 상품 정답을 **한 명도 못 맞혔다(0.00%)**.

    이것을 넣으면 신규 브랜드가 살아날 뿐 아니라 **전체 정확도도 같이 오른다**
    (39.84 -> 41.71%). 43.9% 만 보고 채택했으면 신규 브랜드가 영영 안 뜨는
    서비스가 됐다.
    """
    rng = np.random.default_rng(seed)
    sel = rng.random(len(X)) < frac
    Xa = X[sel].copy()
    Xa[:, I_CF] = 0.0
    Xa[:, I_SUP] = 0.0
    Xa[:, I_CF_RANK] = 1.0          # 0~1 중 꼴찌
    Xa[:, I_COS_BRAND] = 0.0
    return np.vstack([X, Xa]), np.concatenate([y, y[sel]]), int(sel.sum())
