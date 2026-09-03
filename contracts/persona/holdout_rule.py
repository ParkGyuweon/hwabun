# -*- coding: utf-8 -*-
"""리뷰 한 사람분을 seed / holdout_target / excluded 로 가른다.

계약 원본은 `contracts/persona-schema.md` §7.1 이다. 이 파일은 그 판정 순서를
**그대로** 옮긴 것이고, 다른 곳에서 같은 판정을 다시 구현하지 않는다.

    정렬  submission_time DESC NULLS LAST -> review_id DESC
          -> 첫 리뷰가 holdout 후보다
    2     후보의 canonical_product_id 가 Product Feature 에 있는가
          없으면 excluded. holdout 테이블에 넣지 않는다
    3     rating >= 4 또는 is_recommended = true 인가
          맞으면 positive / eligible=true
          아니면 eligible=false 로 남긴다 (버리지 않는다)
    7     후보를 제외한 이전 리뷰가 seed 다

계약이 정하지 않아 여기서 정한 것 세 가지 — 문서에 근거를 남겼다.

    negative / diagnostic 경계
        §7.1-5 는 "negative 또는 diagnostic" 이라고만 쓰고 경계를 정하지 않는다.
        `contracts/recommendation-io-spec.md` "리뷰 극성의 처리" 가 별점 1~2 를
        부정, 3 을 중립으로 두므로 그것을 따른다.

    같은 상품의 이전 리뷰 (누출 방지)
        §7.1-7 을 글자대로 적용하면 **정답 상품이 seed 에도 남는다.** 같은 상품에
        리뷰를 두 번 이상 쓴 사람이 PC 9,900명 중 2,160명(21.8%) 있다. seed 상품은
        `is_seen=true` 로 추천 후보에서 하드 제외되므로(persona-design.md §6),
        그대로 두면 정답을 절대 맞힐 수 없는 평가가 된다.
        후보와 canonical_product_id 가 같은 이전 리뷰는 seed 가 아니라 excluded 다.
        `batch/jobs/eval_metadata.py` 도 같은 이유로 같은 방어를 하고 있다.
        → 계약 §7.1-7 에 이 조건을 명시하는 수정이 필요하다.

    is_simulation_context
        seed 만 true 다. 정답 상품이 행동 생성에 새어들면 그 로그로 추천을
        평가할 때 자기실현이 된다 (`simulator/generator/README.md` 가 같은
        이유로 --behavior hidden_preference 를 둔다).

`batch/jobs/eval_metadata.py` 는 **다른 규칙**이다 (마지막 *긍정* 리뷰를 target 으로
삼는다). 두 규칙의 차이는 `compare_holdout_rules.py` 가 수치로 낸다. 어느 쪽을
정본으로 삼을지는 아직 팀 결정 전이므로 이 파일이 계약을 이긴다고 보지 않는다.
"""
from __future__ import annotations

SEED = "seed"
HOLDOUT_TARGET = "holdout_target"
EXCLUDED = "excluded"

POSITIVE = "positive"
NEGATIVE = "negative"
DIAGNOSTIC = "diagnostic"

POSITIVE_RATING_MIN = 4        # 계약 §7.1-3
NEGATIVE_RATING_MAX = 2        # recommendation-io-spec.md 리뷰 극성


def canonical_product_id(review):
    """계약 §2.2 — group_id 가 있으면 그것이 대표 상품이다."""
    return review.get("group_id") or review.get("product_id")


def order_by_recency(reviews):
    """submission_time DESC NULLS LAST -> review_id DESC (계약 §7.1-1).

    시각이 없는 리뷰를 뒤로 밀어야 NULLS LAST 다. 파이썬 정렬 하나로는
    None 과 문자열을 비교할 수 없어 두 덩이로 나눈 뒤 이어 붙인다.
    """
    dated, undated = [], []
    for r in reviews:
        (dated if r.get("submission_time") is not None else undated).append(r)
    key = lambda r: (str(r.get("submission_time") or ""), str(r.get("review_id") or ""))
    dated.sort(key=key, reverse=True)
    undated.sort(key=lambda r: str(r.get("review_id") or ""), reverse=True)
    return dated + undated


def _label(review):
    """계약 §7.1-3~5 — 후보가 정답이 될 수 있는가."""
    rating = review.get("rating")
    if (rating is not None and rating >= POSITIVE_RATING_MIN) or review.get("is_recommended") is True:
        return POSITIVE, True
    if rating is not None and rating <= NEGATIVE_RATING_MAX:
        return NEGATIVE, False
    return DIAGNOSTIC, False       # 평점 3 또는 평점 없음


def classify(reviews, product_ids):
    """한 사람의 리뷰 목록을 판정한다.

    Args:
        reviews: 페르소나 JSON 의 `reviews` 배열
        product_ids: Product Feature 에 존재하는 canonical 상품 ID 집합

    Returns:
        (roles, decision)
        roles    : review_id -> "seed" | "holdout_target" | "excluded"
        decision : 후보 판정 결과. 후보가 없으면 None
                   {"review", "canonical_product_id", "role", "label",
                    "is_holdout_eligible"}
    """
    ordered = order_by_recency(reviews)
    if not ordered:
        return {}, None

    candidate = ordered[0]
    canonical = canonical_product_id(candidate)

    if canonical not in product_ids:
        role, label, eligible = EXCLUDED, None, False
    else:
        role = HOLDOUT_TARGET
        label, eligible = _label(candidate)

    # 후보와 같은 상품의 이전 리뷰는 seed 가 아니다 (위 누출 방지 참조)
    roles = {}
    for review in ordered[1:]:
        roles[review["review_id"]] = (
            EXCLUDED if canonical_product_id(review) == canonical else SEED)
    roles[candidate["review_id"]] = role

    decision = {
        "review": candidate,
        "canonical_product_id": canonical,
        "role": role,
        "label": label,
        "is_holdout_eligible": eligible,
    }
    return roles, decision


def is_simulation_context(role):
    """행동 생성이 이 리뷰를 참고해도 되는가 (seed 만 true)."""
    return role == SEED


def seed_reviews(reviews, roles):
    """seed 만 최신순으로 돌려준다. 평가 Profile 의 속성 원천이다."""
    return [r for r in order_by_recency(reviews) if roles.get(r["review_id"]) == SEED]
