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
    curl "http://127.0.0.1:8300/api/recommend?persona_id=PC00001&size=10&banner_slots=1&reserved=0&hero=new_brand&seed=review"
    → items 10 (순수 순위) + hero (new_brand 정책: 신규 상품 중 점수 최고, 없으면 items[0]) — 현행 화면(2026-09-10 이후)
    (09-09 원안 `banner_slots=6&reserved=2`: 칸 1~4 축 순환, 칸 5·6 new_brand 전용 — 배너 행이 화면에서 빠져 지금은 안 쓴다. 능력은 남아 있다)
    reason 은 아이템·배너 모두 key 하나 (attribute → content → cf → new_brand → popular)
    성분 축은 위치가중 ≥ 0.3 인 성분만(위치 내림차순). banner_slots=0 이면 예전과 같고 reserved 는 메인 안
    hero=new_brand (Jira 237, 2026-09-10) — 배너 행이 화면에서 빠져 전용 칸이 없을 때. 신규 상품 중 점수 최고를
      히어로로 준다(응답 hero.hero_policy·reserved·product_name·score 포함). 신규가 없으면 top 으로. 기본 top.

상품 등록 (Jira 216) — 실서비스 형태
    POST /api/products  body = 계약 입력 필드 1건 또는 배열
        {"product_id":"SB000001","product_name":"…","brand_name":"SSAFY Beauty",
         "secondary_category":"Treatments","tertiary_category":"Exfoliators",
         "highlights":["Pores"],"ingredients":"Water, Lactic Acid, …","price_krw":30800}
    → §4 파생(price_usd·rating 주입·loves 0) → 계약 검사(422) → 인코딩 → 즉시 카탈로그 편입
    → `batch/ingest/data/serving/registered_products.jsonl` 에 남아 재시작 후에도 유지
    시연 브랜드 SSAFY Beauty 8개는 이 파일에 미리 들어 있다 (catalog_registry.py 로 변환).
    DELETE /api/products/{id}  판매 중단 — 후보에서 즉시 제외, 재등록하면 복귀 (Jira 219)
    POST /api/catalog/sync     쇼핑몰 백엔드(8090) ACTIVE 상품을 읽어 편입·갱신·중단 (Jira 222).
                               SHOP_BACKEND_URL + CATALOG_SYNC_INTERVAL_SEC 로 주기 실행. 승인 훅 없어도 카탈로그 일치

실시간 행동 유입 (Jira 226) — KAFKA_BOOTSTRAP_SERVERS 가 있으면 activity-events 를 별도 consumer group
    (recommend-state-v1) 으로 구독해 Engine.observe 로 넘긴다. Spark 와 독립. 수동 commit·event_id 중복 제거·
    상태 이벤트 필터. /health.kafka_state 에 alive·connected·lag. 단일 replica MVP — 확장은 updater→Redis.

세션 상태 영속화 (Jira 224) — POST /api/events 로 받은 이벤트를 session_events.jsonl 에 append 하고
    기동 때 재생한다. 재시작해도 개인화 상태가 남는다. SESSION_EVENTS_PATH (컨테이너 /data). 워커 1개 전제 그대로.
    POST /api/sessions/compact 로 페르소나별 마지막 N건만 남겨 줄인다.

대시보드 처방 문장 (Jira 220) — POST /api/prescription
    입력은 docs/dashboard/action-prescription-prompt.md §2 그대로 (판정 verb 는 프론트가 정함).
    v0.3 프롬프트 · gpt-4.1-mini · 온도 0 · json_schema 강제 → §6 자동 거부 → 저장(prescriptions.jsonl).
    응답 {prescription|null, rejected_by[], cached, model, prompt_version}. GMS_KEY 없으면 503.

배포 (Jira 219): deploy/recommend.Dockerfile · deploy/ec2-1 compose 의 `recommend` 서비스 (8300, 내부 전용).
    등록 상품은 /data 볼륨. WORKERS=1 — 상태가 프로세스 메모리라 워커를 늘리면 답이 갈린다.
