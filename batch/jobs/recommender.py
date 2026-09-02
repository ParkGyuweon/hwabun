"""
추천 점수 계산 — 사용자 벡터와 상품 카탈로그로 목록을 정렬한다.

    score(i) = w1·cos(v_u⁺, v_i) − λ·cos(v_u⁻, v_i) + w2·attr(i) + w3·prior(i)

    w1/w2/w3 는 시드 개수에 따른 스케줄을 따른다 (docs/ai/recommendation-design.md 7-2).
    λ 는 잠정값이다. 실제 로그가 쌓이면 재측정한다.

노출 정책 (프론트 합의)
    리뷰 쓴 상품      제외 — 이미 산 상품이라 자리만 낭비한다
    장바구니 담긴 상품 제외 — 중복 행동 유도만 된다
    단순 조회 상품    상한 2개까지 포함 — 재고려 리마인드는 유효한 추천이다
                     (상한을 0~6 으로 재봤을 때 2개에서 포화. 비용 −0.6%p)

⚠️ 오프라인 평가에서는 조회 상품까지 전부 제외한다. 시드가 결과에 섞이면
   자기 자신을 맞히는 셈이라 적중률이 부풀려진다(leakage).
"""
import os
import sys

import numpy as np

BD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BD)

LAMBDA = 0.15
VIEW_CAP = 2
# MMR 다양성 계수. **값이 클수록 약하게 건다** — 헷갈리기 쉬운 방향이다.
#
#     선택 = argmax [ λ_mmr x score(i) - (1-λ_mmr) x max cos(v_i, 이미 고른 것) ]
#                     └ 점수(관련성)          └ 중복 벌점(다양성)
#
# λ 가 점수 쪽에 붙어 있어서 1.0 이면 벌점 계수가 0 이 되어 **끈 것과 같고**,
# 내릴수록 중복 벌점이 세진다 (0.8 = 약하게 / 0.5 = 세게).
#
# **다양성과 정확도가 같이 오른다.** 상위 10개를 한 브랜드가 5~6칸 먹고 있어서
# 정답이 들어올 자리가 없었기 때문이다. 중복을 걷어내면 그 자리가 생긴다.
# 강하게 걸면(0.5) 그때부터는 손해다.
#
# **정확도가 아니라 다양성으로 고른다.** valid(1,975명)에서 λ 를 스윕하면 어느
# 값에서도 정확도 차이가 유의하지 않다 — 깎지도 올리지도 않는다:
#   λ    전체(valid)  고유 브랜드   한 브랜드 최대 점유   λ=1.0 대비
#   1.0  24.41%          3.7개          61.3%          기준 (끔)
#   0.9  24.51%          4.0개          60.3%          +0.10%p [-0.20, +0.41]
#   0.8  24.35%          4.2개          59.0%          -0.05%p [-0.53, +0.35]  <- 채택
#   0.7  24.00%          4.4개          57.0%          -0.41%p [-0.96, +0.20]
#   0.5  24.00%          5.9개          45.6%          -0.41%p [-1.39, +0.48]
# 정확도가 같으니 목록의 고유 브랜드를 3.7 -> 4.2 개로 늘리는 0.8 을 쓴다.
# (test 에서는 끄면 -0.91%p 로 유의하게 나왔다. 두 분할의 표본 변동이 효과만 하다는
#  뜻이라 근거는 다양성 쪽에 둔다)
# 측정: docs/ai/recommendation-design.md 8절
LAMBDA_MMR = 0.8

