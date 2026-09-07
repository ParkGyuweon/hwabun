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

# 어휘집에 **없는** 브랜드를 위한 폴백 (어휘집 0.5, 2026-09-03).
#
# brand 는 55개 고정 원핫이라 목록에 없는 브랜드는 그 55차원이 전부 0 이 된다.
# 브랜드가 등록될 때마다 차원을 늘리고 기존 상품 200개를 다시 인코딩하는 것은
# 서비스 운영 중에 할 수 없다. 그래서 **어휘집 밖 브랜드에만** 점수 항을 더한다.
#
#   score += BRAND_W   이 상품 브랜드가 사용자의 시드 브랜드에 있고, 어휘집에 없을 때
#
# 목록에 있는 브랜드는 지금처럼 원핫으로 계산한다. 그래서 **기존 카탈로그의 벡터와
# 점수가 한 자리도 바뀌지 않는다** — 대표 지표가 흔들리지 않는다.
#
# 가중치는 원핫 블록과 같은 0.60 이다. 관계 항으로 **전면 교체**하는 안도 재봤다.
# valid 에서는 구분되지 않았지만(24.20% vs 24.30%) test 에서 -0.81%p 였다.
# 신규 브랜드 지원만 필요하다면 폴백으로 충분하고 기존 수치를 지킬 수 있다.
# 재현: Research/eval/eval_brand_relation_feature_20260903.py
BRAND_W = 0.60

# ── CF 가점 (2026-09-07, Jira 174) ────────────────────────────────────────
#
# **가점 전용이다.** 두 점수를 minmax 로 정규화해 섞으면 CF 이력이 없는 상품이
# 0점(최하위)을 받아 **신규 등록 상품을 밑바닥으로 민다** — 정답이 신규 상품일 때
# 24.15% -> 1.55% 로 사실상 사라진다. 가점 전용은 CBF 를 안 건드려 18.20% 로
# 살아 있다. 입점 플랫폼에서 이 차이는 기능의 유무다.
#
#     score += CF_BETA x (cf / cf 최대)      이력이 없으면 **중앙값**을 준다
#
# 이력 없는 상품에 0 을 주면 "아무도 안 샀다" 가 아니라 "모른다" 를 나쁜 것으로
# 취급하게 된다. 중앙값을 주면 순위를 흔들지 않고 비켜선다 (15.90 -> 18.20%).
#
# 지지자(그 상품을 긍정 평가한 사람 중 다른 상품도 산 사람)가 CF_MIN_SUPPORT
# 미만이면 가점을 막는다. 0명 구간에서 CF 를 얹으면 -0.46%p 손해다 — 데이터가
# 거의 없을 때의 CF 값은 노이즈이고 가점 전용이어도 순위를 흔든다.
#
# 근거: docs/ai/evaluation-framework.md 부록 N·O·P.
CF_BETA = 1.0
CF_MIN_SUPPORT = 3


def load_cooc(path=None):
    """동시발생 산출물을 읽는다. 없으면 (None, None) — 항이 꺼진다.

    평가 스크립트가 `--cf` 로 이것을 켜고 끈다. 파일이 없을 때 죽지 않는 이유는
    `build_cooc.py` 가 리뷰 원본을 필요로 해서 없는 환경이 있기 때문이다.
    """
    import os as _os
    path = path or _os.path.join(
        _os.path.dirname(_os.path.abspath(__file__)),
        "..", "ingest", "data", "serving", "item_cooc.npz")
    if not _os.path.exists(path):
        return None, None
    d = np.load(path, allow_pickle=True)
    return np.asarray(d["S"], np.float32), np.asarray(d["supporters"])


def cf_bonus(cooc, rows, cand=None, supporters=None,
             min_support=CF_MIN_SUPPORT):
    """동시발생에서 CF 가점 항을 만든다. 이력이 없는 상품에는 중앙값을 준다.

    cooc:       (상품수, 상품수) 아이템-아이템 유사도. None 이면 항이 꺼진다
    rows:       사용자가 전환한 상품의 행 번호
    cand:       후보 마스크. 정규화를 **후보 안에서** 한다 (밖까지 넣으면 흔들린다)
    supporters: 상품별 지지자 수. 주면 임계 미만 상품의 가점을 막는다
    """
    if cooc is None or not rows:
        return None
    cf = np.asarray(cooc)[list(rows)].sum(axis=0)
    if supporters is not None:
        cf = np.where(np.asarray(supporters) >= min_support, cf, 0.0)
    m = np.ones(len(cf), bool) if cand is None else np.asarray(cand, bool)
    if not m.any():
        return None
    hi = float(cf[m].max())
    if hi <= 0:
        return None
    v = cf / hi
    # 중앙값은 **이력이 있는 상품끼리** 잰다. 후보 전체에서 재면 이력 없는 상품이
    # 많을 때 중앙값이 0 이 되어 중립 가점이 무력화된다 — 신규 브랜드가 대부분인
    # 플랫폼 초기가 정확히 그 상태다. 필요한 순간에 안 듣는 것을 막는다.
    seen = v[m & (v > 0)]
    med = float(np.median(seen)) if seen.size else 0.0
    return np.where(v > 0, v, med)