"""
import glob
import datetime
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
import persona_feature as pf                                   # noqa: E402  (속성 별칭표, Jira 245)
from product_encoder import Encoder, brand_key                 # noqa: E402  (brand_key: Jira 247)
from recommender import (CF_MIN_SUPPORT, LAMBDA_MMR, RESERVED,  # noqa: E402
                         Recommender, load_cooc, schedule_for)
from user_vector import UserVector                             # noqa: E402
from catalog_registry import (KRW_PER_USD, Registry, RegistrationError, derive,  # noqa: E402
                              grow_square, grow_vector, validate)
from banners import AXES, DEFAULT_AXES, BannerPlanner, pick_reason      # noqa: E402
import prescription as rx                                               # noqa: E402
from live_stats import LiveStats, LIVE_HTML                            # noqa: E402  (Jira 295 실시간 현황)
import catalog_sync                                                     # noqa: E402  (Jira 222)
from session_store import SessionLog                                    # noqa: E402  (Jira 224)
import kafka_state                                                      # noqa: E402  (Jira 226)
import validate_product_registration as vpr                    # noqa: E402

# 히어로 정책 (2026-09-10, Jira 237). top = items[0] (계약 원안) · new_brand = 신규 상품 중 점수 최고.
HERO_POLICIES = ("top", "new_brand")

# 신규 브랜드 판정 (2026-09-11 결정, Jira 247-b): **등록 후 NEW_BRAND_DAYS 일 이내** 인 등록 상품만 신규다.
# 원천 카탈로그(세포라 200개)는 등록 시각이 없어 신규가 아니다. 이전 규칙(지지자 <3 또는 어휘집 밖 브랜드)은
# 운영 중 갱신되는 값이 없어 한 번 신규면 영영 신규였다 — 오프라인 평가 스크립트는 여전히 그 규칙을 쓴다.
# NEW_BRAND_ALWAYS_PREFIX 에 걸리는 product_id 는 기간과 무관하게 신규로 둔다. 배포는 "SB"(시연 브랜드 SSAFY Beauty 8개,
# 2026-09-14 결정, Jira 249) — 09-23 에 14일이 지나도 히어로 new_brand 후보에서 빠지지 않게. 오프라인 평가는 비움.
NEW_BRAND_DAYS = float(os.environ.get("NEW_BRAND_DAYS", "14"))
NEW_BRAND_ALWAYS_PREFIX = tuple(p for p in os.environ.get("NEW_BRAND_ALWAYS_PREFIX", "").split(",") if p.strip())


def _parse_ts(v):
    """registered_at / createdAt (ISO-8601, 'Z' 허용) → aware datetime. 못 읽으면 None"""
    if not v:
        return None
    try:
        t = datetime.datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=datetime.timezone.utc)
# 실회원 가입 속성 (Jira 245). 값은 contracts/persona-schema.md §3 enum + persona_feature 의 원본 표기 별칭.
# 검증은 여기서 하고, 정규화(lightMedium→light, brunette→brown, Grey→gray)는 persona_feature.normalize 가 한다
ATTR_PARAMS = ("skin_type", "skin_tone", "hair_color", "eye_color")
ATTR_ALLOWED = {
    "skin_type": {"combination", "dry", "normal", "oily"},
    "skin_tone": {"fair", "light", "medium", "tan", "deep"} | set(pf.TONE_BUCKET),
    "hair_color": {"auburn", "black", "blonde", "brown", "gray", "red"} | set(pf.HAIR_ALIAS),
    "eye_color": {"blue", "brown", "gray", "green", "hazel"} | set(pf.EYE_ALIAS),
}
HERO_DEFAULT = "top"

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
        self.brands = [brand_key(p) for p in self.products]         # 브랜드 키 = brand_id (Jira 247)
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
        records, inactive = self.registry.load_ops()
        self._append(records, persist=False)
        # 비활성(판매 중단) 상품 — 후보에서만 빠진다. 벡터·행은 남아 기존 순위 계산이 안 흔들린다 (Jira 219)
        self.inactive: set[str] = {g for g in inactive if g in self.index}
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
        # 세션 상태 영속화 (Jira 224) — 이벤트 로그를 재생해 재시작 전 상태로 돌아간다
        self.session_log = SessionLog()
        n_p, n_e, ms = self.session_log.replay(lambda pid, evs: self.observe(pid, evs, persist=False, source="replay"))
        self.session_replayed = {"personas": n_p, "events": n_e, "ms": ms, "path": self.session_log.path}
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
                self.brands[i] = brand_key(x)
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
                self.brands.append(brand_key(x))
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

    def deactivate(self, product_id):
        """판매 중단 — 추천 후보에서 즉시 빠진다. 재등록(POST)하면 돌아온다"""
        if product_id not in self.index:
            raise KeyError(product_id)
        self.inactive.add(product_id)
        self.registry.deactivate(product_id)

    def new_flags(self, now=None):
        """(상품수,) bool — 등록 후 NEW_BRAND_DAYS 일 이내인 등록 상품 (Jira 247-b). 원천 200개는 False.
        NEW_BRAND_ALWAYS_PREFIX 에 걸리는 id 는 항상 True. 매 요청 다시 계산한다 — 208개라 수십 µs."""
        now = now or datetime.datetime.now(datetime.timezone.utc)
        out = np.zeros(len(self.products), bool)
        for i, p in enumerate(self.products):
            if p.get("product_source", "seed_catalog") != "brand_registered":
                continue
            if NEW_BRAND_ALWAYS_PREFIX and str(p.get("product_id", "")).startswith(NEW_BRAND_ALWAYS_PREFIX):
                out[i] = True
                continue
            t = _parse_ts(p.get("registered_at"))
            out[i] = t is not None and (now - t).total_seconds() < NEW_BRAND_DAYS * 86400
        return out

    def new_until(self, p):
        """이 상품이 신규에서 빠지는 시각(ISO). 신규 대상이 아니면 None"""
        if p.get("product_source", "seed_catalog") != "brand_registered":
            return None
        if NEW_BRAND_ALWAYS_PREFIX and str(p.get("product_id", "")).startswith(NEW_BRAND_ALWAYS_PREFIX):
            return "always"
        t = _parse_ts(p.get("registered_at"))
        return (t + datetime.timedelta(days=NEW_BRAND_DAYS)).isoformat() if t else None

    def new_mask(self):
        """서버 경로의 신규 마스크 — 등록 후 N일 규칙을 Recommender 에 얹어 돌려준다"""
        self.rec.new_override = self.new_flags()
        return self.rec.new_mask()

    def _hero_row(self, hero_policy, scores, is_new):
        """new_brand 정책일 때 히어로 상품 행. 점수가 유효한(-inf 아님: 전환·비활성 제외) 신규 상품 중
        최고점. 없으면 None → 호출부가 top(items[0]) 으로 돌아간다."""
        if hero_policy != "new_brand":
            return None
        s = np.asarray(scores, float)
        cand = np.where(np.asarray(is_new, bool) & np.isfinite(s))[0]
        if len(cand) == 0:
            return None
        return int(cand[np.argmax(s[cand])])

    def _mask_inactive(self, scores):
        if not self.inactive:
            return scores
        s = np.asarray(scores, float).copy()
        for g in self.inactive:
            s[self.index[g]] = -np.inf
        return s

    def register(self, inputs):
        """등록 입력(계약 필드) 여러 건 → 파생 → 검사 → 편입. 하나라도 계약 위반이면 전부 거절"""
        derived, warnings = [], {}
        for inp in inputs:
            x = derive(inp, self._medians, self._overall)
            warnings[x["product_id"]] = validate(x, self._vocab, self._medians, self._overall)
            derived.append(x)
        added, replaced = self._append(derived)
        for x in derived:
            self.inactive.discard(x["product_id"])          # 다시 등록하면 재활성
        is_new = self.new_mask()
        out = []
        for x in derived:
            i = self.index[x["product_id"]]
            out.append({"product_id": x["product_id"], "brand_name": x["brand_name"],
                        "position_in_catalog": i, "price_usd": x["price_usd"],
                        "rating": x["rating"], "rating_source": x["rating_source"],
                        "brand_in_vocab": brand_key(x) in self.known,
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

    def observe(self, persona_id, events, persist=True, source="http", partition=None):
        st = self.states.get(persona_id)
        if st is None:                                        # setdefault 는 있어도 매번 UserVector() 를 만든다
            st = self.states[persona_id] = UserVector()
        n = 0
        for ev in events:
            st.observe(ev); n += 1
        if persist and n:
            self.session_log.append(persona_id, events)          # 상태에 영향 있는 이벤트만 남는다
        if n:
            LIVE.record_events(persona_id, events, source=source, partition=partition)   # /live (Jira 295)
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
                  banner_slots=0, axes=DEFAULT_AXES, hero_policy=HERO_DEFAULT, attrs=None):
        """persona_id 가 없거나(익명) 페르소나 표에 없어도(실회원 accountId) 동작한다.
        속성 친화도는 빠지고 행동 상태 + 인기 prior 로 순위를 매긴다 — 요청서 C 안 (Jira 214).
        상태는 persona_id 가 있으면 그 키로 쌓이므로, 미등록 회원도 행동이 오면 개인화된다.

        banner_slots > 0 이면 hero 와 banners[] 를 함께 낸다 (§5-1, Jira 218). 그때 전용 칸
        `reserved` 는 **배너 칸**(뒤 reserved 개)에 두고 메인 items 는 순수 순위다 — 프론트 확정.
        banner_slots = 0 이면 예전처럼 reserved 가 메인 안에 든다.

        hero_policy (2026-09-10): 'top' 이면 items[0] 에 축 문구 (기존). 'new_brand' 이면 신규
        상품(new_mask: 지지자 <3 또는 어휘집 밖 브랜드) 중 이 사용자 점수가 가장 높은 것을 히어로로
        준다 — 배너 행이 화면에서 빠져 전용 칸이 사라진 뒤 신규 브랜드가 배너에 나올 자리가
        히어로뿐이라서다(기획 §15-10, 09-10 포함으로 결정). 전환 상품·비활성 제외, 신규가 없으면 'top'.
        히어로 상품은 banners 와 겹치지 않게 뺀다. items 와는 겹칠 수 있다(계약 §중복 배제 그대로).

        attrs (2026-09-11, Jira 245): 실회원(accountId)은 페르소나 표에 없어 속성 친화도(LTR 피처 #1)가
        전부 중립 0.5 로 죽는다. 프론트가 가입 때 받은 skin_type·skin_tone·hair_color·eye_color 를
        쿼리로 보내면 그 값으로 persona 를 만들어 친화도·`attribute` 근거 문구·배너 콜드스타트에 쓴다.
        페르소나 표에 있는 id 면 표가 우선이고 쿼리는 무시한다(시뮬레이터·PA 경로 불변).
        일부만 와도 된다 — 없는 속성은 AffinityTable 이 중립으로 채운다."""
        persona = self.personas.get(persona_id) if persona_id else None
        attribute_source = "persona_table" if persona is not None else None
        attrs = {k: v for k, v in (attrs or {}).items() if v}
        if persona is None and attrs:
            persona = {"persona_id": persona_id, **attrs}
            attribute_source = "query"
        if persona_id:
            st, source = self.state_of(persona_id, seed_from_reviews)
        else:
            st, source = UserVector(), "cold_start"
        t0 = time.perf_counter()
        scores = self._mask_inactive(self.rec.score(st, persona))   # 한 번만 계산 — 메인·배너가 같이 쓴다
        reserved_main = 0 if banner_slots > 0 else reserved
        ranked = self.rec.rank(st, persona=persona, k=size, reserved=reserved_main, flags=True,
                               scores=scores)
        pos, _ = st.weights()
        rows_seed = [self.index[g] for g in pos if g in self.index] or \
                    [self.index[g] for g in st.converted if g in self.index]
        picks = [(self.index[g], f) for g, _, f in ranked]
        is_new = self.new_mask()
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
            # 히어로를 배너보다 먼저 정한다 — new_brand 히어로는 배너 칸과 겹치지 않게 뺀다
            hero_row = self._hero_row(hero_policy, s_b, is_new)
            if hero_row is not None:
                exclude.add(self.products[hero_row]["product_id"])
            banners, traits = self.planner.plan(s_b, rows_seed, persona, tuple(axes),
                                                banner_slots, reserved, exclude, is_new)
            b_reasons = self.reasons(persona, st, rows_seed,
                                     [(b["_row"], b["reserved"]) for b in banners], is_new)
            for b, r in zip(banners, b_reasons):
                b["reason"] = pick_reason(r)
                b["product_source"] = self.products[b.pop("_row")].get("product_source", "seed_catalog")
            if hero_row is not None:
                hp = self.products[hero_row]
                hero = self.planner.hero_for(hp["product_id"], traits)
                hr = self.reasons(persona, st, rows_seed, [(hero_row, True)], is_new)[0]
                hero.update({"hero_policy": "new_brand", "reserved": True,
                             "product_name": hp.get("product_name"), "brand_name": hp.get("brand_name"),
                             "score": round(float(s_b[hero_row]), 4), "reason": pick_reason(hr),
                             "product_source": hp.get("product_source", "seed_catalog")})
            elif items:
                hero = self.planner.hero_for(items[0]["product_id"], traits)
                # 'new_brand' 를 요청했는데 신규 상품이 없으면 top 으로 돌아간 것 — 응답에 그대로 적는다
                hero["hero_policy"] = "top"
        ms = (time.perf_counter() - t0) * 1000

        n_products = len(st.converted | st.viewed)
        # 유입 추적 식별자 (교차 브랜드 유입 · 추천 CTR). FE 는 recommendation_click ·
        # product_view 에 recommendation_id / list_id / position / algorithm 을 그대로 싣는다.
        body = {"persona_id": persona_id, "persona_known": attribute_source == "persona_table",
                # 속성 친화도의 출처 — persona_table(페르소나 표) · query(가입 속성 쿼리, Jira 245) · null(없음)
                "attribute_source": attribute_source,
                "attributes": ({k: persona.get(k) for k in ATTR_PARAMS if persona.get(k)}
                               if persona is not None else {}),
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
                         "banner_list_id": "banner_row", "hero": hero, "banners": banners,
                         "hero_policy": hero_policy})
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
LIVE = LiveStats()                      # 실시간 처리 현황 (Jira 295) — 프로세스 전역, 스레드 안전


def get_engine():
    global engine
    if engine is None:
        engine = Engine()
    return engine


# ── 쇼핑몰 백엔드 카탈로그 동기화 (Jira 222) ─────────────────────────────────
SHOP_BACKEND_URL = os.environ.get("SHOP_BACKEND_URL")                       # 예: http://shop-backend:8090
CATALOG_SYNC_INTERVAL = int(os.environ.get("CATALOG_SYNC_INTERVAL_SEC", "0") or 0)   # 0 이면 주기 실행 안 함
_last_sync: Optional[dict] = None
_sync_lock = __import__("threading").Lock()


def run_catalog_sync(base_url=None):
    """한 번 동기화. 동시에 두 번 돌지 않게 잠근다 (주기 스레드 + 수동 호출)"""
    global _last_sync
    url = base_url or SHOP_BACKEND_URL
    if not url:
        return {"error": "SHOP_BACKEND_URL 이 없다", "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    with _sync_lock:
        _last_sync = catalog_sync.sync(get_engine(), url, log=lambda m: print(m, flush=True))
    return _last_sync


def _sync_loop():
    import threading
    while True:
        time.sleep(CATALOG_SYNC_INTERVAL)
        try:
            run_catalog_sync()
        except Exception as ex:                    # 동기화가 죽어도 추천은 계속 돈다
            print(f"[catalog-sync] 실패: {ex.__class__.__name__}: {ex}", flush=True)


# ── Kafka 행동 이벤트 구독 (Jira 226) ───────────────────────────────────────
KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP_SERVERS")        # 없으면 구독 안 함 — POST /api/events 만
_kafka: Optional[kafka_state.StateConsumer] = None


@app.on_event("shutdown")
def _shutdown():
    if _kafka is not None:
        _kafka.stop()


@app.on_event("startup")
def _startup():
    global _kafka
    if KAFKA_BOOTSTRAP:
        _kafka = kafka_state.StateConsumer(get_engine(), KAFKA_BOOTSTRAP, log=lambda m: print(m, flush=True))
        _kafka.start()
    if SHOP_BACKEND_URL:
        import threading
        try:
            run_catalog_sync()                     # 첫 동기화는 기동 때 바로
        except Exception as ex:
            print(f"[catalog-sync] 첫 동기화 실패: {ex.__class__.__name__}: {ex}", flush=True)
        if CATALOG_SYNC_INTERVAL > 0:
            threading.Thread(target=_sync_loop, daemon=True, name="catalog-sync").start()
            print(f"[catalog-sync] {SHOP_BACKEND_URL} 를 {CATALOG_SYNC_INTERVAL}초마다 읽는다", flush=True)
    get_engine()


@app.get("/live/stats")
def live_stats():
    """실시간 처리 현황 숫자 (Jira 295). /live 페이지가 1초마다 읽는다"""
    e = get_engine()
    snap = LIVE.snapshot()
    snap["sessions_in_memory"] = len(e.states)
    snap["kafka"] = (_kafka.health() if _kafka is not None else None)
    snap["demo"] = _demo_status()
    return snap


# ── 시연 구동 (Jira 295): /live 의 시작 버튼이 demo_live.py 를 자식 프로세스로 띄운다 ──
_DEMO_SCRIPT = os.path.join(ROOT, "simulator", "generator", "demo_live.py")
_demo = {"proc": None, "started_at": None, "args": None, "log": None}


def _demo_status():
    p = _demo["proc"]
    running = p is not None and p.poll() is None
    tail = ""
    try:
        if _demo["log"] and os.path.exists(_demo["log"]):
            with open(_demo["log"], "rb") as f:
                f.seek(0, 2); n = f.tell(); f.seek(max(0, n - 400))
                raw = f.read()
                try:
                    txt = raw.decode("utf-8")
                except UnicodeDecodeError:
                    txt = raw.decode("cp949", "replace")          # Windows 콘솔 인코딩으로 남은 옛 줄
                lines = txt.strip().splitlines()
                tail = lines[-1] if lines else ""
    except Exception:
        tail = ""
    return {"available": os.path.exists(_DEMO_SCRIPT), "running": running,
            "exit_code": (None if running or p is None else p.returncode),
            "started_at": _demo["started_at"], "args": _demo["args"], "last_line": tail}


class DemoStart(BaseModel):
    rate: int = 3000
    max_events: int = 0
    http: bool = False


@app.post("/live/demo/start")
def live_demo_start(req: DemoStart):
    """9,900명 로그 되감기 시작 — 로컬 시연 전용. Docker 이미지에는 simulator/ 가 없어 404 가 된다"""
    if not os.path.exists(_DEMO_SCRIPT):
        raise HTTPException(404, {"code": "DEMO_UNAVAILABLE", "path": _DEMO_SCRIPT})
    if _demo_status()["running"]:
        return {"ok": True, "already": True, **_demo_status()}
    import subprocess
    log_path = os.path.join(os.path.dirname(SessionLog().path), "demo_live.log")
    port = os.environ.get("PORT", "8300")
    args = [sys.executable, _DEMO_SCRIPT, "--recommend", f"http://127.0.0.1:{port}",
            "--rate", str(max(100, min(int(req.rate), 20000)))]
    if req.max_events:
        args += ["--max-events", str(int(req.max_events))]
    if req.http:
        args += ["--http"]
    if KAFKA_BOOTSTRAP:
        args += ["--bootstrap", KAFKA_BOOTSTRAP]
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    _demo["log"] = log_path
    _demo["proc"] = subprocess.Popen(args, stdout=open(log_path, "ab"), stderr=subprocess.STDOUT, env=env, cwd=ROOT)
    _demo["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%S"); _demo["args"] = args[2:]
    return {"ok": True, **_demo_status()}


@app.post("/live/demo/stop")
def live_demo_stop():
    p = _demo["proc"]
    if p is not None and p.poll() is None:
        p.terminate()
        try:
            p.wait(5)
        except Exception:
            p.kill()
    return {"ok": True, **_demo_status()}


@app.get("/live", include_in_schema=False)
def live_page():
    """시연용 한 페이지 — 이벤트가 추천 상태에 반영되는 것을 초 단위로 보인다 (Jira 295).
    인증 없음: 추천 서버는 내부 네트워크 전용이고, 이 페이지는 nginx 에서 열어 줄 때만 밖에 보인다"""
    from fastapi.responses import HTMLResponse
    return HTMLResponse(LIVE_HTML)


@app.get("/health")
def health():
    e = get_engine()
    return {"ok": True, "scorer": e.scorer, "products": len(e.products),
            "seed_products": e.n_seed, "registered_products": len(e.products) - e.n_seed,
            "new_brand_rule": {"days": NEW_BRAND_DAYS, "always_prefix": list(NEW_BRAND_ALWAYS_PREFIX),
                               "new_now": int(e.new_flags().sum())},
            "inactive_products": len(e.inactive),
            "sessions": {"personas_in_memory": len(e.states), "replayed": e.session_replayed,
                         "appended_events": e.session_log.appended},
            # Kafka 구독 상태 (Jira 226). alive·connected·lag·last_processed_at 를 그대로 — 스레드는 장애 경계가 아니다
            "kafka_state": (_kafka.health() if _kafka is not None else None),
            "catalog_sync": ({"source": SHOP_BACKEND_URL, "interval_sec": CATALOG_SYNC_INTERVAL,
                              "last": ({k: (len(v) if isinstance(v, (list, dict)) else v)
                                        for k, v in _last_sync.items()} if _last_sync else None)}
                             if SHOP_BACKEND_URL else None),
            "personas": len(e.personas), "cf": e.cooc is not None,
            "ltr_trees": (e.ltr_meta or {}).get("n_trees"),
            "lambda_mmr": LAMBDA_MMR, "load_ms": round(e.load_ms)}


@app.get("/api/recommend")
def recommend(persona_id: Optional[str] = Query(None, description="없으면 익명 cold_start. 페르소나 표에 없는 값(실회원 id)도 받는다"),
              size: int = Query(10, ge=1, le=50),
              reserved: int = Query(RESERVED, ge=0, le=10),
              seed: Optional[str] = Query(None, description="'review' 면 리뷰 시드를 상태로 쓴다 (시연용)"),
              banner_slots: int = Query(0, ge=0, le=12, description="배너 칸 수. 0 이면 hero·banners 를 안 내린다 (§5-1)"),
              axes: str = Query(",".join(DEFAULT_AXES), description="축 배너 순환 순서. concern,ingredient,clean,price_bin,category,segment 중 쉼표 구분"),
              hero: str = Query(HERO_DEFAULT, description="히어로 정책. top = items[0] · new_brand = 신규 상품 중 점수 최고 (배너 행이 없을 때, Jira 237)"),
              skin_type: Optional[str] = Query(None, description="실회원 가입 속성 (Jira 245). combination·dry·normal·oily. 페르소나 표에 있는 id 면 무시"),
              skin_tone: Optional[str] = Query(None, description="fair·light·medium·tan·deep (원본 표기 porcelain·lightMedium 등도 버킷으로 받음)"),
              hair_color: Optional[str] = Query(None, description="auburn·black·blonde·brown·gray·red"),
              eye_color: Optional[str] = Query(None, description="blue·brown·gray·green·hazel")):
    e = get_engine()
    attrs = {"skin_type": skin_type, "skin_tone": skin_tone, "hair_color": hair_color, "eye_color": eye_color}
    bad_attrs = {k: v for k, v in attrs.items() if v and v not in ATTR_ALLOWED[k]}
    if bad_attrs:
        raise HTTPException(422, {"code": "INVALID_ATTRIBUTE", "bad": bad_attrs,
                                  "allowed": {k: sorted(v) for k, v in ATTR_ALLOWED.items()}})
    ax = tuple(a.strip() for a in axes.split(",") if a.strip()) or DEFAULT_AXES
    bad = [a for a in ax if a not in AXES]
    if bad:
        raise HTTPException(422, {"code": "INVALID_AXES", "bad": bad, "allowed": list(AXES)})
    if hero not in HERO_POLICIES:
        raise HTTPException(422, {"code": "INVALID_HERO", "bad": hero, "allowed": list(HERO_POLICIES)})
    body = e.recommend(persona_id or None, size, reserved, seed_from_reviews=(seed == "review"),
                       banner_slots=banner_slots, axes=ax, hero_policy=hero, attrs=attrs)
    LIVE.record_recommend(persona_id, body.get("latency_ms", 0))
    return body


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
    registered_at: Optional[str] = None     # 등록 시각 (백엔드 createdAt) — 신규 브랜드 14일 규칙 (Jira 247-b)


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
            "active": product_id not in e.inactive,
            "supporters": int(e.supporters[i]) if e.supporters is not None else None,
            "reserved_candidate": bool(e.new_mask()[i]),
            "registered_at": p.get("registered_at"), "new_until": e.new_until(p),
            "new_rule": f"registered within {NEW_BRAND_DAYS:g} days"}


@app.post("/api/sessions/compact")
def sessions_compact(keep_last: int = Query(500, ge=10, le=10000)):
    """세션 이벤트 로그를 페르소나별 마지막 keep_last 건만 남겨 줄인다 (Jira 224). 기동 재생 시간이 길어질 때 운영자가 부른다"""
    e = get_engine()
    before, after = e.session_log.compact(keep_last)
    return {"before": before, "after": after, "path": e.session_log.path}


@app.post("/api/catalog/sync")
def catalog_sync_now(source: Optional[str] = Query(None, description="백엔드 베이스 URL. 없으면 SHOP_BACKEND_URL")):
    """쇼핑몰 백엔드 ACTIVE 상품을 지금 읽어 카탈로그에 맞춘다 (Jira 222). 승인 훅이 없어도 카탈로그가 어긋나지 않게.
    추가·갱신·중단·거부 목록을 돌려준다. 백엔드에 못 붙으면 error 를 채워 200 으로 답한다 (추천은 영향 없음)."""
    if not (source or SHOP_BACKEND_URL):
        raise HTTPException(400, {"code": "NO_SOURCE", "message": "source 파라미터나 SHOP_BACKEND_URL 이 필요하다"})
    return run_catalog_sync(source)


@app.delete("/api/products/{product_id}")
def deactivate_product(product_id: str):
    """판매 중단·삭제 — 추천 후보에서 즉시 빠진다 (Jira 219). 백엔드가 상품 INACTIVE/삭제 시 부른다.
    기록은 registered_products.jsonl 에 op 행으로 남아 재시작 후에도 유지. 재등록(POST)하면 재활성."""
    e = get_engine()
    try:
        e.deactivate(product_id)
    except KeyError:
        raise HTTPException(404, f"product_id {product_id} 없음")
    return {"product_id": product_id, "active": False, "inactive_products": len(e.inactive)}


# ── 대시보드 처방 문장 (Jira 220) ──────────────────────────────────────────
_rx_store: Optional[rx.Store] = None
_rx_client = None
_rx_client_tried = False


def _rx_deps():
    global _rx_store, _rx_client, _rx_client_tried
    if _rx_store is None:
        _rx_store = rx.Store()
    if not _rx_client_tried:
        _rx_client = rx.make_client()
        _rx_client_tried = True
    return _rx_store, _rx_client


@app.post("/api/prescription")
def prescribe(body: rx.PrescriptionInput,
              force: bool = Query(False, description="저장본이 있어도 다시 생성"),
              model: str = Query(rx.MODEL)):
    """브랜드 대시보드 할 일 처방 문장 (docs/dashboard/action-prescription-prompt.md v0.3, Jira 225).
    판정(verb)과 옮길 위치(insert_after)는 프론트가 정해서 보낸다. 여기서는 문장만 만들고 §7 자동 거부 11개를 건다 —
    거부되면 prescription=null, rejected_by 에 코드. 실증 필요 표현은 needs_evidence 꼬리표.
    봉투는 프론트 PrescriptionEnvelope (input_hash 포함). 같은 입력은 저장본을 준다 (cached=true)."""
    store, client = _rx_deps()
    problems = rx.input_problems(body)
    if problems:                       # LLM 을 부르기 전에 끝나는 경우 — 키가 없어도 답한다
        return rx.prescribe(body, None, store, force=force, model=model)
    key = rx.store_key(body, model)
    if not force and store.get(key):
        return dict(store.get(key), cached=True)
    if client is None:
        raise HTTPException(503, {"code": "LLM_UNAVAILABLE", "message": "GMS_KEY 가 없어 처방 문장을 만들 수 없습니다"})
    return rx.prescribe(body, client, store, force=force, model=model)


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