# 시드(리뷰) 상품 개수 -> (w1 콘텐츠, w2 속성, w3 인기)
#
# **행동이 쌓일수록 속성의 몫을 콘텐츠로 넘긴다.** 이전 스케줄은 시드 6개 이상에
# w2=0.55 를 줘서 가장 많이 행동한 사람에게 속성 비중이 가장 컸다. 서술과 코드가
# 반대였고, 그 구간에서 Recall@10 16.9% (같은 조건에서 속성을 빼면 21.2%) 였다.
#
# **고친 것은 6개 이상 구간 하나뿐이다.** 1~5개 구간은 측정으로 뒷받침된 값이라
# 그대로 둔다. 그 구간까지 같이 손대면 1~2개 구간에서 26.24% -> 25.38% 로 손해를 본다.
#
# leave-last-out **test 집합 1,971명** (부트스트랩 300회, 짝비교).
# 선택은 valid 에서 하고 test 는 한 번만 본다 (docs/ai/evaluation-framework.md 1절):
#   이 스케줄          23.44%  (롱테일 31.23%)   시드 6개 이상 구간 26.32%
#   이전 스케줄        22.53%  (롱테일 30.84%)   시드 6개 이상 구간 19.03%
#   속성 항 제거       22.58%  (롱테일 30.84%)   -0.86%p CI [-1.57, -0.05]
# 속성 항은 정확도를 올리는 장치가 아니라 **롱테일 보험**이라 남긴다.
# 측정: docs/ai/persona-feature-port.md §7 · batch/jobs/eval_persona_feature.py
SCHEDULE = [(0, 0.00, 0.30, 0.70),
            (5, 0.70, 0.25, 0.05),
            (10 ** 9, 0.80, 0.18, 0.02)]


def schedule_for(n_seed):
    for hi, w1, w2, w3 in SCHEDULE:
        if n_seed <= hi:
            return w1, w2, w3
    return SCHEDULE[-1][1:]


class Recommender:
    def __init__(self, matrix, index, prior, affinity=None, lam=LAMBDA):
        """matrix (상품수, 차원) · index product_id->행 · prior 인기도 0~1
           affinity: 페르소나 속성 친화도를 내주는 함수 f(persona) -> (상품수,) 배열"""
        self.M = matrix
        self.idx = index
        self.ids = [None] * len(index)
        for g, i in index.items():
            self.ids[i] = g
        self.prior = prior
        self.affinity = affinity
        self.lam = lam

    def score(self, state, persona=None, n_seed=None):
        """state: user_vector.UserVector"""
        vp, vn = state.vectors(self.idx, self.M)
        pos, _ = state.weights()
        w1, w2, w3 = schedule_for(len(pos) if n_seed is None else n_seed)

        s = np.full(len(self.M), 0.0)
        if vp is not None:
            s += w1 * (self.M @ vp)
        if vn is not None:
            s -= self.lam * (self.M @ vn)
        if self.affinity is not None and persona is not None:
            s += w2 * self.affinity(persona)
        s += w3 * self.prior
        return s

    def mmr(self, scores, order, k, lam):
        """다양성 보정 — 점수 1등만 줄세우지 않고 서로 덜 닮은 것을 섞는다.

            선택 = argmax [ lam x score(i) - (1-lam) x max cos(v_i, 이미 고른 것) ]

        **lam 이 클수록 약하게 건다.** lam 은 점수 쪽 계수라 1.0 이면 벌점이 0 이 되어
        원래 순서 그대로고, 내릴수록 중복에 대한 벌점이 세진다.

        점수 축과 유사도 축의 크기가 다르면 lam 의 의미가 흔들리므로,
        후보 점수를 0~1 로 편 뒤 섞는다.

        **정확도를 깎는 장치다.** 점수 1등을 밀어내기 때문이다. 켤지 말지는
        docs/ai/recommendation-design.md 8절의 측정으로 판단한다.
        """
        if lam >= 1.0 or len(order) <= 1:
            return order[:k]
        cand = list(order)
        s = scores[cand]
        lo, hi = float(s.min()), float(s.max())
        norm = (s - lo) / (hi - lo) if hi > lo else np.zeros_like(s)
        rel = dict(zip(cand, norm))

        picked = [cand[0]]
        rest = cand[1:]
        while rest and len(picked) < k:
            sim = self.M[rest] @ self.M[picked].T      # (남은 후보, 고른 것)
            penalty = sim.max(axis=1)
            gain = lam * np.array([rel[i] for i in rest]) - (1 - lam) * penalty
            best = int(np.argmax(gain))
            picked.append(rest.pop(best))
        return picked

    def rank(self, state, persona=None, k=10, evaluation=False,
             review_products=(), view_cap=VIEW_CAP, lam_mmr=LAMBDA_MMR):
        """추천 목록 상위 k개. evaluation=True 면 본 상품을 전부 뺀다(leakage 차단)"""
        s = self.score(state, persona).copy()
        blocked = set(review_products) | set(state.converted)
        if evaluation:
            blocked |= state.viewed
        for g in blocked:
            i = self.idx.get(g)
            if i is not None:
                s[i] = -np.inf

        order = [i for i in np.argsort(-s) if np.isfinite(s[i])]
        if not evaluation and view_cap is not None:
            out, used = [], 0
            for i in order:
                if self.ids[i] in state.viewed:
                    if used >= view_cap:
                        continue
                    used += 1
                out.append(i)
                if len(out) >= k * 3:      # MMR 이 고를 여지를 남긴다
                    break
            order = out
        order = self.mmr(s, order, k, lam_mmr)
        return [(self.ids[i], float(s[i])) for i in order[:k]]

    def rank_of(self, state, product_id, persona=None, **kw):
        """정답 상품이 지금 몇 위인지. 목록 갱신마다 기록해 순위 곡선을 만든다"""
        s = self.score(state, persona)
        blocked = set(kw.get("review_products", ())) | set(state.converted)
        if kw.get("evaluation"):
            blocked |= state.viewed
        blocked.discard(product_id)
        m = s.copy()
        for g in blocked:
            i = self.idx.get(g)
            if i is not None:
                m[i] = -np.inf
        t = self.idx[product_id]
        return int((m > m[t]).sum()) + 1