def brand_match(brands, rows, known=None):
    """rows 의 브랜드 집합에 속하면 1, 아니면 0 인 (상품수,) 배열.

    known 을 주면 **그 목록에 없는 브랜드에만** 1 을 준다 (어휘집 밖 폴백).
    문자열만 비교하므로 처음 보는 브랜드도 그대로 동작한다 — 그게 존재 이유다.
    """
    seen = {brands[i] for i in rows}
    if known is not None:
        seen = {b for b in seen if b not in known}
    if not seen:
        return None
    return np.fromiter((1.0 if b in seen else 0.0 for b in brands),
                       np.float32, len(brands))
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
#
# ⚠ 위 표는 **CBF 단독** 기준이다 (2026-09-03). CF 채택 후 다시 스윕하지 않았다 —
# 근거를 정확도가 아니라 다양성에 두었고, CF 는 브랜드 쏠림을 오히려 풀어 주므로
# (최다 브랜드 5.92 -> 4.43칸, 부록 S) 0.8 을 바꿀 이유가 생기지 않았다.
# **재스윕한다면 홀드아웃에서 한다. test 는 소진됐다** (부록 Q).
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
#   이 스케줄          23.39%  (롱테일 31.29%)   시드 6개 이상 구간 25.00%   <- CBF 단독
#   이전 스케줄        22.43%  (롱테일 30.91%)   시드 6개 이상 구간 17.46%
#   속성 항 제거       22.58%  (롱테일 30.91%)   -0.81%p CI [-1.52, -0.02]
# 2026-09-03 재측정. 계약 §7.1.1(is_recommended) · §7.1.2(tie-break) 를 정본이
# 받으면서 162명의 target 이 바뀌었다 (eval_metadata.py 머리말). 결론은 그대로다.
# 속성 항은 정확도를 올리는 장치가 아니라 **롱테일 보험**이라 남긴다.
#
# ⚠ 위 세 줄은 **CBF 단독** 값이다. 이 스케줄은 그대로 쓰지만 **현재 성능이
# 아니다** — CF 가점 채택 후 대표 지표는 Recall@10 38.86% (롱테일 40.61%) 다
# (docs/ai/evaluation-framework.md 부록 S). 스케줄 자체는 CF 를 얹어도 판단이
# 바뀌지 않아 다시 고르지 않았다: CF 는 가점 전용이라 w1/w2/w3 의 상대 비중을
# 건드리지 않는다.
# 측정: docs/ai/persona-feature-port.md §7 · batch/jobs/eval_persona_feature.py
SCHEDULE = [(0, 0.00, 0.30, 0.70),
            (5, 0.70, 0.25, 0.05),
            (10 ** 9, 0.80, 0.18, 0.02)]


def schedule_for(n_seed):
    for hi, w1, w2, w3 in SCHEDULE:
        if n_seed <= hi:
            return w1, w2, w3
    return SCHEDULE[-1][1:]


def prior_in_catalog(prior, rows):
    """인기도를 **그 사이트 카탈로그 안에서** 다시 0~1 로 편다 (2026-09-03).

    prior 는 카탈로그 200개 전체에서 잰 값이다. 사이트가 자기 상품 20개만 판다면
    그 20개가 전역 순위에서 아래쪽에 몰려 있을 수 있고, 그러면 인기도 항이 전
    후보에 비슷한 값을 줘서 **아무것도 구분하지 못한다.** 신규 브랜드일수록 심하다.
    사이트 안에서 다시 펴면 그 안의 상대 인기도가 된다.

    minmax 는 아핀 변환이라 이미 정규화된 값에 다시 걸어도 원본 log1p 에 건 것과
    같다. 상품이 하나뿐이면 펼 수 없으므로 0 을 준다 — 후보가 하나면 인기도 항이
    순위에 영향을 주지 않는 것이 맞다.
    """
    out = np.zeros_like(np.asarray(prior, float))
    if len(rows) == 0:
        return out
    sub = np.asarray(prior, float)[rows]
    lo, hi = float(sub.min()), float(sub.max())
    out[rows] = (sub - lo) / (hi - lo) if hi > lo else 0.0
    return out


