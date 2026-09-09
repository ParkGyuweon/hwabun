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
원천 200개는 신규가 0 이다. **등록 상품**(Jira 216)이 들어오면 그때부터 채워진다.

히어로 + 배너 (Jira 218, §5-1) — 프론트 확정 2026-09-09
    curl "http://localhost:8300/api/recommend?persona_id=PC00001&size=10&banner_slots=6&reserved=2&seed=review"
    → items 10 (순수 순위) + hero (items[0] 에 축 문구, banner_type 항상 있음)
      + banners 6: 칸 1~4 축 순환(기본 concern,segment), 칸 5·6 new_brand(전용). items 와 겹치지 않음
    reason 은 아이템·배너 모두 key 하나 (attribute → content → cf → new_brand → popular)
    성분 축은 위치가중 ≥ 0.3 인 성분만. banner_slots=0 이면 예전과 같고 reserved 는 메인 안

상품 등록 (Jira 216) — 실서비스 형태
    POST /api/products  body = 계약 입력 필드 1건 또는 배열
        {"product_id":"SB000001","product_name":"…","brand_name":"SSAFY Beauty",
         "secondary_category":"Treatments","tertiary_category":"Exfoliators",
         "highlights":["Pores"],"ingredients":"Water, Lactic Acid, …","price_krw":30800}
    → §4 파생(price_usd·rating 주입·loves 0) → 계약 검사(422) → 인코딩 → 즉시 카탈로그 편입
    → `batch/ingest/data/serving/registered_products.jsonl` 에 남아 재시작 후에도 유지
    시연 브랜드 SSAFY Beauty 8개는 이 파일에 미리 들어 있다 (catalog_registry.py 로 변환).
