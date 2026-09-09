# -*- coding: utf-8 -*-
"""추천 추론 서버 — 계약 §5 `GET /api/recommend` 의 파이썬 참조 구현 (Jira 206).

왜 파이썬 서버인가
    모델(`ltr_model.pkl`)은 sklearn pickle 이라 자바가 못 읽는다. 피처 19개
    (`ltr_features.py`)를 자바로 다시 짜면 **에러 없이 순위만 조금씩 틀린다** —
    골든 재현에서 소수 6자리 반올림으로 두 상품 순서가 뒤집힌 적이 있다.
    학습과 서빙이 같은 코드를 쓰게 하려면 파이썬이 점수를 내고 백엔드가
    프록시하는 것이 안전하다. ONNX 로 가더라도 이 서버가 참조 구현이다.

무엇을 하나 (계약 §5 처리 1~7)
    1. 사용자 상태 조회      — 여기서는 메모리 (Redis 자리). POST /events 로 쌓는다
    4. 점수 = LTR 모델 추론  — 산출물이 없으면 선형 폴백 (Recommender 가 알아서)
    5. 노출 정책             — 전환·리뷰 제외, 조회 상한 2개 (Recommender.rank)
    6. MMR + 전용 칸         — λ_mmr 0.8, reserved 칸은 신규 상품 (§5-1)
    7. 상위 size 개 + reason

시연용 편의 — `seed=review`
    행동 로그가 없는 페르소나는 콜드 스타트(인기도·속성)만 나온다. 시연에서는
    그 사람의 **리뷰 시드 상품(eval_metadata)** 을 전환한 것으로 놓고 보여줄 수 있다.
    응답의 `state_source` 가 `"review_seed"` 로 표시된다 — 실서비스 경로가 아니다.

실행
    pip install fastapi uvicorn
    python -m uvicorn batch.serving.recommend_server:app --port 8300
    curl "http://localhost:8300/api/recommend?persona_id=PC00001&size=10&reserved=2&seed=review"
    curl "http://localhost:8300/api/recommend?size=10"                  # 익명 cold_start
    curl "http://localhost:8300/api/recommend?persona_id=member-42"     # 미등록 회원: 상태만 개인화

persona_id 규칙 (Jira 214)
    없음            → 익명. 상태 없음, 속성 친화도 없음. 인기 prior 순 + MMR. state_source=cold_start
    표에 없는 값    → 실회원 accountId 로 본다. persona_known=false, 속성 친화도 없음.
                      /api/events 로 온 행동은 그 키로 쌓여 다음 요청부터 개인화된다
    표에 있는 값    → 기존과 같다 (persona_known=true)
    404 는 더 내지 않는다 — 백엔드 프록시가 회원↔페르소나 매핑 없이도 호출할 수 있게

reserved 칸은 카탈로그에 신규 상품(지지자 <3 또는 어휘집 밖 브랜드)이 있을 때만 채워진다.
현재 200개 카탈로그는 신규가 0 이라 reserved_filled=0 이고 그 칸은 일반 순위다.
"""
import glob
import json
import os
import sys
import time
import uuid
from typing import List, Optional

import numpy as np
from fastapi import FastAPI, Query
from pydantic import BaseModel

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
JOBS = os.path.join(ROOT, "batch", "jobs")
sys.path.insert(0, JOBS)

from ltr_features import LtrFeatures, load_ltr                 # noqa: E402
from persona_feature import load as load_affinity              # noqa: E402
from product_encoder import Encoder                            # noqa: E402
from recommender import (CF_MIN_SUPPORT, LAMBDA_MMR, RESERVED,  # noqa: E402
                         Recommender, load_cooc, schedule_for)
from user_vector import UserVector                             # noqa: E402

PDIR = os.path.join(ROOT, "simulator", "personas", "data")
META_DIR = os.path.join(ROOT, "batch", "ingest", "data")