class Recommender:
    def __init__(self, matrix, index, prior, affinity=None, lam=LAMBDA,
                 catalog=None, brands=None, known_brands=None,
                 cooc=None, supporters=None, cf_beta=CF_BETA,
                 ltr=None, ltr_feat=None):
        """matrix (상품수, 차원) · index product_id->행 · prior 인기도 0~1
           affinity: 페르소나 속성 친화도를 내주는 함수 f(persona) -> (상품수,) 배열
           catalog: 이 사이트가 파는 상품(id 또는 행 번호). 주면 후보를 그것으로
                    제한하고 **인기도를 그 안에서 다시 편다**
           brands: 행 번호 -> brand_name. 주면 brand 관계 항이 켜진다"""
        self.brands = list(brands) if brands is not None else None
        # 어휘집에 있는 브랜드. 여기 있는 것은 원핫이 처리하므로 폴백을 안 건다
        self.known_brands = set(known_brands) if known_brands is not None else set()
        self.M = matrix
        self.idx = index
        self.ids = [None] * len(index)
        for g, i in index.items():
            self.ids[i] = g
        self.catalog = None if catalog is None else sorted(
            {index[g] if isinstance(g, str) else int(g) for g in catalog})
        self.prior = (prior if self.catalog is None
                      else prior_in_catalog(prior, self.catalog))
        self.affinity = affinity
        self.lam = lam
        # CF 를 안 주면 항이 통째로 꺼져 **기존과 한 자리도 다르지 않다.**
        self.cooc = cooc
        self.supporters = supporters
        self.cf_beta = cf_beta
        # 학습 결합 (2026-09-07 채택). 주면 **선형 합을 통째로 대체**한다 —
        # 가중치 스케줄도 CF 가점도 타지 않는다. 그 값들은 모델의 피처로 들어간다.
        # 안 주면 항이 통째로 꺼져 이전과 한 자리도 다르지 않다.
        self.ltr = ltr
        self.ltr_feat = ltr_feat

    def score(self, state, persona=None, n_seed=None):
        """state: user_vector.UserVector"""
        if self.ltr is not None and self.ltr_feat is not None:
            return self._score_ltr(state, persona)
        vp, vn = state.vectors(self.idx, self.M)
        pos, _ = state.weights()
        w1, w2, w3 = schedule_for(len(pos) if n_seed is None else n_seed)

        s = np.full(len(self.M), 0.0)
        if vp is not None:
            s += w1 * (self.M @ vp)
        if self.brands is not None:
            # 전환한 상품의 브랜드를 그 사람이 "쓰던 브랜드" 로 본다
            rows = [self.idx[g] for g in state.converted if g in self.idx]
            bm = brand_match(self.brands, rows, self.known_brands) if rows else None
            if bm is not None:
                s += BRAND_W * bm
        if vn is not None:
            s -= self.lam * (self.M @ vn)
        if self.affinity is not None and persona is not None:
            s += w2 * self.affinity(persona)
        s += w3 * self.prior
        if self.cooc is not None:
            rows = [self.idx[g] for g in state.converted if g in self.idx]
            cand = None
            if self.catalog is not None:
                cand = np.zeros(len(self.M), bool)
                cand[self.catalog] = True
            bonus = cf_bonus(self.cooc, rows, cand, self.supporters)
            if bonus is not None:
                s = s + self.cf_beta * bonus
        return s

    def _score_ltr(self, state, persona):
        """학습 결합. 선형 합 대신 모델이 점수를 낸다 (계약 §5 처리 4단계)

        **피처를 후보 안에서 만들어야 한다.** `cf` 와 `cf_rank` 가 후보 집합에
        의존하므로, 사이트가 자기 상품만 판다면 그 안에서 다시 매겨야 한다.
        후보 밖까지 넣어 등수를 매기면 에러 없이 순위만 틀린다.
        """
        # 시드는 **긍정 가중이 붙은 상품 전부**다 (전환 + 정독한 미전환, 규칙 5-1).
        #
        # ⚠ 전환한 상품만 쓰면 안 된다. 그러면 점수가 전환과 전환 사이에 한 발짝도
        #   안 움직여서 **"행동이 쌓일수록 좋아진다" 가 깨진다** — 동적 축에서
        #   시작 실패자 구제율이 4.5% -> 0.4% 로 주저앉는 것을 확인했다.
        #   긍정 집합을 쓰면 9.7% 로 오히려 선형을 넘는다 (부록 T).
        pos, _ = state.weights()
        rows = [self.idx[g] for g in pos if g in self.idx]
        if not rows:
            rows = [self.idx[g] for g in state.converted if g in self.idx]
        cand = np.ones(len(self.M), bool)
        if self.catalog is not None:
            cand[:] = False
            cand[self.catalog] = True
        if not rows:
            # 시드가 없으면 모델이 볼 것이 없다. 인기도만 남긴다 (스케줄 0개 구간)
            return np.asarray(self.prior, float) * 0.70
        X = self.ltr_feat.make(persona, rows, cand)
        return self.ltr.predict_proba(X)[:, 1]

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
        if self.catalog is not None:        # 이 사이트가 파는 상품만 후보다
            keep = np.zeros(len(s), bool)
            keep[self.catalog] = True
            s[~keep] = -np.inf
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
