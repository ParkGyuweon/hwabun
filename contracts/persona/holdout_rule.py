# -*- coding: utf-8 -*-
"""리뷰 한 사람분을 seed / holdout_target / excluded 로 가른다.

계약 원본은 `contracts/persona-schema.md` §7.1 이다. 이 파일은 그 판정 순서를
**그대로** 옮긴 것이고, 다른 곳에서 같은 판정을 다시 구현하지 않는다.

    1  카탈로그에 있는 리뷰만 남기고 submission_time DESC NULLS LAST -> review_id DESC
       로 정렬한다. Join 실패 리뷰는 excluded 다
    2  정렬 순서대로 긍정 조건을 만족하는 첫 리뷰가 target 이다
    3  긍정 리뷰가 없으면 target 이 없다. holdout 테이블에 넣지 않는다
    4  target 보다 나중에 쓴 리뷰는 excluded 다 (시간 절단)
    5  target 보다 먼저 쓴 리뷰 중 target 과 다른 상품이 seed 다
    6  target 과 같은 상품의 이전 리뷰는 excluded 다

왜 "마지막 긍정 리뷰" 인가
    우리가 만드는 것은 선호 상품을 맞히는 추천기다. 1점 준 상품을 맞히라는 것은
    다른 과제다. 그래서 정답은 긍정 상호작용이어야 하고, 불만 리뷰는 정답이
    아니라 사람의 속성(`latest_review_label`)으로 남긴다. AI 담당과 합의했고
    `batch/jobs/eval_metadata.py` 가 이미 같은 정의를 쓴다.

계약이 정하지 않아 여기서 정한 것 — 지금은 모두 계약에 명시했다.

    긍정 조건 (§7.1.1)
        rating >= 4 또는 (is_recommended = true 그리고 rating >= 3).
        평점 3에 "추천한다" 는 정상적인 긍정 신호지만, 1~2점에 추천은 서로
        모순되는 입력이라 긍정으로 보지 않는다 (PC 9,900명 중 8명).

    tie-break (§7.1.2)
        submission_time 이 날짜 단위라 같은 날 리뷰의 선후를 못 가린다.
        review_id DESC 로 고정해 실행마다 결과가 달라지지 않게 한다.

    같은 상품의 이전 리뷰 (§7.1-6)
        seed 상품은 is_seen=true 로 추천 후보에서 하드 제외된다. 같은 상품에
        리뷰를 두 번 이상 쓴 사람이 PC 21.8% 라 상품 단위로 빼지 않으면 정답을
        절대 맞힐 수 없는 평가가 된다.

    is_simulation_context
        seed 만 true 다. 정답 상품이 행동 생성에 새어들면 그 로그로 추천을
        평가할 때 자기실현이 된다.
"""
from __future__ import annotations

SEED = "seed"
HOLDOUT_TARGET = "holdout_target"
EXCLUDED = "excluded"

POSITIVE = "positive"
NEGATIVE = "negative"
DIAGNOSTIC = "diagnostic"

POSITIVE_RATING_MIN = 4        # 계약 §7.1.1
RECOMMENDED_RATING_MIN = 3     # is_recommended 를 인정하는 하한
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


def is_positive(review):
    """계약 §7.1.1 긍정 조건."""
    rating = review.get("rating")
    if rating is None:
        return False
    if rating >= POSITIVE_RATING_MIN:
        return True
    return review.get("is_recommended") is True and rating >= RECOMMENDED_RATING_MIN


def polarity(review):
    """리뷰 하나의 극성. `latest_review_label` 과 진단용 라벨에 쓴다."""
    if is_positive(review):
        return POSITIVE
    rating = review.get("rating")
    if rating is not None and rating <= NEGATIVE_RATING_MAX:
        return NEGATIVE
    return DIAGNOSTIC              # 평점 3인데 추천 안 함, 또는 평점 없음


def classify(reviews, product_ids):
    """한 사람의 리뷰 목록을 판정한다.

    Args:
        reviews: 페르소나 JSON 의 `reviews` 배열
        product_ids: Product Feature 에 존재하는 canonical 상품 ID 집합

    Returns:
        (roles, decision)
        roles    : review_id -> "seed" | "holdout_target" | "excluded"
        decision : {"review", "canonical_product_id", "label",
                    "is_holdout_eligible", "latest_review_label"}
                   긍정 리뷰가 없으면 target 관련 키가 None 이다.
                   카탈로그에 든 리뷰가 하나도 없으면 None 이다.
    """
    joinable = [r for r in reviews if canonical_product_id(r) in product_ids]
    roles = {r["review_id"]: EXCLUDED
             for r in reviews if canonical_product_id(r) not in product_ids}

    ordered = order_by_recency(joinable)                    # 최신 -> 오래된
    if not ordered:
        return roles, None

    target = next((r for r in ordered if is_positive(r)), None)
    latest_label = polarity(ordered[0])

    if target is None:
        # 긍정 리뷰가 없다. target 없이 전부 이력으로만 쓴다 (계약 §7.1-3)
        for r in ordered:
            roles[r["review_id"]] = SEED
        return roles, {
            "review": None, "canonical_product_id": None, "label": None,
            "is_holdout_eligible": False, "latest_review_label": latest_label,
        }

    canonical = canonical_product_id(target)
    cut = ordered.index(target)
    for i, r in enumerate(ordered):
        if i < cut:
            roles[r["review_id"]] = EXCLUDED                # target 이후 — 시간 절단
        elif i == cut:
            roles[r["review_id"]] = HOLDOUT_TARGET
        elif canonical_product_id(r) == canonical:
            roles[r["review_id"]] = EXCLUDED                # 같은 상품 — 누출 방지
        else:
            roles[r["review_id"]] = SEED

    return roles, {
        "review": target,
        "canonical_product_id": canonical,
        "label": POSITIVE,
        "is_holdout_eligible": True,
        "latest_review_label": latest_label,
    }


def is_simulation_context(role):
    """행동 생성이 이 리뷰를 참고해도 되는가 (seed 만 true)."""
    return role == SEED


def seed_reviews(reviews, roles):
    """seed 만 최신순으로 돌려준다. 평가 Profile 의 속성 원천이다."""
    return [r for r in order_by_recency(reviews) if roles.get(r["review_id"]) == SEED]