class Engine:
    """산출물을 한 번 읽어 들고, 요청마다 Recommender.rank 를 부른다."""

    def __init__(self):
        t0 = time.perf_counter()
        e = Encoder()
        self.enc = e
        self.V = np.asarray(e.matrix(), np.float32)
        self.products = e.products
        self.index = {p["product_id"]: i for i, p in enumerate(self.products)}
        lg = np.log1p(np.array([p["loves_count"] for p in self.products], float))
        self.prior = ((lg - lg.min()) / (lg.max() - lg.min())).astype(np.float32)
        self.affinity = load_affinity(self.index)
        self.brands = [p["brand_name"] for p in self.products]
        self.known = set(e.blk["brand"]["vocab"])
        self.cooc, self.supporters = load_cooc()
        ltr = load_ltr()
        self.ltr_meta = ltr[1] if ltr else None
        feat = (LtrFeatures(e, self.V, self.prior, self.affinity, self.cooc, self.supporters)
                if ltr else None)
        self.rec = Recommender(self.V, self.index, self.prior, affinity=self.affinity,
                               brands=self.brands, known_brands=self.known,
                               cooc=self.cooc, supporters=self.supporters,
                               ltr=ltr[0] if ltr else None, ltr_feat=feat)
        self.scorer = "ltr" if ltr else "linear"
        # 클릭·상세 진입 이벤트가 그대로 싣는 값 (event-properties recommendation_click.algorithm).
        # 모델이 바뀌면 문자열이 바뀌어야 하므로 학습 시각과 트리 수를 넣는다
        m = self.ltr_meta or {}
        self.algorithm = (f"ltr-{m.get('n_trees', '?')}t-{str(m.get('trained_at', ''))[:10]}"
                          if ltr else "linear-cbf-cf")
        self.personas = {}
        for fn in sorted(glob.glob(os.path.join(PDIR, "personas_*.json"))):
            with open(fn, encoding="utf-8") as f:
                for p in json.load(f):
                    self.personas[p["persona_id"]] = p
        self.seeds = {}                         # persona_id -> seed_product_ids (시연용)
        for fn in glob.glob(os.path.join(META_DIR, "eval_metadata*.jsonl")):
            with open(fn, encoding="utf-8") as f:
                for l in f:
                    r = json.loads(l)
                    self.seeds.setdefault(r["persona_id"], r["seed_product_ids"])
        self.states = {}                        # persona_id -> UserVector (Redis 자리)
        self.load_ms = (time.perf_counter() - t0) * 1000

    # ── 상태 ──────────────────────────────────────────────────────────────
    def state_of(self, persona_id, seed_from_reviews=False):
        st = self.states.get(persona_id)
        if st is not None and (st.converted or st.viewed or st.pos):
            return st, "events"
        if seed_from_reviews and persona_id in self.seeds:
            st = UserVector()
            for g in self.seeds[persona_id]:
                st.observe({"event_name": "add_to_cart", "product_id": g, "properties": {}})
            return st, "review_seed"
        return st or UserVector(), "cold_start"

    def observe(self, persona_id, events):
        st = self.states.setdefault(persona_id, UserVector())
        n = 0
        for ev in events:
            st.observe(ev); n += 1
        return n

    # ── 근거 문구 ─────────────────────────────────────────────────────────
    def reasons(self, persona, st, rows_seed, picks, is_new):
        """항별 분해(breakdown)는 LTR 에서 없다. 대신 **각 신호가 그 상품에 실제로
        있었는지**를 말한다 — 없는 근거를 지어내지 않는다."""
        N = len(self.V)
        at = self.affinity(persona) if persona is not None else np.zeros(N)
        at_hi = float(np.quantile(at, 0.8)) if np.any(at) else np.inf
        cos = None
        if rows_seed:
            u = self.V[rows_seed].mean(0); n = np.linalg.norm(u)
            cos = self.V @ (u / n) if n > 1e-9 else None
        cf = None
        if self.cooc is not None and rows_seed:
            cf = np.asarray(self.cooc)[rows_seed].sum(axis=0)
        skin = (persona or {}).get("skin_type")
        out = []
        for i, flag in picks:
            r = {}
            if flag:
                r["new_brand"] = "새로 입점한 브랜드의 상품 — 먼저 만나 보세요"
            if cf is not None and cf[i] > 0 and (self.supporters is None
                                                  or self.supporters[i] >= CF_MIN_SUPPORT):
                r["cf"] = "회원님이 담은 상품을 고른 사람들이 함께 고른 상품"
            if cos is not None and cos[i] >= 0.5:
                r["content"] = "회원님이 본 상품과 성분·고민 구성이 비슷한 상품"
            if skin and at[i] >= at_hi:
                r["attribute"] = f"{skin} 피부 사용자 사이에서 반응이 좋은 상품"
            if not r:
                r["popular"] = "많은 사용자가 선택한 상품"
            out.append(r)
        return out

    # ── 추천 ──────────────────────────────────────────────────────────────
    def recommend(self, persona_id=None, size=10, reserved=RESERVED, seed_from_reviews=False):
        """persona_id 가 없거나(익명) 페르소나 표에 없어도(실회원 accountId) 동작한다.
        속성 친화도는 빠지고 행동 상태 + 인기 prior 로 순위를 매긴다 — 요청서 C 안 (Jira 214).
        상태는 persona_id 가 있으면 그 키로 쌓이므로, 미등록 회원도 행동이 오면 개인화된다."""
        persona = self.personas.get(persona_id) if persona_id else None
        if persona_id:
            st, source = self.state_of(persona_id, seed_from_reviews)
        else:
            st, source = UserVector(), "cold_start"
        t0 = time.perf_counter()
        ranked = self.rec.rank(st, persona=persona, k=size, reserved=reserved, flags=True)
        ms = (time.perf_counter() - t0) * 1000
        pos, _ = st.weights()
        rows_seed = [self.index[g] for g in pos if g in self.index] or \
                    [self.index[g] for g in st.converted if g in self.index]
        picks = [(self.index[g], f) for g, _, f in ranked]
        is_new = self.rec.new_mask()
        rs = self.reasons(persona, st, rows_seed, picks, is_new)
        items = []
        for pos, ((g, s, f), r) in enumerate(zip(ranked, rs), 1):
            p = self.products[self.index[g]]
            items.append({"product_id": g, "product_name": p.get("product_name"),
                          "brand_name": p.get("brand_name"), "score": round(float(s), 6),
                          "position": pos, "reserved": bool(f), "reason": r})
        n_products = len(st.converted | st.viewed)
        # 유입 추적 식별자 (교차 브랜드 유입 · 추천 CTR). FE 는 recommendation_click ·
        # product_view 에 recommendation_id / list_id / position / algorithm 을 그대로 싣는다.
        body = {"persona_id": persona_id, "persona_known": persona is not None,
                "n_products": n_products,
                "recommendation_id": uuid.uuid4().hex, "list_id": "main",
                "algorithm": self.algorithm,
                "state_source": source, "scorer": self.scorer,
                "size": size, "reserved": int(reserved),
                # 전용 칸에 실제로 들어간 수. 신규 상품(지지자 <3 또는 어휘집 밖 브랜드)이
                # 카탈로그에 없으면 0 이고 그 칸은 일반 순위로 채워진다 — 설계된 동작
                "reserved_filled": sum(1 for it in items if it["reserved"]),
                "items": items, "latency_ms": round(ms, 2)}
        if self.scorer == "linear":
            w1, w2, w3 = schedule_for(len(pos))
            body["weights"] = {"cosine": w1, "attr": w2, "prior": w3}
        return body