"""
import glob
import json
import os
import sys
import time
import uuid
from typing import Any, Dict, List, Optional, Union

import numpy as np
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
JOBS = os.path.join(ROOT, "batch", "jobs")
sys.path.insert(0, JOBS)
sys.path.insert(0, BD)                      # catalog_registry (같은 폴더) — 모듈 실행(-m) 에서도 보이게

from ltr_features import LtrFeatures, load_ltr                 # noqa: E402
from persona_feature import load as load_affinity              # noqa: E402
from product_encoder import Encoder                            # noqa: E402
from recommender import (CF_MIN_SUPPORT, LAMBDA_MMR, RESERVED,  # noqa: E402
                         Recommender, load_cooc, schedule_for)
from user_vector import UserVector                             # noqa: E402
from catalog_registry import (KRW_PER_USD, Registry, RegistrationError, derive,  # noqa: E402
                              grow_square, grow_vector, validate)
from banners import AXES, DEFAULT_AXES, BannerPlanner, pick_reason      # noqa: E402
import validate_product_registration as vpr                    # noqa: E402

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
        self.ltr = ltr
        self.n_seed = len(self.products)          # 원천 카탈로그 크기 — 순위 피처 분모
        self._assemble()
        self.scorer = "ltr" if ltr else "linear"
        # 등록 상품 (Jira 216) — 원천 200개 뒤에 붙는다. 서버가 재시작해도 남는다
        self.registry = Registry(os.environ.get("REGISTERED_PRODUCTS_PATH") or None) \
            if os.environ.get("REGISTERED_PRODUCTS_PATH") else Registry()
        self._vocab = vpr.load_vocab()
        self._medians, self._overall = vpr.rating_reference()
        self._append(self.registry.load(), persist=False)
        self.planner = BannerPlanner(self.enc, self.products, self.index)   # §5-1 hero·banners (Jira 218)
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

    def _assemble(self):
        """배열들로 Recommender·LtrFeatures 를 (다시) 만든다. 상품이 늘 때마다 부른다 —
        208개 기준 수 ms 라 요청 경로에서 불러도 된다"""
        ltr = self.ltr
        # n_ref: 순위 피처 분모를 원천 카탈로그 크기로 고정 — 등록 상품이 붙어도 기존 순위 보존
        feat = (LtrFeatures(self.enc, self.V, self.prior, self.affinity, self.cooc, self.supporters,
                            n_ref=getattr(self, "n_seed", None))
                if ltr else None)
        self.rec = Recommender(self.V, self.index, self.prior, affinity=self.affinity,
                               brands=self.brands, known_brands=self.known,
                               cooc=self.cooc, supporters=self.supporters,
                               ltr=ltr[0] if ltr else None, ltr_feat=feat)

    # ── 등록 상품 편입 (Jira 216) ───────────────────────────────────────────
    def _append(self, records, persist=True):
        """파생값까지 채워진 상품 기록들을 카탈로그 뒤에 붙인다. 이미 있는 id 는 그 행을 갈아 끼운다"""
        new_rows, replaced = [], []
        for x in records:
            v = np.asarray(self.enc.encode(x), np.float32)
            gid = x["product_id"]
            if gid in self.index:
                i = self.index[gid]
                self.V[i] = v
                self.products[i] = x
                self.brands[i] = x.get("brand_name")
                replaced.append(gid)
            else:
                new_rows.append((x, v))
        if new_rows:
            k = len(new_rows)
            self.V = np.vstack([self.V] + [v for _, v in new_rows]).astype(np.float32)
            # 신규는 loves 0 → prior 0. 원천 200개의 정규화는 건드리지 않는다
            self.prior = grow_vector(self.prior, k, 0.0).astype(np.float32)
            self.cooc = grow_square(self.cooc, k)
            self.supporters = grow_vector(self.supporters, k, 0)
            for x, _ in new_rows:
                self.index[x["product_id"]] = len(self.products)
                self.products.append(x)
                self.brands.append(x.get("brand_name"))
            self.affinity.grow([x["product_id"] for x, _ in new_rows])
            # LtrFeatures 가 enc.products 를 읽는다 — 같은 리스트 객체를 유지한다
            self.enc.products = self.products
        if new_rows or replaced:
            self._assemble()
        if new_rows and getattr(self, "planner", None) is not None:
            self.planner.grow([x for x, _ in new_rows])
        if persist:
            for x in records:
                self.registry.append(x)
        return [x["product_id"] for x, _ in new_rows], replaced

    def register(self, inputs):
        """등록 입력(계약 필드) 여러 건 → 파생 → 검사 → 편입. 하나라도 계약 위반이면 전부 거절"""
        derived, warnings = [], {}
        for inp in inputs:
            x = derive(inp, self._medians, self._overall)
            warnings[x["product_id"]] = validate(x, self._vocab, self._medians, self._overall)
            derived.append(x)
        added, replaced = self._append(derived)
        is_new = self.rec.new_mask()
        out = []
        for x in derived:
            i = self.index[x["product_id"]]
            out.append({"product_id": x["product_id"], "brand_name": x["brand_name"],
                        "position_in_catalog": i, "price_usd": x["price_usd"],
                        "rating": x["rating"], "rating_source": x["rating_source"],
                        "brand_in_vocab": x["brand_name"] in self.known,
                        "reserved_candidate": bool(is_new[i]),
                        "action": "replaced" if x["product_id"] in replaced else "added",
                        "warnings": warnings[x["product_id"]]})
        return out

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
    def recommend(self, persona_id=None, size=10, reserved=RESERVED, seed_from_reviews=False,
                  banner_slots=0, axes=DEFAULT_AXES):
        """persona_id 가 없거나(익명) 페르소나 표에 없어도(실회원 accountId) 동작한다.
        속성 친화도는 빠지고 행동 상태 + 인기 prior 로 순위를 매긴다 — 요청서 C 안 (Jira 214).
        상태는 persona_id 가 있으면 그 키로 쌓이므로, 미등록 회원도 행동이 오면 개인화된다.

        banner_slots > 0 이면 hero 와 banners[] 를 함께 낸다 (§5-1, Jira 218). 그때 전용 칸
        `reserved` 는 **배너 칸**(뒤 reserved 개)에 두고 메인 items 는 순수 순위다 — 프론트 확정.
        banner_slots = 0 이면 예전처럼 reserved 가 메인 안에 든다."""
        persona = self.personas.get(persona_id) if persona_id else None
        if persona_id:
            st, source = self.state_of(persona_id, seed_from_reviews)
        else:
            st, source = UserVector(), "cold_start"
        t0 = time.perf_counter()
        scores = self.rec.score(st, persona)                      # 한 번만 계산 — 메인·배너가 같이 쓴다
        reserved_main = 0 if banner_slots > 0 else reserved
        ranked = self.rec.rank(st, persona=persona, k=size, reserved=reserved_main, flags=True,
                               scores=scores)
        pos, _ = st.weights()
        rows_seed = [self.index[g] for g in pos if g in self.index] or \
                    [self.index[g] for g in st.converted if g in self.index]
        picks = [(self.index[g], f) for g, _, f in ranked]
        is_new = self.rec.new_mask()
        rs = self.reasons(persona, st, rows_seed, picks, is_new)
        items = []
        for pos_, ((g, s, f), r) in enumerate(zip(ranked, rs), 1):
            p = self.products[self.index[g]]
            items.append({"product_id": g, "product_name": p.get("product_name"),
                          "brand_name": p.get("brand_name"), "score": round(float(s), 6),
                          "position": pos_, "reserved": bool(f), "reason": pick_reason(r),
                          "product_source": p.get("product_source", "seed_catalog")})

        hero, banners = None, None
        if banner_slots > 0:
            s_b = np.asarray(scores, float).copy()
            for g in st.converted:                                 # 전환한 상품은 배너에도 안 나온다
                i = self.index.get(g)
                if i is not None:
                    s_b[i] = -np.inf
            exclude = {it["product_id"] for it in items} | set(st.converted)
            banners, traits = self.planner.plan(s_b, rows_seed, persona, tuple(axes),
                                                banner_slots, reserved, exclude, is_new)
            b_reasons = self.reasons(persona, st, rows_seed,
                                     [(b["_row"], b["reserved"]) for b in banners], is_new)
            for b, r in zip(banners, b_reasons):
                b["reason"] = pick_reason(r)
                b["product_source"] = self.products[b.pop("_row")].get("product_source", "seed_catalog")
            if items:
                hero = self.planner.hero_for(items[0]["product_id"], traits)
        ms = (time.perf_counter() - t0) * 1000

        n_products = len(st.converted | st.viewed)
        # 유입 추적 식별자 (교차 브랜드 유입 · 추천 CTR). FE 는 recommendation_click ·
        # product_view 에 recommendation_id / list_id / position / algorithm 을 그대로 싣는다.
        body = {"persona_id": persona_id, "persona_known": persona is not None,
                "n_products": n_products,
                "recommendation_id": uuid.uuid4().hex, "list_id": "main",
                "algorithm": self.algorithm,
                "state_source": source, "scorer": self.scorer,
                "size": size, "reserved": int(reserved),
                # 전용 칸에 실제로 들어간 수 (배너 칸이면 배너에서, 아니면 메인에서).
                # 신규 상품이 카탈로그에 없으면 0 이고 그 칸은 일반 순위 — 설계된 동작
                "reserved_filled": (sum(1 for b in banners if b["reserved"]) if banners is not None
                                    else sum(1 for it in items if it["reserved"])),
                "items": items, "latency_ms": round(ms, 2)}
        if banners is not None:
            body.update({"banner_slots": int(banner_slots), "axes": list(axes),
                         "banner_list_id": "banner_row", "hero": hero, "banners": banners})
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
            "seed_products": e.n_seed, "registered_products": len(e.products) - e.n_seed,
            "personas": len(e.personas), "cf": e.cooc is not None,
            "ltr_trees": (e.ltr_meta or {}).get("n_trees"),
            "lambda_mmr": LAMBDA_MMR, "load_ms": round(e.load_ms)}


@app.get("/api/recommend")
def recommend(persona_id: Optional[str] = Query(None, description="없으면 익명 cold_start. 페르소나 표에 없는 값(실회원 id)도 받는다"),
              size: int = Query(10, ge=1, le=50),
              reserved: int = Query(RESERVED, ge=0, le=10),
              seed: Optional[str] = Query(None, description="'review' 면 리뷰 시드를 상태로 쓴다 (시연용)"),
              banner_slots: int = Query(0, ge=0, le=12, description="배너 칸 수. 0 이면 hero·banners 를 안 내린다 (§5-1)"),
              axes: str = Query(",".join(DEFAULT_AXES), description="축 배너 순환 순서. concern,ingredient,clean,price_bin,category,segment 중 쉼표 구분")):
    e = get_engine()
    ax = tuple(a.strip() for a in axes.split(",") if a.strip()) or DEFAULT_AXES
    bad = [a for a in ax if a not in AXES]
    if bad:
        raise HTTPException(422, {"code": "INVALID_AXES", "bad": bad, "allowed": list(AXES)})
    return e.recommend(persona_id or None, size, reserved, seed_from_reviews=(seed == "review"),
                       banner_slots=banner_slots, axes=ax)


class ProductRegistration(BaseModel):
    """계약 product-registration-spec 입력. price_krw 또는 price_usd 중 하나."""
    product_id: Optional[str] = None
    product_name: str
    brand_name: str
    brand_id: Optional[str] = None
    secondary_category: str
    tertiary_category: str
    highlights: List[str] = []
    ingredients: Union[str, List[str]] = []
    price_krw: Optional[float] = None
    price_usd: Optional[float] = None
    rating: Optional[float] = None
    image_url: Optional[str] = None
    review_count: Optional[int] = 0


@app.post("/api/products", status_code=201)
def register_products(body: Union[ProductRegistration, List[ProductRegistration]]):
    """등록 즉시 추천 카탈로그에 편입한다 (Jira 216). 백엔드가 상품 승인 시 한 번 부른다.
    계약 위반이면 422 와 위반 목록. 같은 product_id 를 다시 보내면 그 행을 갈아 끼운다."""
    e = get_engine()
    items = body if isinstance(body, list) else [body]
    try:
        out = e.register([it.model_dump() for it in items])
    except RegistrationError as ex:
        raise HTTPException(422, {"code": "REGISTRATION_CONTRACT_VIOLATION", "errors": ex.errors})
    return {"registered": out, "products": len(e.products),
            "registered_products": len(e.products) - e.n_seed}


@app.get("/api/products/{product_id}")
def get_product(product_id: str):
    e = get_engine()
    i = e.index.get(product_id)
    if i is None:
        raise HTTPException(404, f"product_id {product_id} 없음")
    p = e.products[i]
    return {"product_id": product_id, "brand_name": p.get("brand_name"),
            "product_source": p.get("product_source", "seed_catalog"),
            "supporters": int(e.supporters[i]) if e.supporters is not None else None,
            "reserved_candidate": bool(e.rec.new_mask()[i])}


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