def load_catalog(products_path=None, vocab_path=None):
    """product_encoder 로 상품 행렬·인덱스·인기도를 만든다"""
    from product_encoder import Encoder
    e = Encoder(vocab_path=vocab_path, products_path=products_path)
    M = e.matrix()
    idx = {p["product_id"]: i for i, p in enumerate(e.products)}
    return M, idx, e.prior(), e


if __name__ == "__main__":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    from persona_feature import AffinityTable
    from user_vector import UserVector
    M, idx, prior, enc = load_catalog()
    # 속성 친화도를 꽂지 않으면 w2 항이 통째로 0 이 된다. 데모가 그 상태면
    # 읽는 사람이 "속성은 안 쓰는구나" 로 오해한다
    rec = Recommender(M, idx, prior, affinity=AffinityTable(idx))
    persona = {"skin_type": "dry", "skin_tone": "light",
               "hair_color": "brown", "eye_color": "brown"}
    ids = list(idx)

    st = UserVector()
    for g in ids[:2]:
        st.observe({"event_name": "add_to_cart", "product_id": g, "properties": {}})
    st.observe({"event_name": "page_view", "product_id": ids[5], "properties": {}})
    st.observe({"event_name": "rage_click", "product_id": ids[7], "properties": {}})

    print(f"카탈로그 {M.shape[0]}개 상품 / 벡터 {M.shape[1]}차원")
    print(st)
    print(f"페르소나 속성 {persona}")
    w1, w2, w3 = schedule_for(len(st.weights()[0]))
    print(f"스케줄 w1={w1} w2={w2} w3={w3}  λ={rec.lam}")
    print()
    print("서빙 top-5")
    for g, s in rec.rank(st, persona=persona, k=5):
        mark = "  (조회함)" if g in st.viewed else ""
        print(f"   {s:+.4f}  {enc.products[idx[g]]['product_name'][:46]}{mark}")
    print()
    print("평가 모드 top-5 (본 상품 전부 제외)")
    for g, s in rec.rank(st, persona=persona, k=5, evaluation=True):
        print(f"   {s:+.4f}  {enc.products[idx[g]]['product_name'][:46]}")
    print()
    print("속성 항을 빼면 (affinity 미주입) top-5")
    for g, s in Recommender(M, idx, prior).rank(st, k=5):
        print(f"   {s:+.4f}  {enc.products[idx[g]]['product_name'][:46]}")
    print()
    print(f"특정 상품의 현재 순위: {rec.rank_of(st, ids[100], persona=persona)}위")