class Event(BaseModel):
    event_name: str
    product_id: Optional[str] = None
    properties: dict = {}


class EventBatch(BaseModel):
    persona_id: str
    events: List[Event]


app = FastAPI(title="HWABUN recommend", version="0.1.0")
engine: Optional[Engine] = None


def get_engine():
    global engine
    if engine is None:
        engine = Engine()
    return engine


@app.on_event("startup")
def _startup():
    get_engine()


@app.get("/health")
def health():
    e = get_engine()
    return {"ok": True, "scorer": e.scorer, "products": len(e.products),
            "personas": len(e.personas), "cf": e.cooc is not None,
            "ltr_trees": (e.ltr_meta or {}).get("n_trees"),
            "lambda_mmr": LAMBDA_MMR, "load_ms": round(e.load_ms)}


@app.get("/api/recommend")
def recommend(persona_id: Optional[str] = Query(None, description="없으면 익명 cold_start. 페르소나 표에 없는 값(실회원 id)도 받는다"),
              size: int = Query(10, ge=1, le=50),
              reserved: int = Query(RESERVED, ge=0, le=10),
              seed: Optional[str] = Query(None, description="'review' 면 리뷰 시드를 상태로 쓴다 (시연용)")):
    e = get_engine()
    return e.recommend(persona_id or None, size, reserved, seed_from_reviews=(seed == "review"))


@app.post("/api/events")
def events(batch: EventBatch):
    e = get_engine()
    n = e.observe(batch.persona_id, [ev.model_dump() for ev in batch.events])
    st = e.states[batch.persona_id]
    return {"persona_id": batch.persona_id, "observed": n,
            "converted": sorted(st.converted), "viewed": len(st.viewed)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8300)))
