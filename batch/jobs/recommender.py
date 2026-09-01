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

# 시드(리뷰) 상품 개수 -> (w1 콘텐츠, w2 속성, w3 인기)
#
# **행동이 쌓일수록 속성의 몫을 콘텐츠로 넘긴다.** 이전 스케줄은 시드 6개 이상에
# w2=0.55 를 줘서 가장 많이 행동한 사람에게 속성 비중이 가장 컸다. 서술과 코드가
# 반대였고, 그 구간에서 Recall@10 16.9% (같은 조건에서 속성을 빼면 21.2%) 였다.
#
# **고친 것은 6개 이상 구간 하나뿐이다.** 1~5개 구간은 측정으로 뒷받침된 값이라
# 그대로 둔다. 그 구간까지 같이 손대면 1~2개 구간에서 26.24% -> 25.38% 로 손해를 본다.
#
# 9,900명 leave-last-out 재측정 (부트스트랩 300회, 짝비교):
#   이 스케줄          23.70%  (롱테일 31.50%)   시드 6개 이상 구간 22.51%
#   이전 스케줄        23.08%  (롱테일 31.32%)   시드 6개 이상 구간 17.64%
#   속성 항 제거       22.86%  (롱테일 29.48%)   -0.64%p CI [-1.01, -0.25]
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

    def rank(self, state, persona=None, k=10, evaluation=False,
             review_products=(), view_cap=VIEW_CAP):
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
                if len(out) >= k:
                    break
            order = out
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
    from user_vector import UserVector
    M, idx, prior, enc = load_catalog()
    rec = Recommender(M, idx, prior)
    ids = list(idx)

    st = UserVector()
    for g in ids[:2]:
        st.observe({"event_name": "add_to_cart", "product_id": g, "properties": {}})
    st.observe({"event_name": "page_view", "product_id": ids[5], "properties": {}})
    st.observe({"event_name": "rage_click", "product_id": ids[7], "properties": {}})

    print(f"카탈로그 {M.shape[0]}개 상품 / 벡터 {M.shape[1]}차원")
    print(st)
    w1, w2, w3 = schedule_for(len(st.weights()[0]))
    print(f"스케줄 w1={w1} w2={w2} w3={w3}  λ={rec.lam}")
    print()
    print("서빙 top-5")
    for g, s in rec.rank(st, k=5):
        mark = "  (조회함)" if g in st.viewed else ""
        print(f"   {s:+.4f}  {enc.products[idx[g]]['product_name'][:46]}{mark}")
    print()
    print("평가 모드 top-5 (본 상품 전부 제외)")
    for g, s in rec.rank(st, k=5, evaluation=True):
        print(f"   {s:+.4f}  {enc.products[idx[g]]['product_name'][:46]}")
    print()
    print(f"특정 상품의 현재 순위: {rec.rank_of(st, ids[100])}위")
