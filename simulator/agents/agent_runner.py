# -*- coding: utf-8 -*-
"""
LLM 에이전트 러너 — PA 페르소나가 실제 사이트를 돌아다닌다
================================================================================

무엇을 하는가
    페르소나 프로필을 LLM 에게 주고, 실제 브라우저로 프론트를 조작하게 한다.
    화면을 텍스트로 읽어 "다음에 뭘 할래" 를 묻고, 답을 받아 클릭·스크롤을 실행한다.

왜 로그를 직접 만들지 않는가
    **브라우저를 조작하면 프론트의 log.ts 가 알아서 로그를 남긴다.**
    우리가 로그를 만들면 gen_behavior_logs.py 와 다를 게 없다. 실제 DOM 을 거쳐야
    이벤트 계약·수집 API·Kafka 까지 한 번에 검증된다.

대상은 PA 100명뿐이다
    PC 9,900명은 gen_behavior_logs.py 가 합성 로그를 만든다. PA 는 그 대상에서
    빼두었으므로(--include-agents 없이는 생성 안 됨) 여기서만 로그가 생긴다.

크레딧을 아끼는 법
    --dry-run   LLM 을 부르지 않고 프롬프트만 출력한다. 문구를 다듬을 때 쓴다 (0 크레딧)
    --cache     같은 화면·같은 페르소나면 저장된 응답을 재사용한다 (2회차부터 0 크레딧)
    실측 기준 gpt-4.1-nano 가 1회 0.6 크레딧. 100명 x 30턴 = 약 1,800 (예산의 1.8%)

준비
    pip install playwright openai
    playwright install chromium

    키는 레포 루트 .env 에 둔다 (.gitignore 에 있어 커밋되지 않는다):
        GMS_KEY=...
        OPENAI_API_KEY=...      (--openai 로 개인 키를 쓸 때만)
    환경변수로 줘도 된다 — 환경변수가 .env 보다 우선한다.

실행
    python simulator/agents/agent_runner.py --dry-run --limit 1     # 프롬프트만 확인
    python simulator/agents/agent_runner.py --limit 1 --entry list         --script quick_look,click_product,wishlist_toggle,add_to_cart,back_to_list
                                                                    # 대본 리허설 (0 크레딧)
    python simulator/agents/agent_runner.py --limit 3 --headed      # 3명, 브라우저 보이게
    python simulator/agents/agent_runner.py --limit 100             # 전원 배치
    python simulator/agents/agent_runner.py --limit 100 --post http://localhost:8080

로그에 synthetic 표시를 붙이는 곳
    프론트 로거는 에이전트를 실사용자와 구분하지 못한다(브라우저로 조작하므로).
    그래서 LogSink 가 가로챈 봉투에 actor_type 과 실행 메타데이터 3종을 채운 뒤
    파일로 남기고, --post 를 주면 수집 API 로 대신 보낸다.
    계약이 정한 강제 지점이 Simulator 와 Spark 이라 프론트는 고치지 않는다.
"""
import argparse
import hashlib
import io
import json
import os
import random
import re
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
PERSONA_FILE = os.path.join(ROOT, "simulator", "personas", "data",
                            "personas_100_agent.json")
CACHE_DIR = os.path.join(BD, ".cache")
PRODUCTS_FILE = os.path.join(ROOT, "batch", "ingest", "data", "products_200.json")

# ── 카탈로그 커버리지 ─────────────────────────────────────
# 100명이 200개 중 38개만 만졌다(19%). 원인은 취향이 아니라 화면 구조다.
#   * 목록은 25개씩 끊어 보여주고 나머지는 "더 보기" 버튼 뒤에 있다
#   * 100명 전원이 같은 첫 화면에서 시작하니 보이는 후보가 늘 같은 25개다
# 프롬프트로 "더 내려보라" 고 부탁하지 않고 코드로 시작 지점을 흩는다.
# **딥링크로 시작하지 않는다.** 우리 서비스에는 검색도 광고도 없다 — 없는 유입
# 경로를 흉내 내면 로그가 실제로 일어날 수 없는 동선을 담는다. 전원 목록에서
# 출발한다 (2026-09-03 지시).
#
# 딥링크는 9/1 에 상품 커버리지를 고치려고 넣은 것이었다(27개 -> 200개). 그
# 몫은 이제 spread_start() 가 진다 — 카테고리 탭 · "더 보기" · 시작 스크롤
# 위치. **커버리지는 본실행에서 다시 재야 한다.**
#
# 경로 자체는 남겨 둔다. --entry detail 로 상세 진입을 재현할 때 쓴다.
DEEP_LINK_P = 0.0
CATEGORY_P = 0.6        # 목록에서 시작할 때 이 확률로 카테고리 탭을 하나 고른다
MAX_MORE_CLICKS = 3     # "더 보기" 한도. 25 -> 최대 100개까지 늘린다

# 한 번 굴릴 때 내려가는 px 의 **사람별 중심값** 범위.
#
# 예전에는 시작 스크롤 위치를 사람마다 다르게 흩었다. 그건 현실에 없는
# 상태다 — 검색도 광고도 없으니 **모두 목록 맨 위에서 시작한다.** 사람마다
# 다른 것은 출발점이 아니라 **얼마나 내려보는가** 다. 그래서 스크롤 폭에
# 사람별 성향을 준다. 성향은 persona_id 로 시드해 같은 사람은 늘 같다.
SCROLL_CENTER_MIN = 350
SCROLL_CENTER_MAX = 1500

GMS_BASE = "https://gms.ssafy.io/gmsapi/api.openai.com/v1"
MODEL = "gpt-4.1-nano"          # 실측 5/5 통과. 1회 0.6 크레딧

# 에이전트가 쓸 수 있는 행동. 여기 없는 것을 답하면 그 턴은 버린다.
ACTIONS = ("click_product", "scroll", "quick_look", "add_to_cart",
           "wishlist_toggle", "remove_from_cart", "back_to_list", "leave",
           "sort_list", "checkout", "click_banner", "buy_now", "write_feedback", "select_text")
# 피드백 축 — **계약 파일에서 읽는다.** 베껴 두면 조용히 어긋난다 (Jira 367).
# 09-19 실측: 러너가 "효과·발림성·가격" 을 들고 있었는데 계약·화면은 "효능·사용감·용량·가격" 이라
# 다섯 중 셋이 안 맞았다. 러너는 이 라벨로 button[aria-label="…"] 을 찾으므로 못 찾으면 예외가
# 나고 write_feedback 이 None 을 돌려주며 조용히 넘어간다. 그래서 shop_backend feedback 테이블에
# 에이전트가 남긴 행이 한 건도 없었다 — 러너 로그에는 아무 표시도 안 났다.
# 화면 버튼의 aria-label 은 contracts/feedback-category-vocab.json 의 axes[].label 이고
# (frontend/src/types/feedback.ts 가 그 파일을 그대로 import 한다), 서버가 받는 값은 axes[].id 다.
FEEDBACK_AXES_PATH = os.path.join(ROOT, "contracts", "feedback-category-vocab.json")
# 계약 파일을 못 읽을 때만 쓰는 대체값 (2026-09-19 기준). 여기도 계약과 같아야 한다
FEEDBACK_AXES_FALLBACK = {"효능": "efficacy", "사용감": "texture", "향": "scent",
                          "용기·포장": "packaging", "용량·가격": "value"}


def load_feedback_axes(path=FEEDBACK_AXES_PATH):
    """{화면 라벨: 서버 축 id}. 파일이 없거나 모양이 다르면 대체값."""
    try:
        with open(path, encoding="utf-8") as f:
            axes = json.load(f).get("axes") or []
        got = {str(a["label"]): str(a["id"]) for a in axes if a.get("label") and a.get("id")}
        return got or dict(FEEDBACK_AXES_FALLBACK)
    except Exception:
        return dict(FEEDBACK_AXES_FALLBACK)


FEEDBACK_AXES = load_feedback_axes()
FEEDBACK_MAX_CHARS = 280
# 피드백은 구매와 무관하다 (사용자 결정 09-17). 안 산 사람의 의견이 판매자에게는 더 아플 때가
# 많다. 그래서 둘러보는 중에도 남길 수 있게 행동 목록에 둔다.
#   ⚠ 백엔드가 아직 구매자만 받으면(FeedbackController.purchased) 403 이 되어 조용히 실패한다.
#     그 제한을 푸는 것은 백엔드 몫이고, 여기는 풀린 뒤를 전제한다.
# 주문 직후에도 한 번 더 기회를 준다 — 사고 나서 쓰는 것이 가장 자연스러운 자리다.
FEEDBACK_AFTER_ORDER_P = 0.6
# 리뷰도 같은 자리에서 쓴다. 피드백보다 높게 둔다 — 리뷰는 상품마다 여러 건이 모여야
# 대시보드 리뷰 탭이 값어치를 가지는데, 피드백은 몇 건만 있어도 분류를 보여준다.
REVIEW_AFTER_ORDER_P = 0.8
# 상세를 충분히 본 뒤에만 연다. 들어가자마자 의견부터 쓰는 사람은 없다.
FEEDBACK_MIN_SCROLL_PCT = 40
# 목록 정렬 (Jira 321). 프론트 ProductListPage 의 SortKey 라벨 그대로 — 화면에 보이는 말로 고르게 한다
SORT_KEYS = {"인기순": "popular", "평점 높은순": "rating", "가격 낮은순": "price_asc", "가격 높은순": "price_desc"}
# 결제 (Jira 321). PA 100명은 shop_backend 시드에 회원으로 들어 있다 (docs/shop-backend-requests.md:125)
MEMBER_EMAIL = "{pid}@persona.hwabun.local"
MEMBER_PASSWORD = "hwabun1234"
CHECKOUT_ENABLED = False      # --checkout 으로 켠다. 켜면 회원 로그인으로 들어가고 checkout 행동이 열린다
SURVEY_ANSWER_P = 0.7         # 구매 사유 설문 응답률 — 생성기(gen_behavior_logs)와 같은 값
BANNER_VISIBLE = True         # --no-banner 로 끈다: 에이전트가 배너를 못 보는 대조군 (노출 A/B, Jira 321)

# 행동을 세 개 더 연 이유
#   5개(click_product/scroll/add_to_cart/back_to_list/leave)만으로는 프론트가 정의한
#   이벤트 36종 중 상당수가 **구조적으로 생성 불가능**했다. 특히 v_u- 의 입력인
#   찜 해제·장바구니 제거가 아예 안 나왔다.
#   quick_look     목록에서 상세로 안 가고 요약만 열어보는 동선 (관심은 있으나 약함)
#   wishlist_toggle 담기 전 단계의 관심. 두 번 누르면 찜 해제 = 부정 신호
#   remove_from_cart 담았다 뺀 것. 조사 7-2 기준 상품 특정 부정 신호 중 가장 명확
#
# 다만 선택지를 늘리면 약한 모델이 그쪽으로 도망쳐 전환이 줄어든다(75턴 add_to_cart
# 0건 사고). 그래서 세 개 모두 **코드가 조건을 만족할 때만** 목록에 올린다.
QUICK_LOOK_MAX = 3      # 1인당 요약 열기 상한. 넘으면 상세로 들어가야 한다
CART_MIN_TO_REMOVE = 2  # 장바구니에 이만큼 있어야 빼는 선택지를 연다 (전환 0 방지)
MIN_DETAILS_BEFORE_LEAVE = 3   # 이만큼은 상세를 보고 나서야 나갈 수 있다

# 매 턴 화면 판정을 찍는다. 왜 그 행동이 열렸는지 못 밝힐 때만 켠다 (--debug-screen)
DEBUG_SCREEN = False

# 목록 화면 주소. 딥링크로 상세에 바로 들어온 사람은 **히스토리에 앞 페이지가 없어**
# go_back() 이 about:blank 로 간다. 그때 돌아갈 곳을 알고 있어야 복구가 된다
LIST_URL = None

# ── synthetic 실행 메타데이터 ────────────────────────────────────────────────
# 에이전트는 실제 브라우저로 프론트를 조작하므로, 아무 표시도 하지 않으면 프론트
# 로거가 실사용자와 똑같이 actor_type='user' 로 남긴다.
#
# 진입 주소에 표시를 붙이면 **프론트 로거가 그것을 읽어 봉투에 싣는다**
# (frontend/src/lib/logger.ts syntheticContextFromUrl). 그래서 평상시 LogSink 의
# 보정은 0 이고, 프론트가 표시를 못 붙인 경우에만 채운다.
# 실측: stamped 0 / already 120.
#
# LogSink 를 남겨 두는 이유는 프론트가 파라미터를 못 읽는 경우(배포 빌드,
# 파라미터 누락)에도 로그를 건지기 위해서다. 계약이 정한 강제 지점도
# Simulator + Spark 다.
# 계약: docs/analytics/log-transport-contract.md §9
#
# 이름은 gen_behavior_logs.py 와 맞춘다 — 두 생성기의 로그가 같은 Mart 에 들어간다.
# 시나리오는 배치와 같은 값을 쓰고, 배치(python_batch)와 에이전트는
# generator_type 으로 가른다 (contracts/dw-schema.md).
DEFAULT_SCENARIO_ID = "normal_day"
# 계약 enum 은 python_batch | agent_llm 이다 (contracts/event-schema.json).
# agent_realtime 은 legacy 로 명시적으로 거절된다 (contracts/tests/test_validate_events.py)
GENERATOR_TYPE = "agent_llm"

# 봉투에 schema_version 이 없을 때만 쓰는 값. 평소에는 프론트가 보낸 값을 그대로 쓴다
SCHEMA_VERSION = "0.2.0-draft"
# 수집 API 한 요청의 최대 건수. 백엔드 EventBatchRequest 의 @Size(max = 100)
POST_BATCH = 100


def default_simulation_run_id(now=None):
    """실행 ID 를 안 주면 시각으로 만든다. 배치 생성기와 같은 형식"""
    ts = now or datetime.now(timezone.utc)
    return f"run_{ts.strftime('%Y%m%dT%H%M%SZ')}"


def entry_url(base, scenario_id, simulation_run_id, product_id=None):
    """프론트 진입 주소에 synthetic 표시를 붙인다.

    프론트 로거는 **개발 서버에서만** 이 파라미터를 인정한다. 배포 화면에서도
    받아주면 주소만 고쳐 아무나 로그 출처를 위장할 수 있기 때문이다.
    (frontend/src/lib/logger.ts syntheticContextFromUrl)

    셋 중 하나라도 빠지면 로거가 user 로 되돌리므로 항상 함께 붙인다.
    """
    parts = urlsplit(base)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update({
        "actor": "synthetic",
        "gen": GENERATOR_TYPE,
        "run": simulation_run_id,
        "scenario": scenario_id,
    })
    if product_id:
        # 프론트가 이미 지원하는 진입 경로다 (App.tsx initialProductId).
        # 검색·광고로 상세에 바로 떨어지는 실제 유입에 해당한다
        query["product"] = product_id
    return urlunsplit(parts._replace(query=urlencode(query)))


def load_dotenv(path=None):
    """레포 루트 .env 에서 키를 읽어 환경변수에 얹는다.

    의존성을 늘리지 않으려고 직접 읽는다 (python-dotenv 없이 동작해야 팀원이
    받자마자 돌릴 수 있다). **이미 환경변수에 있으면 덮지 않는다** — CI 나 일회성
    실행에서 준 값이 파일보다 우선이어야 한다.
    """
    path = path or os.path.join(ROOT, ".env")
    if not os.path.exists(path):
        return
    try:
        with io.open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except Exception as exc:                      # 키가 없다고 러너가 죽으면 안 된다
        print(f"  .env 를 읽지 못했습니다 ({exc}) — 환경변수로 주십시오")


def load_prices():
    """상품별 가격.

    페르소나 레코드에는 가격이 없다. 리뷰에는 `product_id` 만 있어 카탈로그와
    조인해야 값이 나온다. 실측: 100명 **전원**이 카탈로그 상품을 리뷰했고
    (1인 평균 4.6개) 개인 상한의 중앙값은 $77 이다.
    """
    try:
        with io.open(PRODUCTS_FILE, encoding="utf-8") as f:
            return {q["product_id"]: float(q["price_usd"])
                    for q in json.load(f)
                    if q.get("product_id") and q.get("price_usd")}
    except Exception:
        return {}


PRICES = None       # 워커 프로세스마다 한 번만 읽는다


def prices():
    global PRICES
    if PRICES is None:
        PRICES = load_prices()
    return PRICES


VOCAB_FILE = os.path.join(ROOT, "contracts", "product-feature-vocab.json")


def price_bin_edges():
    """가격 구간 경계. **계약에서 직접 읽는다.**

    상품 벡터의 `price_bin` 이 쓰는 것과 같은 구간이어야 한다. 코드에 복사해
    두면 계약이 바뀔 때 조용히 어긋나고, 어긋난 줄 모른 채 돌아간다.
    """
    try:
        with io.open(VOCAB_FILE, encoding="utf-8") as f:
            return json.load(f)["price_bin_edges"]
    except Exception:
        return []


CATEGORIES = None


def categories():
    """상품별 카테고리(`secondary_category`). 프론트 탭과 같은 값이다."""
    global CATEGORIES
    if CATEGORIES is None:
        try:
            with io.open(PRODUCTS_FILE, encoding="utf-8") as f:
                CATEGORIES = {q["product_id"]: q.get("secondary_category")
                              for q in json.load(f) if q.get("product_id")}
        except Exception:
            CATEGORIES = {}
    return CATEGORIES


def preferred_categories(p):
    """이 사람이 실제로 사 온 카테고리를, 많이 산 순서로.

    **무작위로 탭을 고르지 않기 위해서다.** 사람은 아무 카테고리나 열지
    않는다 — 쓰던 것을 본다. 무작위로 고르면 커버리지는 넓어지지만 그건
    아무도 하지 않는 행동이고, 상단 노출이 더 많이 보이는 자연스러운 편향까지
    지워 버린다. 그 편향은 노출 정책 실험이 재려는 대상이다.

    100명 전원이 이력에서 카테고리가 나온다 (실측).
    """
    tab = categories()
    own = [tab[r["product_id"]] for r in p.get("reviews", [])
           if tab.get(r.get("product_id"))]
    if not own:
        return []
    seen = {}
    for c in own:
        seen[c] = seen.get(c, 0) + 1
    return [c for c, _ in sorted(seen.items(), key=lambda kv: -kv[1])]


# 2026-09-14: 사이트가 09-09 부터 원화를 보인다 (frontend/src/lib/localize.ts KRW_PER_USD). 이력·예산은
# 달러 원천이라 내부 계산은 달러로 두고, **모델에게 보이는 글자는 전부 원화**로 맞춘다 — 프로필은
# "$20~$45" 인데 카드는 "32,200원" 이면 모델이 비교할 수 없고, 러너의 가격 파싱도 None 이 됐다.
KRW_PER_USD = 1340.86


def won(usd):
    """달러 → 화면과 같은 원화 표기 (100원 단위)"""
    return f"{int(round(usd * KRW_PER_USD / 100.0) * 100):,}원"


def budget_of(p):
    """이 사람이 익숙한 가격대의 **상한**. 없으면 None.

    낸 적 있는 최고가를 그대로 쓰면 안 된다 — $24 를 내 본 사람에게 $25 가
    부담이 되어 버린다. **사람은 늘 같은 값만 내지 않는다.** 그래서 최고가가
    속한 구간(`price_bin`, 계약이 정한 5구간)의 상한을 쓴다.

        ~$20 / $20-35 / $35-50 / $50-80 / $80+

    최상위 구간에서 산 적이 있으면 상한이 없다 — 그 사람에게는 가격 부담을
    표시하지 않는다. 100명 중 47명이 여기 해당한다. 표시가 뜨는 53명에게는
    **정말로 습관 밖** 이라는 뜻이 된다.
    """
    tab = prices()
    own = [tab[r["product_id"]] for r in p.get("reviews", [])
           if r.get("product_id") in tab]
    if not own:
        return None
    # 어휘집 0.7 부터 경계가 **원화**다 (Jira 302). prices() 는 달러라 경계를 달러로 되돌려 비교·반환한다.
    # 이걸 안 하면 "익숙한 가격대 34,862,400원" 같은 값이 프롬프트에 찍히고(won() 이 환율을 두 번 곱함),
    # 장바구니 초과 판정이 영원히 거짓이 된다 (09-16 발견, Jira 331)
    top = max(own)
    for edge in price_bin_edges()[1:]:
        edge_usd = float(edge) / KRW_PER_USD if edge > 1000 else float(edge)
        if top < edge_usd:
            return edge_usd
    return None


def load_catalog():
    """딥링크로 보낼 상품 ID 목록. 프론트 목록과 같은 200개다"""
    try:
        with io.open(PRODUCTS_FILE, encoding="utf-8") as f:
            return [p["product_id"] for p in json.load(f) if p.get("product_id")]
    except Exception:
        return []


_CATEGORY_KO = None


def category_label_ko(code):
    """영문 카테고리 코드 → 사이트 한글 라벨 (contracts/localization/labels-ko.json). 없으면 None"""
    global _CATEGORY_KO
    if _CATEGORY_KO is None:
        try:
            with io.open(os.path.join(ROOT, "contracts", "localization", "labels-ko.json"),
                         encoding="utf-8") as f:
                _CATEGORY_KO = dict(json.load(f).get("category") or {})
        except Exception:
            _CATEGORY_KO = {}
    return _CATEGORY_KO.get(code)


def spread_start(page, rng, prefer=()):
    """목록에서 시작하는 사람이 무엇을 먼저 하는가.

    100명 전원이 같은 첫 화면(25개)에서 시작하면 그 25개만 후보가 된다. 다만
    **출발점을 흩는 것은 답이 아니다** — 검색도 광고도 없으니 모두 맨 위에서
    시작하는 것이 맞다. 여기서는 사람이 실제로 하는 것만 한다: 카테고리 탭을
    고른다. 목록을 늘리는 "더 보기" 는 바닥에 닿았을 때 do_action 이 누른다.
    """
    tabs = page.locator(".list__tabs button")
    if not tabs.count():
        return None                      # 목록 화면이 아니다 (상세로 바로 들어옴)

    picked = None
    if rng.random() < CATEGORY_P:
        # **자기가 사 온 카테고리를 먼저 본다.** 무작위로 고르면 커버리지는
        # 넓어지지만 아무도 하지 않는 행동이 되고, 상단 노출이 더 많이 보이는
        # 자연스러운 편향까지 지워진다 — 그 편향이 노출 정책 실험의 대상이다
        labels = []
        for n in range(tabs.count()):
            try:
                labels.append(tabs.nth(n).inner_text(timeout=1500).split(NL)[0].strip())
            except Exception:
                labels.append("")
        # 탭 글자는 "Treatments 33" 처럼 개수가 붙는다. 개수를 떼고 **이름이
        # 똑같은 탭을 먼저** 찾는다 — 부분 일치로만 찾으면 "Treatments" 를
        # 쓰던 사람이 "Lip Balms & Treatments" 탭으로 끌려간다
        names = [re.sub(r"\s*\d+$", "", t).strip() for t in labels]
        # 2026-09-14: 탭 글자가 한글("크림·로션")이고 이력 카테고리는 영문 코드("Moisturizers")라
        # 09-09 한국어화 뒤로는 이름이 맞은 적이 없었다 — 전원 무작위 탭으로 갔다.
        # 계약 어휘집(contracts/localization/labels-ko.json category) 으로 코드→한글을 붙여 비교한다
        want = [(c.lower(), (category_label_ko(c) or "").lower()) for c in prefer if c]
        idx = next((n for c, ko in want for n, t in enumerate(names)
                    if t and t.lower() in (c, ko)), None)
        if idx is None:                       # 이름이 딱 맞는 탭이 없을 때만
            idx = next((n for c, ko in want for n, t in enumerate(names)
                        if t and (c in t.lower() or (ko and ko in t.lower()))), None)
        if idx is None:                       # 이력의 카테고리가 탭에 없으면
            idx = rng.randrange(tabs.count())  # 그때만 무작위
        try:
            picked = labels[idx] or None
            tabs.nth(idx).click(timeout=3000)
            page.wait_for_timeout(700)
        except Exception:
            picked = None

    # **"더 보기" 를 미리 눌러 두지 않는다.** 버튼은 목록 바닥에 있어서 스크롤
    # 없이는 닿지 않는다. 눌러 두면 아무도 겪지 않은 상태에서 시작하게 된다.
    # 바닥까지 내려간 사람만 누르게 두는 것이 맞다 (do_action 의 scroll).

    # **시작 스크롤 위치를 흩지 않는다.** 목록 맨 위에서 시작하는 것이 사람이
    # 실제로 겪는 상태다. 예전에는 0~55% 지점으로 옮겼는데, 그건 아무도
    # 겪지 않는 화면이었다. 사람을 가르는 것은 출발점이 아니라 스크롤 폭이고
    # 그건 do_action("scroll") 이 사람별 성향으로 처리한다 (2026-09-03).
    return picked

NL = "\n"
PCT_RE = "([0-9]+)[ ]*%"   # "스크롤 62%" 에서 숫자만 뽑는다


# ============================================================================
# 1. 페르소나 -> 프로필 문장
# ============================================================================

TONE_KR = {"fair": "밝은", "light": "밝은 편", "medium": "중간",
           "tan": "어두운 편", "deep": "어두운"}
TYPE_KR = {"combination": "복합성", "dry": "건성", "normal": "중성", "oily": "지성"}


# 실험 (2026-09-08): 100명 본실행에서 담은 상품이 본인 리뷰 카테고리 안인 비율이
# 57% — 카탈로그 무작위 기대(56%)와 같았다 (lift 1.02x). 프로필에 상품 이름만 있고
# 종류(카테고리)가 없어서 모델이 카테고리를 기준으로 못 고르는 것인지 본다.
# 켜면 ① 프로필에 "주로 사 온 종류" 줄 ② 목록 줄마다 (종류) 표기 ③ 행동 기준 한 줄
PREFER_CATEGORY = False
# "먼저 보라" 는 권고형은 100명에서 lift 1.00x — 다섯 기준 중 하나로 묻혔다. strict 는
# 금지형("★ 아닌 상품은 고르지 마라") + 목록 줄에 자기 종류를 ★ 로 표시한다.
# 화면에 보이는 것만으로 잡을 수 있는 상한은 lift 1.64x (99명 중 97명이 ★ 를 봤다)
PREFER_STRICT = False
# 종류 필터를 **코드로** 강제한다 (2026-09-14, Jira 241). 프롬프트 손잡이 셋이 전부
# 무효(lift 1.00~1.26x)라 남은 자리는 허용 행동을 코드가 거르는 것과 같은 자리다:
# 목록 화면에서 내 종류 카드가 하나라도 보이면 **그 카드만 보여 준다** — 모델은 보이는
# 것 안에서만 고를 수 있으니 다른 종류는 고를 수가 없다. 내 종류가 화면에 없으면
# 전부 보여 준다 (빈 화면을 주면 leave 만 남는다). 상한 lift 1.64x 를 그대로 재는 실험.
PREFER_FILTER = False
CURRENT_PREF = ()          # 지금 돌고 있는 사람의 종류 — read_list 가 ★ 를 찍을 때 본다


def _in_pref(pid):
    """이 상품이 지금 사람의 종류 안인가. 종류를 모르는 상품(등록 상품 등)은 밖으로 본다."""
    return bool(CURRENT_PREF) and categories().get(pid) in CURRENT_PREF


STYLE_FILE = os.path.join(ROOT, "simulator", "personas", "data", "persona_style.json")
_STYLE = None
STYLE_MIN = 0.6          # 이 값 이상이면 "그걸 따지는 사람" 으로 적는다 (PA 100명 기준 각 축 약 30명)


def shopping_style(pid):
    """persona_style.json(리뷰 텍스트에서 산출한 성향 축) → 프롬프트 한 줄 (Jira 331).

    정렬을 LLM 에게 맡기니 100명 실행에서 38/38 이 '가격 낮은순' 이었다 — 화면에 가격표만 보이기 때문.
    실제 사용자는 자기 성향으로 정렬을 고른다. 그 성향은 데이터에 이미 있으니 그대로 알려 준다."""
    global _STYLE
    if _STYLE is None:
        try:
            _STYLE = json.load(open(STYLE_FILE, encoding="utf-8"))
        except Exception:
            _STYLE = {}
    st = _STYLE.get(pid) or {}
    parts = []
    if st.get("price", 0) >= STYLE_MIN:
        parts.append("가격을 많이 따진다")
    if st.get("review_lean", 0) >= STYLE_MIN:
        parts.append("리뷰와 평점을 먼저 본다")
    if st.get("ingredient", 0) >= STYLE_MIN:
        parts.append("성분표를 본다")
    if st.get("sensitivity", 0) >= STYLE_MIN:
        parts.append("자극에 민감해 순한 것을 찾는다")
    if not parts:
        return "특별히 따지는 것은 없고 남들이 많이 사는 것을 믿는 편이다"
    return ", ".join(parts)


def profile_text(p):
    """페르소나 레코드 -> LLM 에게 줄 자기소개

    구매 이력을 그대로 넣는 것이 핵심이다. "이 브랜드를 이미 샀다" 가
    다음 선택의 가장 강한 근거이기 때문이다 (브랜드 lift 6.45x).
    """
    revs = sorted(p["reviews"], key=lambda r: r["submission_time"])
    bought, seen = [], set()
    for r in revs:
        if r["group_id"] in seen:
            continue
        seen.add(r["group_id"])
        mark = "만족" if r["rating"] >= 4 else ("불만" if r["rating"] <= 2 else "보통")
        bought.append(f"{r['brand_name']} {r['product_name']} ({mark})")

    # 페르소나 레코드에는 price_usd 가 없다 — 이 줄은 카탈로그와 조인하기
    # 전까지 **한 번도 붙은 적이 없었다.** 그런데 행동 기준은 "가격대도
    # 부담스럽지 않다면" 이라고 말하고 있었다. 예산을 모르는 채로 가격 판단을
    # 시킨 셈이다 (2026-09-03 확인)
    tab = prices()
    own = [tab[r["product_id"]] for r in revs if r.get("product_id") in tab]
    price_line = ""
    if own:
        band = budget_of(p)
        price_line = f"\n- 지금까지 낸 가격: {won(min(own))} ~ {won(max(own))}"
        price_line += (f" ({won(band)} 아래가 익숙한 가격대다)" if band
                       else " (비싼 것도 사 본 적이 있다)")

    cat_line = ""
    if PREFER_CATEGORY:
        pref = preferred_categories(p)
        if pref:
            cat_line = f"\n- 주로 사 온 종류: {', '.join(pref[:3])}"
    return (f"- 피부 타입: {TYPE_KR.get(p['skin_type'], p['skin_type'])}\n"
            f"- 피부 톤: {TONE_KR.get(p['skin_tone'], p['skin_tone'])}\n"
            f"- 쇼핑 성향: {shopping_style(p['persona_id'])}"
            f"{price_line}{cat_line}\n"
            f"- 지금까지 산 것:\n    " + "\n    ".join(bought[-8:]))


SYSTEM_TMPL = """당신은 화장품 쇼핑몰에서 실제로 구매를 고민하는 사람입니다.

오늘 목표는 관심 있는 스킨케어 제품을 살펴보고, 마음에 드는 제품이 있으면
장바구니에 담고, 담은 것 중 정말 살 것이 있으면 주문까지 끝내는 것입니다.
반드시 사야 하는 것은 아니지만, 충분히 살펴본 상품은 계속 미루지 말고
담거나 목록으로 돌아가야 하고, 담아 둔 것이 마음에 남아 있으면 checkout 으로
주문을 마치십시오. 주문하면 오늘 쇼핑은 끝납니다.

[당신이 누구인가]
{profile}

[행동 기준]
- 목록에서는 **아직 보지 않은 상품 중** 내 피부 타입, 피부 톤, 구매 이력,
  가격대에 가장 맞는 상품을 하나 고르십시오.{category_rule}
- **`[이미 봄]` 이 붙은 줄은 이미 상세까지 본 상품입니다. 그 줄은 고르지 마십시오.**
  표시가 없는 줄 중에서만 고르십시오.
- 불만이었던 상품과 비슷한 것은 피하십시오.
- 상세 페이지에서는 처음에는 필요한 정보를 더 읽어볼 수 있습니다.
- 상세 페이지를 충분히 봤다면 계속 스크롤하지 말고 add_to_cart 또는
  back_to_list 중 하나를 고르십시오.
- **내 피부 타입에 맞고 가격대도 부담스럽지 않다면 add_to_cart 를 고르십시오.**
- 상세에서 **지금 바로 사겠다는 마음이 확실하면 buy_now** 를 고르십시오. 장바구니를 거치지 않고 그 상품 하나를
  바로 주문합니다. 조금이라도 고민되면 add_to_cart 로 담아 두십시오. 주문하면 오늘 쇼핑은 끝납니다.
  완벽한 상품을 찾을 때까지 미루지 마십시오 — 사람은 그렇게 쇼핑하지 않습니다.
- 피부 타입이 안 맞거나, 불만이었던 상품과 비슷하거나, 가격이 부담스러우면
  back_to_list 를 고르십시오.
- 목록 끝에 도달했고 더 관심 가는 상품이 없으면 leave 를 고르십시오.
- 궁금하지만 상세까지 볼 정도는 아니면 quick_look 으로 요약만 열어보십시오.
- 상세에서 마음에 들지만 지금 사기는 망설여지면 wishlist_toggle 로 찜하십시오.
  이미 찜한 상품이 마음에서 멀어졌으면 다시 눌러 해제하십시오.
- 장바구니에는 각 상품의 가격이 적혀 있고, 평소 가격대를 넘는 것에는 그 사실이
  함께 적힙니다. 넘는다고 못 사는 것은 아닙니다 — 다만 합계가 부담스러워졌거나
  마음이 식었다면 remove_from_cart 로 빼십시오. 그대로 두어도 됩니다.
- **장바구니에 담은 것이 있고 더 볼 상품이 없거나 살 마음이 섰으면 checkout 으로
  주문을 마치십시오.** 합계가 익숙한 가격대를 크게 넘으면 먼저 빼고 주문하십시오.
  담기만 하고 나가는 것(leave)도 사람이 하는 일이니 억지로 사지는 마십시오.
- 목록 맨 위에 `[배너]` 로 표시된 상품 하나가 크게 실려 있을 수 있습니다. 광고 자리입니다.
  문구가 내 피부나 고민에 맞아 보이면 click_banner 로 그 상품 상세에 들어갈 수 있고,
  아니면 무시하고 목록을 보십시오. 배너라서 눌러야 하는 것은 아닙니다.
- 목록 정렬은 sort_list 로 바꿀 수 있습니다 (인기순 · 평점 높은순 · 가격 낮은순 · 가격 높은순).
  **정렬은 내 쇼핑 성향으로 고르십시오.** 가격을 따지는 사람이면 가격 낮은순, 리뷰와 평점을 먼저 보는
  사람이면 평점 높은순, 남들이 많이 사는 것을 믿는 사람이면 인기순입니다. 성향에 맞는 정렬이 지금 화면
  순서(기본 인기순)와 같으면 바꾸지 마십시오. 한 세션에 한 번이고, 정렬만 바꾸고 고르지 않는 일을 반복하지 마십시오.

[답변 형식]
JSON 만 출력하십시오. 설명이나 코드블록을 붙이지 마십시오.
action 은 **이번 턴에 고를 수 있는 행동**으로 제시된 것 중에서만 고르십시오.

{{"action": {actions},
 "target": "화면에 실제로 있는 상품명",
 "reason": "내 프로필과 연결된 구체적인 한 문장"}}

target 규칙
- 목록에서 상품을 고를 때: 그 줄에 적힌 상품명을 그대로 적으십시오.
- **상세에서 담거나 찜할 때: 지금 보고 있는 상품명을 적으십시오. null 로 두지 마십시오.**
- sort_list 일 때: 정렬 이름을 그대로 적으십시오 (예: "가격 낮은순").
- click_banner 일 때: 배너에 적힌 상품명을 적으십시오.
- buy_now 일 때: 지금 보고 있는 상품명을 적으십시오.
- 상품과 무관한 행동(scroll · back_to_list · leave · checkout)일 때만 null 입니다."""


# ============================================================================
# 2. 화면 -> 텍스트
# ============================================================================

def screen_is_broken(page):
    """화면이 죽었는가 — 카드도 없고 담기 버튼도 없다.

    빈 화면에서는 어떤 조작도 성공하지 못하므로 에이전트가 남은 턴을 전부 버린다.

    원래 잡으려던 것은 AboutProduct.tsx 가 `highlighted_ingredients` 없는 상품에서
    던지던 크래시였다 (202개 중 78개). **2026-09-02 프론트가 옵셔널 체이닝으로
    고쳐 dev 에 들어갔다.** 그래도 이 판정은 남긴다 — 화면이 비는 이유가 그것
    하나뿐이라는 보장이 없고, 비었는데 계속 조작하면 로그가 조용히 망가진다.
    """
    try:
        return (not page.locator(".card[data-product-id]").count()
                and not page.locator('[data-log-action="add_to_cart"]').count())
    except Exception:
        return False


def recover_screen(page):
    """목록으로 되돌려 세션을 살린다. 돌아갈 곳을 모르면 아무것도 하지 않는다"""
    if not LIST_URL:
        return False
    page.goto(LIST_URL, wait_until="networkidle")
    page.evaluate("() => window.scrollTo(0, 0)")
    page.wait_for_timeout(900)
    return True


def read_screen(page, visited=()):
    """지금 브라우저에 보이는 것을 LLM 이 읽을 수 있는 텍스트로 만든다.

    DOM 전체를 주면 토큰이 폭발하고 모델이 헤맨다. **판단에 필요한 것만** 추린다.
    프론트가 data-product-id / data-position 을 노출해 두어 셀렉터가 안정적이다.
    """
    url = page.url
    if "/product/" in url or page.locator('[data-log-action="add_to_cart"]').count():
        return read_detail(page)
    return read_list(page, visited)


def _seen_before(title, visited):
    """카드가 이미 본 상품인가.

    `visited` 는 상세 화면의 h1(상품명)이고 카드는 "브랜드 상품명" 이라 문자열이
    똑같지 않다. 양방향 부분일치로 본다. 너무 짧으면 오탐이 나므로 8자 하한을 둔다.
    """
    t = (title or "").strip().casefold()
    for v in visited:
        v = (v or "").strip().casefold()
        if len(v) < 8 or len(t) < 8:
            continue
        if v in t or t in v:
            return True
    return False


def read_banner(page):
    """히어로 배너(AdBanner) 한 줄. 화면에 보일 때만. 이미지형이면 alt 문구를 쓴다 (Jira 321)"""
    if not BANNER_VISIBLE:
        return ""                                # 대조군 — 배너는 화면에 있지만 에이전트 눈에는 없다
    ad = page.locator("[data-banner-slot]")
    try:
        if not ad.count() or not ad.first.is_visible():
            return ""
        a = ad.first
        img = a.locator(".ad__image")
        if img.count():
            text = img.first.get_attribute("alt") or ""
        else:
            parts = []
            for sel in (".ad__brand", ".ad__badge", ".ad__kicker", ".ad__head", ".ad__sub"):
                el = a.locator(sel)
                if el.count():
                    t = el.first.inner_text(timeout=800).strip().replace("\n", " ")
                    if t:
                        parts.append(t)
            text = " · ".join(parts)
        text = " ".join(text.split())
        return f"[배너] {text}" if text else ""
    except Exception:
        return ""


def read_list(page, visited=()):
    """목록 화면. **지금 화면에 실제로 보이는 카드만** 읽는다.

    스크롤해도 같은 12개를 돌려주면 프롬프트가 안 바뀌어 LLM 이 같은 판단을
    무한 반복한다 (실제로 25턴 내내 scroll 만 한 사고가 있었다).
    """
    pct = page.evaluate(
        "() => Math.round((window.scrollY + window.innerHeight)"
        " / Math.max(document.body.scrollHeight,1) * 100)")
    cards = page.locator(".card[data-product-id]")
    lines, seen = [], set()
    hidden = 0
    # 코드 필터: 화면에 내 종류 카드가 하나라도 보이면 그것만 남긴다
    only_pref = False
    if PREFER_FILTER and CURRENT_PREF:
        for i in range(cards.count()):
            c = cards.nth(i)
            try:
                if c.is_visible() and _in_pref(c.get_attribute("data-product-id")):
                    only_pref = True
                    break
            except Exception:
                continue
    for i in range(cards.count()):
        if len(lines) >= 12:
            break
        c = cards.nth(i)
        try:
            if not c.is_visible():      # 화면 밖 카드는 보이지 않는 것이다
                continue
            pid = c.get_attribute("data-product-id")
            if only_pref and not _in_pref(pid):
                hidden += 1
                continue
            # 프로모션 배너와 그리드가 같은 .card 를 써서 같은 상품이 두 번 잡힌다.
            # 중복을 그대로 주면 LLM 이 "1번과 11번 중 뭐지" 로 헷갈린다
            if pid in seen:
                continue
            seen.add(pid)
            brand = c.locator(".card__brand").inner_text(timeout=1500).strip()
            name = c.locator(".card__name").inner_text(timeout=1500).strip()
            price = c.locator(".card__price").inner_text(timeout=1500).strip()
        except Exception:
            continue
        # **카드 줄에 직접 표시한다.** 프롬프트 위쪽에 [이미 본 상품] 목록을 따로
        # 주고 있었는데도 모델이 "이미 본 상품이 아니고" 라며 같은 상품을 다시
        # 눌렀다 (100명 중 56명). 목록과 화면을 대조하는 일을 모델에게 시키지
        # 않고, 화면 자체에 답을 적어 준다.
        title = f"{brand} {name}"
        kind_tag = ""
        if PREFER_CATEGORY and categories().get(pid):
            kind = categories()[pid]
            star = "★ " if PREFER_STRICT and kind in CURRENT_PREF else ""
            kind_tag = f" ({star}{kind})"
        lines.append(f"{len(lines)+1}. {title}{kind_tag} — {price}"
                     f"{'  [이미 봄]' if _seen_before(title, visited) else ''}")
    body = "\n".join(lines) if lines else "(화면에 상품이 없습니다)"
    banner = read_banner(page)
    if banner:
        body = banner + "\n\n" + body
    if hidden:
        body += f"\n(내가 안 쓰는 종류 {hidden}개는 눈에 들어오지 않았다)"
    # 바닥이어도 "더 보기" 가 남아 있으면 목록 끝이 아니다. 끝이라고 말하면
    # LLM 이 leave 를 고르고, 26번째 상품부터는 아무도 보지 못한다
    more = page.locator(".list__more").count() > 0
    if pct >= 97:
        tail = "  ← 목록 끝입니다" if not more else "  ← 더 내리면 상품이 더 나옵니다"
    else:
        tail = ""
    return (f"[현재 화면] 상품 목록 (스크롤 {pct}%{tail})\n\n{body}\n\n"
            f"다음에 무엇을 하시겠습니까?"), "list"


def read_detail(page):
    def txt(sel, default=""):
        try:
            return page.locator(sel).first.inner_text(timeout=1500).strip()
        except Exception:
            return default

    name = txt("h1", "(상품명 불명)")
    brand = txt(".detail__brand") or txt(".card__brand")
    price = txt(".detail__price") or txt(".card__price")
    # 지금 화면에 보이는 섹션 — 얼마나 내려왔는지를 알려준다
    secs = []
    for s in ("product_hero", "highlights", "about_product", "ingredients",
              "how_to_use", "similar_products", "reviews"):
        el = page.locator(f'[data-log-section="{s}"]')
        if el.count() and el.first.is_visible():
            secs.append(s)
    pct = page.evaluate(
        "() => Math.round((window.scrollY + window.innerHeight)"
        " / document.body.scrollHeight * 100)")
    return (f"[현재 화면] 상품 상세\n\n"
            f"{brand} {name} — {price}\n"
            f"스크롤 위치: {pct}%\n"
            f"보이는 영역: {', '.join(secs) if secs else '상단'}\n\n"
            f"다음에 무엇을 하시겠습니까?", "detail")


# ============================================================================
# 3. LLM 호출 (캐시)
# ============================================================================

class LocalLLM:
    """로컬 GPU 에 올린 오픈 모델. GMS 크레딧을 쓰지 않는다.

    100명 x 15턴이 약 900 크레딧이라 반복 실행이 부담이다. 러너가 모델에 요구하는
    것은 "허용된 행동 중 하나 + 상품명 + 한 줄 이유" 를 JSON 으로 뱉는 것뿐이라,
    작은 모델로도 되는지 먼저 확인하고 쓴다.

    서버를 따로 띄우지 않고 프로세스 안에서 돌린다. 대신 --workers 로 여러 개를
    띄우면 워커마다 모델을 올려 VRAM 이 그만큼 곱해진다 (8GB 에서는 1개만).
    """

    def __init__(self, model_id, device=None, max_new_tokens=160):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.max_new_tokens = max_new_tokens
        print(f"로컬 모델 {model_id} 를 {self.device} 에 올립니다...")
        t0 = time.time()
        self.tok = AutoTokenizer.from_pretrained(model_id)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_id, torch_dtype=torch.float16 if self.device == "cuda" else None)
        self.model.to(self.device).eval()
        print(f"  준비 {time.time() - t0:.1f}초")

    def chat(self, system, user):
        import torch
        prompt = self.tok.apply_chat_template(
            [{"role": "system", "content": system},
             {"role": "user", "content": user}],
            tokenize=False, add_generation_prompt=True)
        # JSON 만 뱉게 첫 글자를 미리 넣어 준다. 작은 모델은 서두를 붙이는 버릇이 있다
        prompt += '{"action": "'
        ids = self.tok(prompt, return_tensors="pt").to(self.device)
        with torch.no_grad():
            out = self.model.generate(
                **ids, max_new_tokens=self.max_new_tokens, do_sample=True,
                temperature=0.9, top_p=0.9, pad_token_id=self.tok.eos_token_id)
        text = self.tok.decode(out[0][ids["input_ids"].shape[1]:],
                               skip_special_tokens=True)
        return '{"action": "' + text


class ScriptedLLM:
    """정해진 순서를 돌려주는 가짜 LLM. 크레딧 0 으로 배선을 검증한다.

    행동을 새로 열 때 그것이 **실제 DOM 조작과 로그로 이어지는지**는 프롬프트를
    아무리 다듬어도 알 수 없다. 모델을 부르는 대신 순서를 강제해서, 브라우저와
    프론트 로거는 진짜인 채로 나머지 배선을 전부 확인한다.

    target 은 화면에서 고른다 — LLM 이 지어낸 이름을 흉내 내면 매칭 실패까지
    같이 재현돼 무엇을 검증하는지 흐려진다.
    """

    def __init__(self, plan):
        self.plan = list(plan)
        self.i = 0

    def next_action(self, page, acts, here, cart, visited, peeked=()):
        while self.i < len(self.plan):
            act = self.plan[self.i]
            self.i += 1
            if act not in acts:
                print(f"       [대본 {act} 은 이번 턴에 허용되지 않음 — 건너뜀]")
                continue
            target = None
            if act == "click_product":
                target = first_unvisited(page, visited)
                if target is None:
                    continue
            elif act == "quick_look":
                # 요약을 이미 열어본 카드는 다시 고르지 않는다
                target = first_unvisited(page, list(visited) + list(peeked))
                if target is None:
                    continue
            elif act in ("add_to_cart", "wishlist_toggle"):
                target = here
            elif act == "remove_from_cart":
                target = cart[-1] if cart else None
            return {"action": act, "target": target, "reason": "(대본)"}
        return {"action": "leave", "target": None, "reason": "(대본 끝)"}


def parse_action(text):
    """모델 응답에서 JSON 하나를 건진다. 앞뒤에 말을 붙여도 중괄호만 떼어 쓴다"""
    lo, hi = text.find("{"), text.rfind("}")
    if lo < 0 or hi <= lo:
        return None
    try:
        obj = json.loads(text[lo:hi + 1])
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) and obj.get("action") else None


def ask(client, system, user, cache_on, dry, expect_action=True):
    """LLM 에게 다음 행동을 묻는다.

    dry=True 면 호출하지 않고 프롬프트만 보여준다 (크레딧 0).
    cache_on 이면 (system+user) 해시로 응답을 저장·재사용한다 (2회차부터 0).
    """
    if dry:
        print("\n" + "─" * 70)
        print(system)
        print("─" * 70)
        print(user)
        print("─" * 70)
        if not expect_action:
            return {"rating": 5, "axis": "향", "body": "(dry-run) " + "샘플 " * 6}, 0
        return {"action": "scroll", "target": None, "reason": "(dry-run)"}, 0

    key = hashlib.md5((system + "\x00" + user).encode()).hexdigest()
    path = os.path.join(CACHE_DIR, key + ".json")
    if cache_on and os.path.exists(path):
        return json.load(open(path, encoding="utf-8")), 0

    kw = dict(
        model=MODEL,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        # 200 이면 reason 을 쓰다가 잘려서 JSON 이 통째로 깨진다.
        # 프롬프트가 길어질수록 reason 도 길어지므로 넉넉히 준다
        max_tokens=400,
        temperature=0.9,      # 사람마다 다르게 움직여야 한다. 낮추면 전부 같은 동선이 된다
        # 모델이 문장을 섞어 쓰지 못하게 아예 JSON 만 뱉도록 강제한다
        response_format={"type": "json_object"},
    )
    try:
        r = client.chat.completions.create(**kw)
    except Exception:
        kw.pop("response_format")        # 지원 안 하는 모델이면 없이 재시도
        r = client.chat.completions.create(**kw)
    txt = (r.choices[0].message.content or "").strip()
    finish = r.choices[0].finish_reason
    if txt.startswith("```"):                    # 코드펜스로 감싸는 경우가 있다
        txt = txt.split("```")[1]
        txt = txt[4:] if txt.startswith("json") else txt
        txt = txt.strip()
    try:
        obj = json.loads(txt)
    except Exception:
        # 왜 깨졌는지 안 보이면 고칠 수가 없다. 잘린 것인지 헛소리인지 구분한다
        why = "토큰 잘림" if finish == "length" else "파싱 실패"
        print(f"       [{why}] {txt[:110]}")
        return None, 1
    # 행동을 묻는 호출만 action 을 검사한다. 리뷰·피드백은 {"rating"/"axis", "body"} 를
    # 받으므로 action 이 없다 — 예전에는 여기서 무조건 거절돼 **한 번도 성공한 적이 없다**
    # (Jira 361). 글을 받는 호출은 expect_action=False 로 부른다.
    if expect_action and obj.get("action") not in ACTIONS:
        print(f"       [모르는 action] {obj.get('action')!r}")
        return None, 1
    if cache_on:
        os.makedirs(CACHE_DIR, exist_ok=True)
        json.dump(obj, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    return obj, 1


# ============================================================================
# 4. 행동 실행
# ============================================================================

def norm(s):
    """상품명 비교용 정규화. LLM 이 이름을 조금 다르게 쓰는 것을 흡수한다

    2026-09-14: 한글을 살린다. 이전 식(`[^a-z0-9]` 제거)은 09-09 사이트 한국어화 뒤
    카드 이름을 거의 전부 빈 문자열로 만들었고, 빈 이름은 `name in want` 에 항상 참이라
    화면 첫 카드가 매번 열렸다(종류 필터 실험에서 고른 것과 다른 상품 62%).
    """
    return re.sub(r"[^0-9a-z가-힣]", "", str(s).lower())


# 프론트 노출 훅이 요소가 50% 보인 채 300ms 머물러야 이벤트를 낸다
# (frontend/src/hooks/useImpression.ts 의 VISIBLE_RATIO · DEFAULT_HOLD_MS).
# Playwright 의 click() 은 스크롤한 뒤 곧바로 누르므로 그 300ms 가 지나지 않고,
# 결과가 "노출 없는 클릭" 이다 — 분모 0 에 분자 1 이라 CTR 이 1 을 넘는다 (Jira 354).
# 사람도 카드를 보고 나서 누르므로, 누르기 전에 화면에 올리고 머문다.
IMPRESSION_HOLD_MS = 300
DWELL_BEFORE_CLICK_MS = (520, 900)      # 유지 시간보다 넉넉히. 아래끝도 300 을 넘긴다


def dwell_then_click(loc, page, hold=None):
    """요소를 화면에 올리고 노출이 날 만큼 머문 뒤 누른다.

    스크롤이 실패해도 클릭은 시도한다 — 노출을 못 남기는 것이 클릭을 못 하는 것보다 낫다.
    """
    try:
        loc.scroll_into_view_if_needed(timeout=2000)
    except Exception:
        pass
    lo, hi = DWELL_BEFORE_CLICK_MS
    page.wait_for_timeout(hold if hold is not None else random.randint(lo, hi))
    return click_safe(loc, page)


def click_safe(loc, page):
    """겹친 요소 때문에 막히는 클릭을 뚫는다.

    카드에 마우스를 올리면 Quick Look 버튼이 카드 한가운데를 덮는다.
    Playwright 는 기본으로 요소 중앙을 누르므로 그대로 두면 30초를 기다리다
    TimeoutError 로 죽는다. 사람이라면 버튼을 피해 이미지 구석을 누를 것이므로
    좌상단(8,8) 을 먼저 누르고, 그래도 막히면 이벤트를 직접 쏜다.
    """
    for kw in ({"position": {"x": 8, "y": 8}, "timeout": 4000},
               {"timeout": 3000, "force": True}):
        try:
            loc.click(**kw)
            return True
        except Exception:
            pass
    try:
        loc.dispatch_event("click")   # 히트테스트를 건너뛰고 핸들러만 실행
        return True
    except Exception:
        return False


def find_card(page, target):
    """LLM 이 말한 이름과 맞는 목록 카드를 찾는다. 없으면 None

    이름을 줄여 쓰는 경우가 많아 부분 일치까지 허용한다. 못 찾으면 첫 카드로
    대충 누르지 않는다 — 고른 적 없는 클릭이 로그에 남으면 수집 자체를 못 믿는다.
    """
    cards = page.locator(".card[data-product-id]")
    want = norm(target)
    if not want:
        return None
    # 2026-09-14: 이름이 비었거나 아주 짧은 카드는 건너뛴다. `name in want` 는 빈 이름에
    # 항상 참이라, 화면 순서상 앞에 있는 빈 카드(배너·히어로 자리)가 매번 먹었다 —
    # 종류 필터 실험에서 62% 가 고른 것과 다른 상품을 열었다(09-08 은 1%). 같은 이유로
    # 첫 매칭이 아니라 **가장 길게 겹치는 카드**를 고른다.
    best, best_len = None, 0
    for i in range(cards.count()):
        card = cards.nth(i)
        try:
            name = norm(card.locator(".card__name").inner_text(timeout=1000))
        except Exception:
            continue
        if len(name) < 4:
            continue
        if want in name or name in want:
            score = min(len(name), len(want))
        elif want[:14] in name:
            score = 14
        else:
            continue
        if score > best_len:
            best, best_len = card, score
    return best


ORDER_DONE_SIGNS = (
    '[data-log-section="purchase_survey"]',   # 장바구니 결제의 완료 화면 (설문)
    ".survey--done",                          # 설문을 이미 낸 상태
    ".done__note",                            # 완료 문구 — buy_now 경로도 이건 그린다
    ".cart__continue",                        # "쇼핑 계속하기"
)


def _wait_order_done(page, timeout_ms=15000):
    """주문이 끝났다는 신호 중 **하나라도** 보이면 성공으로 본다.

    한 셀렉터에 걸면 그 화면을 안 지나는 경로가 통째로 실패로 찍힌다 (Jira 360).
    """
    deadline = time.time() + timeout_ms / 1000.0
    while time.time() < deadline:
        for sel in ORDER_DONE_SIGNS:
            try:
                if page.locator(sel).count():
                    return True
            except Exception:
                pass
        page.wait_for_timeout(400)
    return False


def _place_and_survey(page):
    """주문 확인 단계 → 주문 완료(place_order) → 구매 사유 설문. checkout 과 buy_now 가 같이 쓴다 (Jira 321·333).
    ?pay=test 자동 판별(프론트 09-16)로 러너는 결제창 없이 PAID 로 간다."""
    # **buy_now 는 주문 확인 단계를 건너뛴다.** 상세에서 바로 누르면 프론트가 그 자리에서
    # POST /api/orders (201) → /pay (200) 까지 하고 완료 화면으로 넘어간다 (배포본 실측
    # 2026-09-18). 그래서 place_order 버튼이 아예 없다. 예전에는 그 버튼이 없으면 곧바로
    # go_back + False 였고, 완료 화면이 눈앞에 있는데도 주문을 실패로 셌다. 그 때문에
    # `if okd` 안에 있는 주문 직후 단계(피드백·리뷰)가 통째로 안 돌았다 (Jira 361).
    if not _wait_order_done(page, timeout_ms=2000):
        place = page.locator('[data-log-action="place_order"]')
        if not place.count() or not click_safe(place.first, page):
            page.go_back(); page.wait_for_timeout(800)
            return False
        # 눌렀으면 서버 주문 + PAID 표시를 기다린다. 로그인이 없거나 서버가 거절하면
        # 완료 화면 대신 오류 문구가 남는다.
        #
        # **완료 판정을 한 셀렉터에 걸지 않는다.** `purchase_survey` 는 CartPage 의 완료
        # 화면에만 있어서, 그것만 보면 다른 경로가 통째로 실패로 찍힌다 (Jira 360).
        if not _wait_order_done(page):
            return False                         # 결제까지 못 갔다 — purchase 이벤트도 없다
    page.wait_for_timeout(random.randint(1200, 3000))       # 완료 화면을 읽는 시간
    chips = page.locator('[data-log-action="purchase_reason_toggle"]')
    if chips.count() and random.random() < SURVEY_ANSWER_P:
        click_safe(chips.nth(random.randrange(chips.count())), page)
        page.wait_for_timeout(500)
        submit = page.locator(".survey .btn--primary")
        if submit.count():
            click_safe(submit.first, page)
    else:
        skip = page.locator(".survey__skip")
        if skip.count():
            click_safe(skip.first, page)
    page.wait_for_timeout(800)
    return True


def norm_label(t):
    """LLM 이 적은 정렬 이름을 SORT_KEYS 의 키에 맞춘다 (공백·'으로'·'순으로' 따위 제거)"""
    t = str(t or "").replace(" ", "")
    for suf in ("으로", "로", "정렬"):
        if t.endswith(suf):
            t = t[: -len(suf)]
    return t


# ── 리뷰 쓰기 (Jira 356) ──────────────────────────────────────────────────
#  리뷰 칸은 **마이페이지 모달** 안에 있다 (AccountMenu 의 "내 정보" → MyPage → 주문 품목마다
#  WriteReview). 라우트가 아니라 모달이라 URL 이 안 바뀌고, 뒤로가기로는 갈 수 없다.
#
#  ⚠ 셀렉터를 두 겹으로 잡는다. 프론트가 요청한 data-log-action 5개는
#    S15P21A306-fe-buyer-reviews 브랜치에 있는데 dev·배포본에는 아직 없다(머지 뒤 추가됨).
#    배포본 번들 실측: writereview 클래스는 있고 write_review_open 은 0건.
#    속성을 먼저 찾고 없으면 클래스로 간다 — 지금도 돌고, 머지되면 자동으로 안전해진다.
REVIEW_MAX_CHARS = 300
REVIEW_MIN_CHARS = 20          # 프론트 MIN_BODY 보다 넉넉히. 짧으면 제출 버튼이 안 열린다


def _first(page, *selectors):
    """앞에서부터 실제로 있는 것을 돌려준다. 없으면 None."""
    for sel in selectors:
        loc = page.locator(sel)
        try:
            if loc.count():
                return loc.first
        except Exception:
            continue
    return None


def open_mypage(page):
    """헤더 "내 정보" 로 마이페이지 모달을 열고 주문 목록이 그려질 때까지 기다린다."""
    btn = _first(page, '[data-log-action="open_mypage"]', ".account__btn--me")
    if btn is None:
        return False                       # 로그인 상태가 아니다
    if not click_safe(btn, page):
        return False
    # 프론트가 모달을 열 때 주문 목록을 다시 받는다(ordersNonce). 품목이 나타날 때까지 기다린다
    for _ in range(20):
        page.wait_for_timeout(400)
        if page.locator('[data-log-state="orders_ready"]').count():
            break
        if page.locator(".mypage__order-item").count():
            break
    return bool(page.locator(".mypage__order-item").count())


def write_review(page, client, persona, cache_on, dry):
    """마이페이지 주문 품목에 별점과 리뷰를 남긴다.

    **미리 써 둔 문장을 고르지 않고 그 자리에서 쓴다** — write_feedback 과 같은 이유다.
    그 사람이 실제로 산 상품과 피부 타입·고민이 글에 묻어나야 판매자 화면이 값어치를 가진다.

    리뷰는 행동 로그에 남지 않는다(review_submit 이벤트는 만들지 않기로 확정). `review`
    테이블에만 쌓이고 대시보드 리뷰 탭이 그것을 읽는다.

    돌려주는 것: 보냈으면 (상품명, 별점, 글), 못 보냈으면 None.
    """
    if not open_mypage(page):
        return None

    # 아직 리뷰를 안 쓴 품목만. 쓴 품목은 writereview__done 으로 바뀐다
    items = page.locator(".mypage__order-item")
    target = None
    for i in range(min(items.count(), 20)):
        li = items.nth(i)
        try:
            if li.locator(".writereview__done").count():
                continue
            if _first_in(li) is None:
                continue
            target = li
            break
        except Exception:
            continue
    if target is None:
        return None

    try:
        name = target.locator(".mypage__order-item-name").inner_text(timeout=1500)
        name = name.split(NL)[0].strip()
    except Exception:
        name = "이 제품"

    concerns = ", ".join(persona.get("concerns") or []) or "없음"
    sys_p = ("너는 화장품을 사서 써 본 소비자다. 그 상품에 리뷰를 남긴다. "
             "광고 문구가 아니라 실제로 써 본 사람의 말투로, 좋았던 점과 아쉬운 점을 "
             "구체적으로 짚어서 쓴다. "
             'JSON 만 답한다: {"rating": <1~5 정수>, "body": "<한국어 2~3문장>"}')
    usr_p = NL.join([
        "제품: %s" % name,
        "피부 타입: %s · 피부 톤: %s · 고민: %s" % (
            persona.get("skin_type") or "모름",
            persona.get("skin_tone") or "모름",
            concerns),
        "별점은 실제 만족도대로. 다 5점을 주지 않는다.",
        "본문은 %d자 이내, %d자 이상." % (REVIEW_MAX_CHARS, REVIEW_MIN_CHARS),
    ])
    obj, _used = ask(client, sys_p, usr_p, cache_on, dry, expect_action=False)
    if not obj:
        return None
    try:
        rating = int(obj.get("rating") or 0)
    except (TypeError, ValueError):
        return None
    body = str(obj.get("body") or "").strip()[:REVIEW_MAX_CHARS]
    if not 1 <= rating <= 5 or len(body) < REVIEW_MIN_CHARS:
        return None

    try:
        opener = _first_in(target)
        if opener is None or not click_safe(opener, page):
            return None
        page.wait_for_timeout(random.randint(300, 900))
        star = _first(page, '[data-log-action="review_rating"][data-rating="%d"]' % rating,
                      ".writereview__stars button:nth-of-type(%d)" % rating)
        if star is not None:
            click_safe(star, page)
            page.wait_for_timeout(random.randint(200, 600))
        field = _first(page, '[data-log-action="review_body"]', ".writereview__body")
        if field is None:
            return None
        field.fill(body, timeout=4000)
        page.wait_for_timeout(random.randint(500, 1600))     # 쓰고 잠깐 읽어 보는 시간
        send = _first(page, '[data-log-action="review_submit"]', ".writereview__send")
        if send is None or not click_safe(send, page):
            return None
        page.wait_for_timeout(1200)
    except Exception:
        return None
    # 보냈으면 그 품목이 "리뷰 작성 완료" 로 바뀐다
    if not page.locator(".writereview__done").count():
        return None
    return (name, rating, body)


def _first_in(li):
    """품목 안의 "리뷰 쓰기" 버튼. 속성 우선, 없으면 클래스."""
    for sel in ('[data-log-action="write_review_open"]', ".writereview__open"):
        loc = li.locator(sel)
        try:
            if loc.count():
                return loc.first
        except Exception:
            continue
    return None


def write_feedback(page, client, persona, product_name, cache_on, dry):
    """상품 상세의 "이 제품에 의견 남기기" 에 페르소나가 직접 글을 써서 보낸다.

    **미리 써 둔 문장을 고르지 않고 그 자리에서 쓴다.** 그래야 그 사람이 실제로 산 상품과
    피부 타입·고민이 글에 묻어난다 — 판매자 화면의 값어치가 여기서 갈린다 (사용자 결정 09-17).

    축은 계약 고정 목록이다. 지어내면 백엔드가 400 을 준다. 화면 라벨로 고르게 하고
    FEEDBACK_AXES 로 되옮긴다.

    돌려주는 것: `(결과, 이유)`. 보냈으면 `((축 id, 글), "")`, 못 보냈으면 `(None, 이유)`.
    **이유를 반드시 돌려준다.** 예전에는 None 하나만 줘서 축 라벨이 화면과 어긋난 채로
    한 달 가까이 0건이 나가는 동안 아무 표시도 안 났다 (Jira 367).
    """
    panel = page.locator(".feedback")
    if panel.count() == 0:
        return None, "패널 없음"
    try:
        panel.first.scroll_into_view_if_needed(timeout=4000)
    except Exception:
        return None, "패널이 안 보임"

    labels = list(FEEDBACK_AXES)
    concerns = ", ".join(persona.get("concerns") or []) or "없음"
    sys_p = ("너는 화장품을 산 소비자다. 방금 쓴 제품에 대해 브랜드 사장님에게 의견을 남긴다. "
             "광고 문구가 아니라 실제로 써 본 사람의 말투로, 구체적인 한 가지를 짚어서 쓴다. "
             'JSON 만 답한다: {"axis": "<보기 중 하나>", "body": "<한국어 2~3문장>"}')
    usr_p = NL.join([
        "제품: %s" % product_name,
        "피부 타입: %s · 피부 톤: %s · 고민: %s" % (
            persona.get("skin_type") or "모름",
            persona.get("skin_tone") or "모름",
            concerns),
        "고를 수 있는 주제: %s" % " / ".join(labels),
        "본문은 %d자 이내." % FEEDBACK_MAX_CHARS,
    ])
    obj, _used = ask(client, sys_p, usr_p, cache_on, dry, expect_action=False)
    if not obj:
        return None, "LLM 응답 없음"
    label = str(obj.get("axis") or "").strip()
    body = str(obj.get("body") or "").strip()[:FEEDBACK_MAX_CHARS]
    if label not in FEEDBACK_AXES:
        return None, "축 밖 라벨 %r" % label
    if len(body) < 10:
        return None, "본문이 너무 짧음"

    # 라벨이 화면 버튼과 어긋나면 여기서 갈린다. 계약에서 읽은 라벨이니 어긋나면 화면이 바뀐 것
    axis_btn = panel.locator('button[aria-label="%s"]' % label).first
    if axis_btn.count() == 0:
        return None, "화면에 없는 축 버튼 %r (계약 %s)" % (label, os.path.basename(FEEDBACK_AXES_PATH))
    try:
        axis_btn.click(timeout=4000)
        page.wait_for_timeout(random.randint(200, 700))
        page.fill("#feedback-body", body, timeout=4000)
        page.wait_for_timeout(random.randint(400, 1500))     # 쓰고 잠깐 읽어 보는 시간
        btn = panel.locator("button.feedback__submit").first
        if btn.is_disabled():
            return None, "보내기 버튼이 잠김"
        btn.click(timeout=4000)
        page.wait_for_timeout(random.randint(600, 1600))
    except Exception as e:
        return None, "조작 실패 %s" % type(e).__name__
    # 화면이 오류를 적었으면 서버가 거절한 것이다 (401 로그인 · 409 같은 축 중복)
    err = panel.locator(".feedback__error, .feedback__send-error").first
    try:
        if err.count() and (err.inner_text(timeout=1000) or "").strip():
            return None, "서버 거절: %s" % err.inner_text(timeout=1000).strip()[:60]
    except Exception:
        pass
    return (FEEDBACK_AXES[label], body), ""


def do_action(page, act, target, scroll_center=None):
    """LLM 이 고른 행동을 실제 DOM 조작으로 옮긴다. 성공하면 True"""
    a = act

    if a == "select_text":
        # 성분 섹션의 글을 긁는다. 프론트 useTextSelection 이 selectionchange 를 350ms
        # 디바운스해서 text_selection 을 남긴다 — 진짜 마우스 드래그가 아니어도 잡힌다.
        # 성분을 중요시하는 사람이 성분명을 긁어 보는 행동이고, 대시보드의 "드래그 TOP 10"
        # 과 처방 문장이 이 값을 읽는다 (Jira 363).
        sec = page.locator('[data-log-section="ingredients"]')
        if not sec.count():
            return False
        try:
            sec.first.scroll_into_view_if_needed(timeout=4000)
            page.wait_for_timeout(random.randint(400, 1200))   # 눈으로 훑는 시간
            # **아코디언을 먼저 편다.** 접혀 있으면 성분 칩이 DOM 에 없어서 머리글 글자를
            # 긁게 되고, 그러면 어휘집에 안 걸려 matched_count 가 0 이 된다 (실측).
            tog = sec.first.locator('[data-log-action="accordion_toggle"]')
            if tog.count() and tog.first.get_attribute("aria-expanded") == "false":
                click_safe(tog.first, page)
                page.wait_for_timeout(random.randint(500, 1100))
            # **성분 이름 하나를 통째로 긁는다.** 무작위 부분 문자열로 자르면 어휘집에
            # 안 걸려 matched_count 가 0 이 되고, 대시보드의 드래그 TOP 10 은 어휘집에
            # 맞은 것만 세므로 화면에 아무것도 안 뜬다 (실측에서 확인).
            ok = sec.first.evaluate("""(el) => {
              const items = el.querySelectorAll('.chip-list li');
              let node = null;
              if (items.length) {
                node = items[Math.floor(Math.random() * items.length)];
              } else {
                const walk = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
                const parts = [];
                let n;
                while ((n = walk.nextNode())) {
                  if (n.textContent && n.textContent.trim().length > 3) parts.push(n.parentElement);
                }
                if (!parts.length) return false;
                node = parts[Math.floor(Math.random() * parts.length)];
              }
              const range = document.createRange();
              range.selectNodeContents(node);
              const sel = window.getSelection();
              sel.removeAllRanges();
              sel.addRange(range);
              return sel.toString().trim().length >= 2;
            }""")
            if not ok:
                return False
            page.wait_for_timeout(700)          # 디바운스(350ms)를 넘긴다
            # 긁은 김에 복사까지 하는 사람이 있다. 복사는 더 무거운 관심 신호다
            if random.random() < 0.3:
                page.keyboard.press("Control+C")
                page.wait_for_timeout(random.randint(200, 600))
        except Exception:
            return False
        return True


    if a == "scroll":
        # 바닥에 닿았으면 위로 올린다. 아래로만 굴리면 화면이 안 바뀌어
        # "볼 것이 없다" 로 읽히고, 실제로 위쪽에 안 본 상품이 남아 있다
        at_bottom = page.evaluate(
            "() => window.scrollY + window.innerHeight"
            " >= document.body.scrollHeight - 40")
        # **사람마다 내려보는 폭이 다르다.** 조금씩 훑는 사람과 성큼 내리는
        # 사람은 같은 15턴에서 보는 상품 수가 다르다. 중심값은 persona_id 로
        # 시드해 같은 사람은 늘 같고, 매번 ±30% 흔들어 기계처럼 보이지 않게 한다
        c = scroll_center or 850
        step = random.randint(int(c * 0.7), int(c * 1.3))
        page.mouse.wheel(0, -step if at_bottom else step)
        page.wait_for_timeout(random.randint(700, 2500))
        # 목록 바닥에 닿았고 "더 보기" 가 보이면 눌러 준다. 사람은 더 볼 게
        # 있으면 누른다. LLM 의 선택지로 두지 않는 이유는, 행동을 하나 더 늘리면
        # 약한 모델이 그쪽으로 도망쳐 상품을 안 고르기 때문이다
        more = page.locator(".list__more")
        if more.count():
            try:
                more.first.scroll_into_view_if_needed(timeout=1500)
                more.first.click(timeout=2500)
                page.wait_for_timeout(600)
            except Exception:
                pass
        return True

    if a == "back_to_list":
        page.go_back()
        page.wait_for_timeout(1200)
        # 딥링크로 상세에 바로 들어온 사람은 **돌아갈 목록이 없다.** go_back() 이
        # about:blank 로 가고, 그 빈 화면을 "다 봤다" 로 읽어 곧장 나간다
        # (실측: 5명 중 3명이 상세를 한 개도 못 열고 종료).
        # 그래서 목록 주소를 미리 기억해 두고 그리로 이동해 복구한다
        if (page.url.startswith("about:")
                or not page.locator(".card[data-product-id]").count()):
            page.goto(LIST_URL or page.url, wait_until="networkidle")
            page.evaluate("() => window.scrollTo(0, 0)")   # 복구는 목록 맨 위에서
            page.wait_for_timeout(900)
        return True

    if a == "add_to_cart":
        btn = page.locator('[data-log-action="add_to_cart"]')
        if not btn.count():
            return False                         # 목록 화면에서는 담을 수 없다
        if not click_safe(btn.first, page):
            return False
        page.wait_for_timeout(900)
        return True

    if a == "quick_look":
        # 카드에 마우스를 올려야 버튼이 뜬다. 사람이 하는 순서 그대로 간다
        card = find_card(page, target)
        if card is None:
            return False
        try:
            card.hover(timeout=2000)          # hover 가 카드를 화면에 올린다
        except Exception:
            pass
        # 올린 자리에서 머문다 — 요약을 열기 전에 그 카드의 노출이 먼저 나야 한다 (Jira 354)
        page.wait_for_timeout(random.randint(*DWELL_BEFORE_CLICK_MS))
        btn = card.locator(".card__quicklook")
        if not btn.count() or not click_safe(btn.first, page):
            return False
        page.wait_for_timeout(random.randint(900, 2200))   # 요약을 읽는 시간
        # 열었으면 닫는다. 닫는 것까지가 한 동선이라 quick_look_close 가 남는다
        close = page.locator('.qlook__close[data-log-action="quick_look_close"]')
        if close.count():
            click_safe(close.first, page)
            page.wait_for_timeout(500)
        return True

    if a == "wishlist_toggle":
        btn = page.locator('[data-log-action="wishlist_toggle"]')
        if not btn.count():
            return False                         # 목록 화면에는 없다
        if not click_safe(btn.first, page):
            return False
        page.wait_for_timeout(600)
        return True

    if a == "remove_from_cart":
        # 장바구니를 열고 -> 빼고 -> 돌아온다. 한 동선이라 코드가 묶어서 실행한다.
        # 사람도 "빼려고" 장바구니를 열지, 열어놓고 고민하지 않는다
        basket = page.locator('[data-log-action="view_cart"]')
        if not basket.count() or not click_safe(basket.first, page):
            return False
        page.wait_for_timeout(1000)
        rows = page.locator('[data-log-action="remove_from_cart"]')
        if not rows.count():
            page.go_back()
            page.wait_for_timeout(800)
            return False
        want = norm(target)
        pick = rows.first
        if want:                                 # 지목한 상품이 있으면 그것을 뺀다
            for i in range(rows.count()):
                row = rows.nth(i)
                try:
                    text = norm(row.locator("xpath=ancestor::li[1]").inner_text(timeout=800))
                except Exception:
                    continue
                if want[:14] and want[:14] in text:
                    pick = row
                    break
        ok = click_safe(pick, page)
        page.wait_for_timeout(700)
        page.go_back()                           # 보던 화면으로 돌아간다
        page.wait_for_timeout(900)
        return ok

    if a == "click_banner":
        hit = page.locator("[data-banner-slot] .ad__hit")
        if not hit.count():
            return False
        try:
            if not hit.first.is_visible():
                return False
        except Exception:
            return False
        # 배너도 같은 노출 훅을 쓴다. 머물지 않으면 banner_impression 이 안 나
        # banner_click 과 짝이 안 맞는다 (Jira 354)
        if not dwell_then_click(hit.first, page):
            return False
        page.wait_for_timeout(1400)                  # 상세로 넘어간다 — banner_click 은 프론트가 남긴다
        return True

    if a == "sort_list":
        # 프론트 <select> 하나다. 라벨로 받아 SortKey 로 바꾼다. 모르는 말이면 가격 낮은순 —
        # 정렬을 바꾸고 싶다는 뜻은 분명하고, 가격이 이 프롬프트가 가장 자주 든 이유다
        key = SORT_KEYS.get(norm_label(target), "price_asc")
        sel = page.locator(".list__sort select")
        if not sel.count():
            return False                         # 상세 화면에는 정렬이 없다
        try:
            sel.first.select_option(key)
        except Exception:
            return False
        page.wait_for_timeout(900)
        page.evaluate("() => window.scrollTo(0, 0)")   # 정렬이 바뀌면 위에서부터 다시 본다
        return True

    if a == "checkout":
        # 장바구니 → 주문하기(begin_checkout) → 주문 완료(place_order) → 구매 사유 설문.
        # 한 동선이라 코드가 묶어서 실행한다. 프론트가 결제 키(VITE_PORTONE_*) 없이 떠 있으면
        # /api/orders/{id}/pay 로 PAID 가 되고, 키가 있으면 카카오페이 창이 떠서 여기서 멈춘다 —
        # 에이전트는 결제창을 못 넘기므로 러너는 키 없는 프론트를 전제한다 (런북 §5-4)
        basket = page.locator('[data-log-action="view_cart"]')
        if not basket.count() or not click_safe(basket.first, page):
            return False
        page.wait_for_timeout(1000)
        begin = page.locator('[data-log-action="begin_checkout"]')
        if not begin.count() or not click_safe(begin.first, page):
            page.go_back(); page.wait_for_timeout(800)
            return False
        page.wait_for_timeout(900)
        return _place_and_survey(page)

    if a == "buy_now":
        # 상세의 바로구매 (프론트 09-16, data-log-action="buy_now"). 프론트가 add_to_cart → begin_checkout
        # (entry_source=buy_now) 를 연속으로 남기고 주문 확인 단계로 간다. 그 뒤는 checkout 과 같은 꼬리 (Jira 333)
        btn = page.locator('[data-log-action="buy_now"]')
        if not btn.count():
            return False                         # 상세가 아니거나 버튼이 아직 없는 프론트
        if not click_safe(btn.first, page):
            return False
        page.wait_for_timeout(1000)
        return _place_and_survey(page)

    if a == "click_product":
        card = find_card(page, target)
        if card is None:
            return False                         # 화면에 없는 상품을 지어냈다
        # 카드를 화면에 올리고 머문 뒤 누른다 — 그래야 product_impression 이 먼저 난다 (Jira 354)
        if not dwell_then_click(card.locator(".card__link").first, page):
            return False
        page.wait_for_timeout(1400)
        return True

    return False


# ============================================================================
# 5. 한 명 돌리기
# ============================================================================

DETAIL_MAX_SCROLL = 2      # 상세에서 이만큼 내렸으면 결정해야 한다


def first_unvisited(page, visited):
    """목록 화면에서 아직 안 본 상품 이름을 하나 돌려준다. 없으면 None.

    LLM 이 화면에 없는 상품을 지어냈을 때 쓰는 fallback 이다.
    '목록 첫 상품'을 무조건 누르면 그 사람이 고른 적 없는 클릭이 로그에
    남으므로, 최소한 '아직 안 본 상품'이라는 근거는 있어야 한다.
    """
    seen = {norm(v) for v in visited}
    cards = page.locator(".card[data-product-id]")
    other = None
    for i in range(min(cards.count(), 40)):
        c = cards.nth(i)
        try:
            if not c.is_visible():
                continue
            pid = c.get_attribute("data-product-id")
            brand = c.locator(".card__brand").inner_text(timeout=800).strip()
            name = c.locator(".card__name").inner_text(timeout=800).strip()
        except Exception:
            continue
        full = f"{brand} {name}"
        if any(norm(full) in v or v in norm(full) for v in seen if v):
            continue
        if PREFER_FILTER and CURRENT_PREF and not _in_pref(pid):
            other = other or full      # 내 종류가 하나도 없을 때만 쓴다
            continue
        return full
    return other


def has_unvisited_in_list(page, visited):
    """목록에 아직 안 본 상품이 남아 있는가.

    **화면에 보이는 카드만 보면 안 된다.** back_to_list 로 돌아오면 스크롤이
    복원되는데, 그 자리에 안 본 카드가 안 보이면 "다 봤다" 로 판정돼 첫 턴부터
    leave 가 열린다 (실측: 5명 중 5명이 2~3턴에 종료). 스크롤하거나 "더 보기" 를
    누르면 닿을 수 있는 것까지 세야 한다.
    """
    if page.locator(".list__more").count():
        return True                              # 아직 안 불러온 상품이 남아 있다
    seen = {norm(v) for v in visited if norm(v)}
    cards = page.locator(".card[data-product-id]")
    if not cards.count():
        # 화면이 비어 있는 것은 "다 봤다" 가 아니라 화면이 이상한 것이다.
        # 여기서 True 를 돌려줘야 leave 가 안 열리고 다음 턴에 복구할 기회가 생긴다
        return True
    for i in range(min(cards.count(), 120)):
        try:
            name = norm(cards.nth(i).locator(".card__name").inner_text(timeout=600))
        except Exception:
            continue
        if name and not any(name in v or v in name for v in seen):
            return True
    return False


def allowed_actions(kind, pct, scroll_run, carted_here, has_more=False,
                    wished_here=False, quick_looks=0, cart_size=0,
                    n_details=0, has_unvisited=True, cart_over=False,
                    sorted_once=False, checkout=None, has_banner=False,
                    feedback_here=False):
    """이번 턴에 실제로 의미가 있는 행동만 남긴다.

    행동 다섯 개를 매 턴 전부 열어주면 약한 모델은 가장 안전한 scroll 로
    도망친다. 실제로 75턴 동안 add_to_cart 가 0건이었다 — 전환이 0이면
    v_u+ 가 비어서 취향 벡터를 만들 수 없다.
    그래서 프롬프트로 부탁하지 않고 코드가 선택지를 좁힌다.
    """
    if kind == "detail":
        acts = ["back_to_list"]
        if not carted_here:
            acts.insert(0, "add_to_cart")     # 담기를 맨 앞에 둔다
        # 바로구매 — 결제가 켜져 있고 상세를 몇 개는 본 뒤에만 (checkout 과 같은 문턱, Jira 333)
        checkout_ok = CHECKOUT_ENABLED if checkout is None else checkout
        if checkout_ok and n_details >= MIN_DETAILS_BEFORE_LEAVE:
            acts.insert(1, "buy_now")
        if scroll_run < DETAIL_MAX_SCROLL:    # 다 읽었으면 더는 못 내린다
            acts.append("scroll")
        # 성분을 긁어 보는 행동. 상세에서는 늘 열어 둔다 — 성분을 중요시하는 사람이
        # 고르고, 그렇지 않은 사람은 안 고른다. 대시보드의 드래그 TOP 10 이 이 값이다
        acts.append("select_text")
        # 찜은 상품당 한 번만 연다. 계속 열어두면 담기 대신 찜만 반복한다
        if not wished_here:
            acts.append("wishlist_toggle")
        # 의견 남기기 — 구매와 무관하다. 다만 상세를 충분히 본 뒤에만 열고 상품당 한 번만 연다.
        # 백엔드가 같은 상품·같은 축 중복을 409 로 막으므로 두 번 열어도 실패한다.
        if not feedback_here and pct >= FEEDBACK_MIN_SCROLL_PCT:
            acts.append("write_feedback")
        return acts
    # 목록 화면: 끝까지 내려왔고 더 불러올 것도 없으면 scroll 은 무의미하다.
    # 다만 "더 보기" 가 남아 있으면 바닥이어도 내릴 값어치가 있다 (scroll 이
    # 더 보기를 눌러 26번째 상품부터를 화면에 올린다)
    acts = ["click_product"]
    if has_banner:
        acts.insert(1, "click_banner")
    # 목록에서는 스크롤을 늘 연다. 바닥에 닿으면 do_action 이 위로 올리므로
    # "바닥이라 볼 것이 없다" 로 갇히지 않는다. 연속 스크롤은 프롬프트가 지적한다
    acts.append("scroll")
    if quick_looks < QUICK_LOOK_MAX:
        acts.append("quick_look")
    # 담은 것이 하나뿐일 때 빼기를 열면 전환이 0 으로 돌아갈 수 있다.
    # 다만 **평소 가격대를 넘는 것을 담았다면** 하나여도 연다 — 뺄 이유가
    # 화면에 적혀 있는 상태이고, 그때도 안 열면 부정 신호가 나올 자리가
    # 없어진다 (2026-09-03 20명 실측: 세 조건이 겹친 사람이 1명뿐이었다)
    if cart_size >= CART_MIN_TO_REMOVE or (cart_over and cart_size >= 1):
        acts.append("remove_from_cart")
    # **leave 를 일찍 열지 않는다.** 시작 위치를 흩으면서 목록 아래쪽에서 출발하는
    # 사람이 생겼는데, 화면에 "목록 끝" 이 보이면 첫 턴부터 나가버렸다.
    # 상세를 몇 개는 보고 나서, 그리고 화면에 새 상품이 없을 때만 나갈 수 있다
    # 정렬은 목록에서 한 번만. 매 턴 열어두면 정렬만 바꾸며 도망친다 (Jira 321)
    if not sorted_once:
        acts.append("sort_list")
    # 결제는 담은 것이 있고 상세를 몇 개는 본 뒤에만. leave 와 같은 문턱이다 —
    # 담자마자 사게 두면 "담고 안 산 사람" 이 사라져 전환 신호의 대조군이 없어진다
    checkout = CHECKOUT_ENABLED if checkout is None else checkout
    if checkout and cart_size >= 1 and n_details >= MIN_DETAILS_BEFORE_LEAVE:
        acts.append("checkout")
    # 리뷰는 여기 오지 않는다. 산 뒤에만 쓸 수 있는데(백엔드가 order_item_id 로 검증)
    # 주문하면 run_one 이 곧바로 break 하므로 `purchased >= 1` 인 턴이 없다 — 행동으로
    # 두면 선택지에 영원히 안 오른다(실측 125턴 0회). 주문 직후 단계로 옮겼다 (Jira 360).
    if n_details >= MIN_DETAILS_BEFORE_LEAVE or not has_unvisited:
        acts.append("leave")
    return acts


def detail_title(user):
    """상세 화면 프롬프트에서 상품명 줄만 뽑는다"""
    parts = user.split(NL + NL)
    if len(parts) > 1:
        return parts[1].split(" — ")[0].strip()
    return ""


def detail_price(user):
    """상세 화면 프롬프트에서 가격만 뽑는다.

    화면 줄이 "브랜드 상품명 — $38.00" 이라 상품명과 같은 자리에서 나온다.
    DOM 을 다시 읽지 않는 이유는 **화면이 진실**이기 때문이다 — 담긴 값과
    모델이 본 값이 다르면 판단 근거를 맞춰볼 수 없다.
    """
    parts = user.split(NL + NL)
    if len(parts) < 2 or " — " not in parts[1]:
        return None
    try:
        raw = parts[1].split(" — ")[-1].strip().replace(",", "")
        if raw.endswith("원"):                       # 09-09 한국어화 뒤 화면은 원화다
            return float(raw[:-1]) / KRW_PER_USD     # 내부 비교는 달러(이력·예산과 같은 단위)
        return float(raw.lstrip("$"))
    except ValueError:
        return None


class DecisionLog:
    """LLM 의 판단 근거를 별도 파일로 남긴다.

    왜 이벤트에 안 넣는가 — 이벤트는 계약(36종)이고 property 도 계약이 정한 것만
    쓴다. `reason` 은 거기에 없다. 그렇다고 콘솔에만 찍으면 실행이 끝나는 순간
    사라진다 (8/31 GMS 100명 실행의 근거 문장이 그렇게 사라졌다).

    이벤트 로그와는 `persona_id` + `simulation_run_id` + 시각으로 붙는다.
    정성 검증 축의 근거이고, 발표에서 실제 문장을 인용할 때 쓴다.
    """

    def __init__(self, path, run_id, model):
        self.path = path
        self.run_id = run_id
        self.model = model
        self.n = 0
        self.f = None
        if path:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            self.f = open(path, "w", encoding="utf-8", newline="\n")

    def write(self, persona_id, turn, screen, allowed, obj, act, tgt, ok):
        if self.f is None:
            return
        self.f.write(json.dumps({
            "simulation_run_id": self.run_id,
            "model": self.model,
            "persona_id": persona_id,
            "turn": turn,
            "decided_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds")
                          .replace("+00:00", "Z"),
            "screen": screen,
            "allowed": allowed,
            # 모델이 뭐라고 했는가
            "llm_action": (obj or {}).get("action"),
            "llm_target": (obj or {}).get("target"),
            "reason": (obj or {}).get("reason"),
            # 코드가 무엇으로 바꿨는가. 둘이 다르면 교정된 턴이다
            "action": act,
            "target": tgt,
            "corrected": bool(obj) and (obj.get("action") != act),
            "succeeded": bool(ok),
        }, ensure_ascii=False) + "\n")
        self.n += 1

    def close(self):
        if self.f is not None:
            self.f.close()


def run_one(page, client, persona, max_turns, cache_on, dry, verbose, script=None,
            decisions=None):
    global CURRENT_PREF
    CURRENT_PREF = tuple(preferred_categories(persona)[:3])
    if PREFER_FILTER:
        category_rule = ("\n- 목록에는 내가 쓰는 종류의 상품이 먼저 눈에 들어온다. "
                         "그 안에서 고르십시오.")
    elif PREFER_STRICT:
        category_rule = ("\n- **★ 표시가 없는 상품은 고르지 마십시오.** ★ 는 내가 주로 사 온 종류다. "
                         "화면에 ★ 상품이 하나도 없을 때만 다른 종류를 고르거나 scroll 하십시오. "
                         "reason 에 종류를 적으십시오.")
    elif PREFER_CATEGORY:
        category_rule = ("\n- **내가 주로 사 온 종류의 상품을 먼저 보십시오.** 다른 종류는 지금 "
                         "필요해서 살 이유가 있을 때만 고르십시오.")
    else:
        category_rule = ""
    system = SYSTEM_TMPL.format(profile=profile_text(persona), category_rule=category_rule,
                                actions=" | ".join(f'"{a}"' for a in ACTIONS))
    calls, done, failed, carted, purchased, banner_clicks = 0, 0, 0, 0, 0, 0
    reviewed = 0
    sorted_once = False      # 목록 정렬은 세션당 한 번 (Jira 321)

    history = []          # 최근 행동. 없으면 LLM 이 같은 판단을 무한 반복한다
    visited, cart = [], []   # 이미 본 상품 / 담은 상품
    last_detail = None       # (주소, 상품명) — 주문 뒤 피드백을 남기러 돌아갈 곳
    feedback_done = set()    # 의견을 남긴 상품. 같은 상품·같은 축은 백엔드가 409 로 막는다
    cart_prices = {}         # 담은 상품의 화면 가격. 부담 판단에 쓴다
    budget = budget_of(persona)   # 이 사람이 실제로 내 본 최고가
    # 내려보는 폭의 사람별 중심값. **전용 스트림에서 뽑는다** — 기본 스트림을
    # 소비하면 이 값을 넣은 것만으로 이후 궤적이 통째로 달라져 A/B 가 깨진다
    scroll_center = random.Random(persona["persona_id"] + "|scroll").randint(
        SCROLL_CENTER_MIN, SCROLL_CENTER_MAX)
    wished = set()           # 찜한 상품. 상품당 한 번만 열어준다
    peeked = []              # 요약만 열어본 상품. 같은 카드를 다시 열지 않게 한다
    quick_looks = 0          # 요약 열어본 횟수. 상한을 넘으면 상세로 가야 한다
    feedbacks = 0            # 산 뒤에 남긴 의견 수
    feedback_failed = 0      # 시도했는데 못 남긴 횟수. 0건이 조용히 지나가지 않게 센다 (Jira 367)
    scroll_run = 0           # 연속 스크롤 횟수. 상세에서 결정을 강제하는 데 쓴다
    here = ""                # 지금 상세를 보고 있는 상품
    broken = 0
    for turn in range(1, max_turns + 1):
        if screen_is_broken(page):
            # 화면이 죽었다. 목록으로 되돌리고 이 턴은 LLM 을 부르지 않는다
            broken += 1
            if verbose:
                print(f"    {turn:>2}. (화면이 비어 목록으로 복구)")
            if not recover_screen(page) or broken > 3:
                break
            continue
        user, kind = read_screen(page, visited)
        m = re.search(PCT_RE, user)
        pct = int(m.group(1)) if m else 0
        if kind == "detail":
            here = detail_title(user) or here
            # 무엇을 봤는지는 LLM 이 말한 target 이 아니라 화면이 진실이다.
            # target 을 틀리게 쓰거나 빠뜨리면 중복 방지가 통째로 무력해진다
            if here and here not in visited:
                visited.append(here)
            if here:
                last_detail = (page.url, here)   # 주문 뒤 돌아갈 상세
        # 이미 담은 상품을 또 담게 두면 같은 전환이 중복으로 쌓인다
        carted_here = any(norm(c) and (norm(c) in norm(here) or norm(here) in norm(c))
                          for c in cart)
        has_more = kind == "list" and page.locator(".list__more").count() > 0
        wished_here = any(norm(w) and (norm(w) in norm(here) or norm(here) in norm(w))
                          for w in wished)
        has_unvisited = kind != "list" or has_unvisited_in_list(page, visited)
        acts = allowed_actions(kind, pct, scroll_run, carted_here, has_more,
                               wished_here=wished_here, quick_looks=quick_looks,
                               cart_size=len(cart), n_details=len(visited),
                               has_unvisited=has_unvisited,
                               cart_over=any(
                                   budget is not None and v > budget
                                   for v in cart_prices.values()),
                               sorted_once=sorted_once,
                               has_banner=(kind == "list" and bool(read_banner(page))),
                               feedback_here=any(
                                   norm(f) and (norm(f) in norm(here) or norm(here) in norm(f))
                                   for f in feedback_done))
        user = (f"[이번 턴에 고를 수 있는 행동] {' | '.join(acts)}"
                f"{NL}이 중에서만 고르십시오." + NL + NL + user)
        if kind == "detail" and "scroll" not in acts:
            user = ("[결정하십시오] 이 상품을 충분히 봤습니다."
                    " 마음에 들면 add_to_cart, 아니면 back_to_list 입니다."
                    + NL + NL + user)
        # 본 상품과 담은 상품을 알려주지 않으면 같은 상품만 25턴 내내 반복한다.
        # (실제로 한 페르소나가 BELIF 두 개만 왕복한 사고가 있었다)
        if visited:
            user = (f"[이미 본 상품] {', '.join(visited[-8:])}"
                    f"{NL}이미 본 상품은 다시 누르지 말고 다른 상품을 고르십시오."
                    + NL + NL + user)
        if peeked:
            user = (f"[요약만 열어본 상품] {', '.join(peeked[-6:])}{NL}"
                    f"같은 상품을 또 열지 말고, 관심이 남았으면 상세로 들어가십시오."
                    f"{NL}{NL}") + user
        if wished:
            user = (f"[찜한 상품] {', '.join(sorted(wished))}{NL}"
                    f"이미 찜한 상품을 다시 누르면 찜이 해제됩니다.{NL}{NL}") + user
        if cart:
            # **화면에 답을 적어 준다.** "가격이 부담스러우면 빼십시오" 라고
            # 말만 해서는 모델이 못 한다 — 9/3 에 [이미 봄] 표시로 재진입을
            # 12.2% -> 1.1% 로 줄인 것과 같은 방식이다. 합계와 개인 상한을
            # 나란히 두고, 넘는 품목에는 표시를 붙인다
            items = []
            for c in cart:
                pr = cart_prices.get(c)
                over = budget is not None and pr is not None and pr > budget
                items.append(f"{c}" + (f" {won(pr)}" if pr is not None else "")
                             + (f"  (익숙한 가격대 {won(budget)} 위)" if over else ""))
            total = sum(v for v in cart_prices.values())
            tail = ""
            if total:
                tail = f" — 합계 {won(total)}"
                if budget is not None:
                    tail += f" (익숙한 가격대는 한 개에 {won(budget)} 아래다)"
            user = (f"[장바구니] {', '.join(items)}{tail}{NL}{NL}") + user
        if history:
            recent = NL.join(f"  {i}. {h}" for i, h in
                             enumerate(history[-6:], max(1, len(history) - 5)))
            user = f"[지금까지 한 행동]{NL}{recent}{NL}{NL}{user}"
            # 연속으로 스크롤만 하고 있으면 대놓고 지적한다
            if len(history) >= 3 and all(h.startswith("scroll") for h in history[-3:]):
                user = ("[주의] 스크롤을 세 번 연속 했습니다. **이번에는 상품을 하나 고르거나"
                        " 목록 끝이면 leave 하십시오.**" + NL + NL + user)
        if verbose and DEBUG_SCREEN:
            print(f"       [화면 {kind} · 스크롤 {pct}% · 상세 {len(visited)}개"
                  f" · 새 상품 {'있음' if has_unvisited else '없음'}"
                  f" · 선택지 {'/'.join(acts)}]")
        if script is not None:
            obj, used = script.next_action(page, acts, here, cart, visited, peeked), 0
        elif isinstance(client, LocalLLM):
            obj, used = parse_action(client.chat(system, user)), 0
        else:
            obj, used = ask(client, system, user, cache_on, dry)
        calls += used
        if obj is None:
            failed += 1
            if verbose:
                print(f"    {turn:>2}. (응답 형식 깨짐 — 건너뜀)")
            continue
        act, tgt = obj["action"], obj.get("target")
        if act not in acts:
            # 크레딧을 또 쓰지 않는다. 이번 턴은 허용된 첫 행동으로 대체한다.
            # 다만 click_product 로 교정할 때 target 을 그대로 두면,
            # LLM 이 지어낸 이름이 매칭에 실패해 엉뚱한 상품이 눌릴 수 있다.
            # 그 사람이 고른 적 없는 클릭이 로그에 남는 것은 수집 목적에 반한다
            new_act = acts[0]
            if new_act == "click_product":
                tgt = first_unvisited(page, visited)
                if tgt is None:                  # 누를 만한 새 상품이 없다
                    new_act = "leave" if "leave" in acts else acts[-1]
            elif new_act in ("add_to_cart", "wishlist_toggle", "buy_now"):
                tgt = here or tgt                # 화면이 진실이다
            elif new_act == "remove_from_cart":
                tgt = cart[-1] if cart else None
            elif new_act == "sort_list":
                tgt = random.choice(list(SORT_KEYS))   # 보정 폴백도 한쪽으로 쏠리지 않게 (Jira 326)
            elif new_act == "click_banner":
                tgt = None
            else:
                tgt = None
            if verbose:
                print(f"       [허용 밖 {act} -> {new_act}]")
            act = new_act
            if act == "leave":
                if verbose:
                    print(f"    {turn:>2}. leave (목록에 새 상품 없음)")
                break

        if act == "leave":
            if verbose:
                print(f"    {turn:>2}. leave — {obj.get('reason')}")
            break

        try:
            okd = do_action(page, act, tgt, scroll_center)
        except Exception as e:            # 셀렉터가 바뀌었거나 화면이 예상 밖일 때
            okd = False
            if verbose:
                print(f"       [조작 실패] {type(e).__name__}: {str(e)[:70]}")
        if act == "write_feedback":
            # do_action 은 DOM 조작만 한다. 의견은 글을 쓰려고 LLM 을 한 번 더 부르므로 여기서 처리한다.
            # **집계(done/failed)와 history 보다 앞이어야 한다** — 뒤에 두면 성공해도 실패로 세고
            # 다음 턴 프롬프트가 "(실패)" 라는 틀린 사실을 본다.
            got, why = None, "LLM 클라이언트 없음"
            if client:
                try:
                    got, why = write_feedback(page, client, persona, here or "이 제품", cache_on, dry)
                except Exception as e:
                    got, why = None, "예외 %s" % type(e).__name__
            okd = bool(got)
            if not okd:
                feedback_failed += 1
                if verbose:
                    print(f"       [의견 못 남김] {why}")
            if okd:
                calls += 1
                feedbacks += 1
                feedback_done.add(here)
                if verbose:
                    print(f"        의견 [{got[0]}] {got[1][:46]}")
        scroll_run = scroll_run + 1 if act == "scroll" else 0
        history.append(f"{act}" + (f" → {tgt}" if tgt else "")
                       + ("" if okd else "  (실패)"))
        if okd and act == "add_to_cart":
            # 담은 것도 화면 기준. here 는 지금 보고 있는 상세 페이지의 상품이다
            nm = here or (" ".join(str(tgt).split()[:4]) if tgt else "")
            if nm and nm not in cart:
                cart.append(nm)
                pr = detail_price(user)
                if pr is not None:
                    cart_prices[nm] = pr
        if okd and act == "wishlist_toggle":
            # 같은 상품을 다시 누르면 해제다. 상태를 뒤집어 둬야 프롬프트가 맞는다
            nm = here or (str(tgt) if tgt else "")
            if nm:
                wished.discard(nm) if nm in wished else wished.add(nm)
        if okd and act == "quick_look":
            quick_looks += 1
            if tgt and tgt not in peeked:
                peeked.append(str(tgt))
        if okd and act == "remove_from_cart":
            gone = str(tgt) if tgt else (cart[-1] if cart else None)
            if gone in cart:
                cart.remove(gone)
                cart_prices.pop(gone, None)
        if okd and act == "sort_list":
            sorted_once = True
        done += okd
        failed += (not okd)
        if okd and act == "add_to_cart":
            carted += 1
        if okd and act in ("checkout", "buy_now"):
            purchased += 1
        if okd and act == "click_banner":
            banner_clicks += 1
        if decisions is not None:
            decisions.write(persona["persona_id"], turn, kind, acts, obj, act, tgt, okd)
        if verbose:
            mark = "  " if okd else "! "
            print(f"    {turn:>2}.{mark}{act:<14} {str(tgt)[:30]:<32} {(obj.get('reason') or '')[:40]}")
        if okd and act in ("checkout", "buy_now"):
            if verbose:
                print(f"    {turn:>2}. {act} 완료 — 주문. 오늘 쇼핑 끝")
            # ── 산 뒤에 의견 남기기 ────────────────────────────────────────
            # 피드백은 산 사람만 쓸 수 있는데(FeedbackController.purchased) 주문하면 세션이
            # 끝난다. 그래서 행동이 아니라 주문 직후 단계로 둔다. 글은 **미리 써 둔 것을
            # 고르지 않고 LLM 이 그 자리에서 쓴다** — 그 사람이 실제로 산 상품과 피부 타입이
            # 글에 묻어나야 판매자 화면이 값어치가 있다 (사용자 결정 09-17).
            if client and last_detail and random.random() < FEEDBACK_AFTER_ORDER_P:
                url, name = last_detail
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=15000)
                    page.wait_for_timeout(random.randint(600, 1800))
                    got, why = write_feedback(page, client, persona, name, cache_on, dry)
                except Exception as e:
                    got, why = None, "예외 %s" % type(e).__name__
                if got:
                    calls += 1
                    feedbacks += 1
                    if verbose:
                        print(f"        의견 남김 [{got[0]}] {got[1][:40]}")
                else:
                    feedback_failed += 1
                    if verbose:
                        print(f"        의견 못 남김 — {why}")
            # ── 산 뒤에 리뷰 쓰기 ──────────────────────────────────────────
            # 리뷰도 **행동이 아니라 주문 직후 단계**다. 행동으로 두면 절대 실행되지 않는다 —
            # 선택지에 오르는 조건이 `purchased >= 1` 인데 주문하면 바로 아래에서 break 로
            # 세션이 끝나서 그런 턴이 존재하지 않는다. 실측 125턴 중 0회 (Jira 360).
            # 화면 구조와도 이게 맞다 — 리뷰 칸은 주문 뒤 마이페이지 모달 안에 있다.
            if client and random.random() < REVIEW_AFTER_ORDER_P:
                try:
                    got = write_review(page, client, persona, cache_on, dry)
                except Exception:
                    got = None
                if got:
                    calls += 1
                    reviewed += 1
                    if verbose:
                        print(f"        리뷰 남김 [{got[0][:24]}] {got[1]}점 {got[2][:32]}")
            cart.clear()
            break                                # 주문하면 세션이 끝난다 (프롬프트와 같은 약속)
        if dry:
            break                                # 프롬프트 확인용이므로 한 턴만
    return dict(calls=calls, done=done, failed=failed, carted=carted, purchased=purchased,
                feedbacks=feedbacks, feedback_failed=feedback_failed,
                banner_clicks=banner_clicks, broken=broken, reviewed=reviewed)


# ============================================================================
# 6. 메인
# ============================================================================


def run_parallel(a):
    """자기 자신을 --shard 로 여러 번 띄우고 로그를 합친다.

    Playwright 의 sync API 가 스레드 안전하지 않아 스레드가 아니라 프로세스로
    나눈다. 한 워커가 죽어도 나머지는 계속 돈다.
    """
    import subprocess
    n = min(a.workers, a.limit)
    base, ext = os.path.splitext(a.out)
    parts = [f"{base}.part{i}{ext}" for i in range(n)]
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)

    # **실행 ID 를 부모가 정해 모든 샤드에 물려준다.** 샤드마다 만들면 한 번의
    # 실행이 워커 수만큼의 simulation_run_id 로 쪼개져 실행 단위 집계가 깨진다
    run_id = a.simulation_run_id or default_simulation_run_id()

    argv = [sys.executable, os.path.abspath(__file__),
            "--url", a.url, "--limit", str(a.limit), "--turns", str(a.turns),
            "--model", MODEL,
            "--scenario-id", a.scenario_id, "--simulation-run-id", run_id,
            "--entry", a.entry]
    for flag, on in (("--headed", a.headed), ("--dry-run", a.dry_run),
                     ("--openai", a.openai), ("--cache", a.cache),
                     ("--debug-screen", a.debug_screen)):
        if on:
            argv.append(flag)
    if a.api_base:                  # 자체 모델 서버 주소도 워커에 물려준다
        argv += ["--api-base", a.api_base]
    if a.decisions and a.decisions.lower() == "off":
        argv += ["--decisions", "off"]   # 경로는 샤드별 --out 에서 유도된다
    if a.post:                      # 안 넘기면 워커가 파일로만 쓰고 수집이 안 된다
        argv += ["--post", a.post, "--post-timeout", str(a.post_timeout)]
    if a.script:
        argv += ["--script", a.script]
    if a.product:
        argv += ["--product", a.product]
    if a.min_details is not None:
        argv += ["--min-details", str(a.min_details)]
    if a.checkout:
        argv.append("--checkout")
    if not a.banner:
        argv.append("--no-banner")

    print(f"워커 {n}개로 나눠 실행합니다 (Playwright sync API 가 스레드 안전하지"
          f" 않아 프로세스로 분리)")
    print(f"  실행 ID {run_id} — 모든 워커가 같은 값을 씁니다")
    t0 = time.time()
    procs = []
    for i in range(n):
        cmd = argv + ["--shard", str(i), "--shards", str(n),
                      "--out", parts[i], "--quiet"]
        procs.append(subprocess.Popen(cmd))
    codes = [p.wait() for p in procs]
    dead = [i for i, c in enumerate(codes) if c != 0]

    # 로그 합치기 — 워커마다 따로 쓴 파일을 하나로 잇는다
    total = 0
    with io.open(a.out, "w", encoding="utf-8") as out:
        for p in parts:
            if not os.path.exists(p):
                continue
            with io.open(p, encoding="utf-8") as f:
                for line in f:
                    out.write(line)
                    total += 1
            os.remove(p)

    # 판단 근거도 합친다 — 워커마다 --out 옆에 따로 쓴다. 안 합치면 12개로 흩어진다
    dec_total = 0
    if not (a.decisions and a.decisions.lower() == "off"):
        dbase, dext = os.path.splitext(a.out)
        dec_out = f"{dbase}_decisions{dext}"
        with io.open(dec_out, "w", encoding="utf-8") as out:
            for p in parts:
                pb, pe = os.path.splitext(p)
                dp = f"{pb}_decisions{pe}"
                if not os.path.exists(dp):
                    continue
                with io.open(dp, encoding="utf-8") as f:
                    for line in f:
                        out.write(line)
                        dec_total += 1
                os.remove(dp)

    dt = time.time() - t0
    print()
    print("=" * 60)
    print(f"  워커 {n}개 · {dt:.0f}초 ({dt/60:.1f}분)")
    if dead:
        print(f"  실패한 워커 {len(dead)}개: {dead}  <- 그만큼 페르소나가 빠졌습니다")
    print(f"  수집 로그 {total:,}건 -> {a.out}")
    if dec_total:
        print(f"  판단 근거 {dec_total:,}건 -> {dec_out}")
    print("=" * 60)


def main():
    global MODEL
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:5173", help="프론트 주소")
    ap.add_argument("--limit", type=int, default=3, help="돌릴 페르소나 수")
    ap.add_argument("--turns", type=int, default=25, help="1인당 최대 턴")
    ap.add_argument("--headed", action="store_true", help="브라우저를 띄워서 본다")
    ap.add_argument("--dry-run", action="store_true", help="LLM 호출 없이 프롬프트만 (0 크레딧)")
    ap.add_argument("--cache", action="store_true", help="같은 화면이면 저장된 응답 재사용")
    ap.add_argument("--local-model", default=None, metavar="HF_ID",
                    help="로컬 GPU 의 오픈 모델을 쓴다 (크레딧 0). "
                         "예) HuggingFaceTB/SmolLM2-1.7B-Instruct")
    ap.add_argument("--decisions",
                    help="LLM 판단 근거를 남길 jsonl 경로. 안 주면 --out 옆에"
                         " *_decisions.jsonl 로 만든다. 'off' 면 남기지 않는다")
    ap.add_argument("--api-base",
                    help="OpenAI 호환 자체 모델 서버 주소. 예) http://70.12.130.103:8501/v1"
                         " (GPU 서버에 model_server.py 를 띄워 두고 쓴다. 크레딧 0)")
    ap.add_argument("--openai", action="store_true",
                    help="GMS 대신 개인 OpenAI 키를 쓴다 (OPENAI_API_KEY 환경변수)")
    ap.add_argument("--model", default=None, help=f"모델 (기본 {MODEL})")
    ap.add_argument("--out", default=os.path.join(BD, "data", "agent_events.jsonl"),
                    help="가로챈 행동 로그를 적을 파일")
    ap.add_argument("--workers", type=int, default=1,
                    help="동시에 돌릴 프로세스 수. LLM 대기가 병목이라 그대로 빨라진다")
    ap.add_argument("--shard", type=int, default=0, help=argparse.SUPPRESS)
    ap.add_argument("--shards", type=int, default=1, help=argparse.SUPPRESS)
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--prefer-category", action="store_true",
                    help="실험: 프로필·목록에 상품 종류를 적고 내 종류를 먼저 보게 한다")
    ap.add_argument("--prefer-strict", action="store_true",
                    help="실험: 내 종류를 ★ 로 표시하고 ★ 아닌 상품은 고르지 못하게 한다 (--prefer-category 포함)")
    ap.add_argument("--prefer-filter", action="store_true",
                    help="종류 필터를 코드로 강제 — 목록에 내 종류 카드가 보이면 그것만 보여 준다 (Jira 241)")
    ap.add_argument("--debug-screen", action="store_true",
                    help="매 턴 화면 판정과 선택지를 찍는다 (행동이 왜 열렸는지 볼 때)")
    ap.add_argument("--product", default=None, metavar="PRODUCT_ID",
                    help="전원이 이 상품 상세에서 시작한다 (재구매 시연용, Jira 362). 예) SB000001")
    ap.add_argument("--min-details", type=int, default=None, metavar="N",
                    help="구매·이탈이 열리는 상세 조회 수 문턱 (기본 3). --product 로 상품을 "
                         "못박고 바로 사게 할 때 1 로 낮춘다 — 시연 데이터 생성 전용 (Jira 362)")
    ap.add_argument("--entry", choices=("auto", "list", "detail"), default="auto",
                    help="시작 화면을 고정한다. 기본 auto 는 페르소나마다 무작위 "
                         "(리허설에서 특정 동선을 재현할 때 쓴다)")
    ap.add_argument("--no-banner", dest="banner", action="store_false", default=True,
                    help="에이전트가 배너를 못 보게 한다 (노출 A/B 대조군, Jira 321). 배너 노출 로그는 프론트가 그대로 남긴다")
    ap.add_argument("--checkout", action="store_true",
                    help="PA 회원으로 로그인하고 checkout(주문) 행동을 연다 (Jira 321). 결제 키 없는 프론트 전제")
    ap.add_argument("--script", default=None,
                    help="LLM 대신 정해진 행동 순서를 실행한다 (크레딧 0). "
                         "예) click_product,wishlist_toggle,add_to_cart,back_to_list")
    ap.add_argument("--scenario-id", default=DEFAULT_SCENARIO_ID,
                    help=f"synthetic 시나리오 ID (기본 {DEFAULT_SCENARIO_ID})")
    ap.add_argument("--simulation-run-id", default=None,
                    help="이번 실행 ID. 안 주면 시각으로 만든다")
    ap.add_argument("--post", default=None, metavar="URL",
                    help="수집 API 베이스 URL. 예) http://localhost:8080"
                         " (안 주면 파일로만 남긴다)")
    ap.add_argument("--post-timeout", type=int, default=40,
                    help="수집 API 응답 대기 초. Kafka 가 없으면 25초쯤 뒤 503 이 온다")
    a = ap.parse_args()
    global CHECKOUT_ENABLED, BANNER_VISIBLE, MIN_DETAILS_BEFORE_LEAVE
    CHECKOUT_ENABLED = bool(a.checkout)
    BANNER_VISIBLE = bool(a.banner)
    if a.min_details is not None:
        # 문턱은 모듈 전역이라 여기서 갈아 끼운다. 평가용 실행에서는 쓰지 않는다 —
        # "사람은 몇 개는 보고 산다" 는 전제가 깨진다
        MIN_DETAILS_BEFORE_LEAVE = a.min_details
    global PREFER_CATEGORY, PREFER_STRICT, PREFER_FILTER
    PREFER_FILTER = a.prefer_filter
    PREFER_STRICT = a.prefer_strict
    PREFER_CATEGORY = a.prefer_category or a.prefer_strict or a.prefer_filter
    # dry-run · 스크립트 모드가 기본 경로에 쓰면 진짜 실행 파일을 덮어쓴다 —
    # 2026-09-08 에 --dry-run --limit 1 이 09-07 100명 본실행 33,217건을 지웠다
    if (a.dry_run or a.script) and a.out == ap.get_default("out"):
        a.out = os.path.join(BD, "data", "agent_events_dryrun.jsonl")

    simulation_run_id = a.simulation_run_id or default_simulation_run_id()
    start_url = entry_url(a.url, a.scenario_id, simulation_run_id)
    # 상세로 딥링크한 사람이 목록으로 돌아갈 때 쓸 주소 (product 파라미터 없음)
    globals()["LIST_URL"] = start_url

    if a.model:
        MODEL = a.model
    if a.debug_screen:
        globals()["DEBUG_SCREEN"] = True

    load_dotenv()

    client = None
    if a.local_model and not a.dry_run and not a.script:
        client = LocalLLM(a.local_model)
    elif a.api_base and not a.dry_run and not a.script:
        # 자체 모델 서버 (model_server.py). GPU 서버에 모델을 올려 두고 여기서는
        # 브라우저만 돌린다 — 노트북 VRAM 이 8GB 라 3B 가 한계인데, 서버가 32GB 면
        # 7B 이상을 쓸 수 있고 노트북 GPU 가 비어 워커도 늘릴 수 있다.
        # 키는 검사하지 않는 서버라 자리만 채운다.
        from openai import OpenAI
        client = OpenAI(base_url=a.api_base, api_key="not-used")
        print(f"모델 서버 {a.api_base} · 모델 {MODEL}")
    elif not a.dry_run and not a.script:
        from openai import OpenAI
        if a.openai:
            key = os.environ.get("OPENAI_API_KEY")
            if not key:
                print("OPENAI_API_KEY 가 없습니다. 레포 루트 .env 에 넣거나 환경변수로 주십시오.")
                raise SystemExit(1)
            client = OpenAI(api_key=key)          # 기본 엔드포인트 = api.openai.com
        else:
            key = os.environ.get("GMS_KEY")
            if not key:
                print("GMS_KEY 가 없습니다. 레포 루트 .env 에 'GMS_KEY=...' 를 넣으십시오.")
                raise SystemExit(1)
            client = OpenAI(base_url=GMS_BASE, api_key=key)

    if a.workers > 1 and a.shards == 1:
        run_parallel(a)
        return

    personas = json.load(open(PERSONA_FILE, encoding="utf-8"))[:a.limit]
    catalog = load_catalog()
    if not catalog:
        print(f"상품 목록을 못 읽었습니다 ({PRODUCTS_FILE}) — 전원 목록에서 시작합니다")
    print("PA(LLM 에이전트) — 정성 검증 축입니다. 대표 정량 지표(PC 9,900명)에"
          " 합치지 마십시오 (docs/ai/evaluation-framework.md 5절)")
    if a.shards > 1:
        # 앞에서부터 순서대로 나누지 않고 건너뛰며 나눈다. 페르소나 파일이
        # 정렬돼 있으면 앞쪽 샤드에만 무거운 사람이 몰릴 수 있다
        personas = personas[a.shard::a.shards]
    print(f"페르소나 {len(personas)}명 · 모델 {MODEL} · 최대 {a.turns}턴"
          + ("  [dry-run]" if a.dry_run else ""))
    print(f"프론트 {start_url}")
    print(f"실행 메타데이터 actor_type=synthetic generator_type={GENERATOR_TYPE} "
          f"scenario_id={a.scenario_id} simulation_run_id={simulation_run_id}")
    print(f"수집 API {a.post}" if a.post else "수집 API 전송 없음 (파일로만 남김)")

    dec_path = a.decisions
    if dec_path is None:
        base, ext = os.path.splitext(a.out)
        dec_path = f"{base}_decisions{ext}"
    elif dec_path.lower() == "off":
        dec_path = None
    decisions = DecisionLog(dec_path, simulation_run_id, MODEL)
    if dec_path:
        print(f"판단 근거 {dec_path}")

    from playwright.sync_api import sync_playwright
    # run_one 이 돌려주는 key 는 전부 여기 있어야 한다 — 없으면 아래 합산 루프가 조용히 버린다.
    # feedbacks 가 빠져 있어서 "의견 0건" 이 요약에 한 번도 안 찍혔다 (Jira 367)
    tot = dict(calls=0, done=0, failed=0, carted=0, purchased=0, banner_clicks=0, broken=0,
               reviewed=0, feedbacks=0, feedback_failed=0)
    t0 = time.time()

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    sink = LogSink(a.out, a.scenario_id, simulation_run_id,
                   post_base=a.post, timeout=a.post_timeout)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not a.headed)
        for p in personas:
            ctx = browser.new_context()          # 페르소나마다 새 세션
            # 게이트가 비어 있는 동안의 이벤트는 버린다. 페르소나를 고른 뒤
            # 채운다 (LogSink._gate 주석 참고)
            gate = {"persona_id": None}
            sink.attach(ctx, gate)               # 백엔드 없이도 로그를 건진다
            page = ctx.new_page()

            # 출발 지점은 페르소나마다 다르되 **같은 사람은 늘 같은 곳**에서
            # 시작한다. 실행마다 달라지면 커버리지 변화가 코드 때문인지
            # 운 때문인지 구분할 수 없다
            rng = random.Random(p["persona_id"])
            deep = catalog and rng.random() < DEEP_LINK_P
            if a.entry != "auto":
                deep = a.entry == "detail"
            # --product 로 상품을 못박으면 전원이 그 상세에서 시작한다. 재구매 시연에 쓴다 —
            # 재구매 마트 key 에 simulation_run_id 가 있어(dw-schema §4.15) 같은 run_id 로 두 번
            # 돌려야 한 사람의 두 구매가 묶이는데, 어떤 상품을 살지는 LLM 이 정해서 같은 상품을
            # 두 번 사게 만들 방법이 없었다 (Jira 362).
            pinned = a.product or None
            entry = entry_url(a.url, a.scenario_id, simulation_run_id,
                              product_id=pinned or (rng.choice(catalog) if deep else None))

            page.goto(entry, wait_until="networkidle")

            # 딥링크로 들어간 상세가 렌더되지 않으면 목록으로 되돌린다.
            # AboutProduct.tsx 크래시는 2026-09-02 고쳐졌다. 이 방어는 이제
            # 대부분 놀지만, 놀고 있다는 것 자체가 확인이라 남긴다
            if (deep or pinned) and not page.locator('[data-log-action="add_to_cart"]').count():
                print(f"  {p['persona_id']}  상세가 렌더되지 않아 목록에서 시작합니다")
                page.goto(LIST_URL, wait_until="networkidle")
                page.wait_for_timeout(800)

            # **페르소나 전환은 마지막 화면 이동 뒤여야 한다.** App.tsx 가
            # `useState(personas[0])` 로 들고 있어 페이지를 새로 열면 선택이
            # PA00001 로 돌아간다. 전환을 앞으로 옮겼더니 goto 가 되돌려
            # 다른 사람 로그가 통째로 사라졌다.
            #
            # 그래서 전환 **전** 화면의 이벤트는 게이트로 버린다. 그게 44%를
            # PA00001 에 쌓이게 하던 것이다 (2026-09-03 규명).
            #
            # 근본 수정으로 제안했던 `?persona=` 는 프론트가 받아들였다
            # (dev `10dd3b3`, Research/handoff/frontend-persona-url-param.md).
            # 러너는 아직 화면을 먼저 열고 고르는 순서라 게이트를 그대로 둔다 —
            # 게이트는 배치 전송으로 섞여 오는 남의 이벤트도 같이 막는다.
            # 러너가 `?persona=` 로 바로 들어가게 바꾸는 것은 별건이다.
            # --checkout 이면 회원 로그인이 신원이다. 로그인이 안 되면 스위처로 물러나되 주문은 못 한다
            logged_in = CHECKOUT_ENABLED and login_member(page, p["persona_id"])
            if CHECKOUT_ENABLED and not logged_in:
                print(f"  {p['persona_id']}  회원 로그인 실패 — 스위처로 진행 (주문은 서버가 막는다)")
            if not logged_in and not switch_persona(page, p["persona_id"]):
                print(f"  {p['persona_id']}  페르소나 전환 실패 — 건너뜀")
                ctx.close()
                continue
            gate["persona_id"] = p["persona_id"]   # 여기부터 이 사람의 로그다

            spread_start(page, rng, preferred_categories(p))   # 자기가 쓰던 카테고리부터

            print(f"  {p['persona_id']}  {TYPE_KR.get(p['skin_type'], '')}/"
                  f"{p['skin_tone']}  구매 {p['n_products']}개")
            script = ScriptedLLM(a.script.split(",")) if a.script else None
            r = run_one(page, client, p, a.turns, a.cache, a.dry_run, not a.quiet,
                        decisions=decisions,
                        script=script)
            for k in tot:
                tot[k] += r[k]
            drain_logs(page, sink)
            ctx.close()
        browser.close()
    sink.close()

    dt = time.time() - t0
    print()
    print("=" * 60)
    print(f"  실행 {tot['done']}건 / 실패 {tot['failed']}건 / 장바구니 {tot['carted']}건 / 주문 {tot['purchased']}건"
          f" / 배너 클릭 {tot['banner_clicks']}건 / 리뷰 {tot['reviewed']}건 / 의견 {tot['feedbacks']}건")
    if tot.get("feedback_failed"):
        print(f"  ⚠ 의견을 못 남긴 시도 {tot['feedback_failed']}회 — 이유는 --verbose 로 보입니다")
    if tot.get("broken"):
        print(f"  ⚠ 화면이 비어 복구한 횟수 {tot['broken']}회"
              f" — AboutProduct.tsx 크래시는 2026-09-02 고쳐졌으므로 다른 원인입니다")
    print(f"  LLM 호출 {tot['calls']}회 · {dt:.0f}초")
    if tot["calls"] and not a.local_model and not a.api_base:
        print(f"  예상 크레딧 약 {tot['calls'] * 0.6:.0f}"
              f"  (100명 환산 {tot['calls'] * 0.6 / max(len(personas),1) * 100:,.0f})")
    top = sorted(sink.kinds.items(), key=lambda x: -x[1])[:8]
    print(f"  수집 로그 {sink.n}건 -> {a.out}")
    if decisions.n:
        print(f"  판단 근거 {decisions.n}건 -> {decisions.path}"
              f"  (교정된 턴 포함. 이벤트와는 persona_id+simulation_run_id 로 붙는다)")
    decisions.close()
    if top:
        print("  " + " · ".join(f"{k} {v}" for k, v in top))

    # 표시가 어디서 붙었는지. 프론트가 스스로 붙이기 시작하면 stamped 가 0 이 된다
    print(f"  actor_type=synthetic  {sink.n}건 "
          f"(러너가 채움 {sink.stamped} · 봉투에 이미 있었음 {sink.already})")
    if sink.dropped:
        print(f"  persona_id 가 없는 이벤트 {sink.dropped}건은 전송 제외 (파일에는 있음)")
    if sink.pre_switch or sink.foreign:
        print(f"  페르소나 전환 전 {sink.pre_switch}건 · 다른 사람 몫 {sink.foreign}건 버림"
              f"  (프론트 기본 페르소나로 찍히던 것. 파일에도 남기지 않는다)")
    if a.post:
        print(f"  수집 API 전송  성공 {sink.sent}건 / 실패 {sink.send_failed}건")
        if sink.send_failed:
            print("    수집 서버와 Kafka 가 떠 있는지 확인하세요. 파일에는 그대로 남아 있습니다.")
    print("=" * 60)


# ============================================================================
# 6. 행동 로그 가로채기
# ============================================================================

LOGGER_TS = os.path.normpath(os.path.join(
    BD, "..", "..", "frontend", "src", "lib", "logger.ts"))
FLUSH_WAIT_MARGIN_MS = 1200


def flush_interval_ms(path=None, default=5000):
    """프론트 로거의 flush 주기를 **logger.ts 에서 직접 읽는다.**

    값을 여기에 복사해 두면 프론트가 주기를 바꿨을 때 조용히 어긋난다 —
    `behavior_weights.py` 가 행동 가중치를 `log.ts` 에서 읽는 것과 같은 이유다.
    파일이 없거나 형식이 바뀌면 기본값으로 돌아간다(더 오래 기다릴 뿐 안전하다).
    """
    try:
        with io.open(path or LOGGER_TS, encoding="utf-8") as f:
            m = re.search(r"FLUSH_INTERVAL_MS\s*=\s*(\d+)", f.read())
        return int(m.group(1)) if m else default
    except OSError:
        return default


def drain_logs(page, sink, extra_ms=FLUSH_WAIT_MARGIN_MS):
    """마지막 턴의 이벤트가 나갈 때까지 기다린다.

    **왜 필요한가 (2026-09-07 규명)**
        프론트 로거는 큐가 BATCH_SIZE(20) 를 넘거나 FLUSH_INTERVAL_MS(5초)
        타이머가 돌 때 배치를 보낸다. 그런데 러너는 1.2초만 기다리고 컨텍스트를
        닫고 있었다. 마지막 턴에서 만든 이벤트는 대개 20건에 못 미쳐 **타이머를
        기다리는 중**이라, 그대로 사라졌다.

        PA 100명 실행에서 잡혔다 — 담기 결정 217건 중 이벤트가 194건이었고,
        **마지막 턴이 담기였던 23명이 정확히 23명 전부** 1건씩 잃었다.
        마지막 턴이 담기가 아닌 77명은 한 건도 안 잃었다 (23/23 대 0/77).

        `logger.ts` 에는 pagehide·visibilitychange 훅이 없어서 컨텍스트를 닫아도
        beacon 이 나가지 않는다. 기다리는 것 말고 방법이 없다.

    **조용해졌다고 끝난 것이 아니다.** 큐에 20건이 안 차면 아무것도 안 오는
    상태로 타이머를 기다린다 — 그래서 "조용하면 종료" 로는 못 짠다.
    주기를 통째로 넘긴 뒤, 그때부터 조용한지를 본다.
    """
    wait = flush_interval_ms() + extra_ms
    before = sink.n
    page.wait_for_timeout(wait)
    # 주기를 넘겼는데도 계속 들어오면(대량 배치가 나뉘어 오는 중) 조금 더 준다
    for _ in range(8):
        last = sink.n
        page.wait_for_timeout(400)
        if sink.n == last:
            break
    return sink.n - before


class LogSink:
    """프론트가 /api/events 로 보내는 행동 로그를 가로채 표시를 채우고 내보낸다.

    두 가지를 한다.

    1. **파일로 남긴다.** 프론트는 sendBeacon/fetch 로 백엔드에 로그를 보내는데,
       백엔드가 안 떠 있으면 그 요청은 그대로 실패하고 **로그가 통째로 사라진다** —
       에이전트를 25턴씩 돌려놓고 아무것도 못 건지는 사고가 여기서 난다.
    2. **synthetic 표시를 채운다.** 에이전트는 실제 브라우저로 조작하므로 프론트
       로거가 실사용자와 똑같이 `actor_type='user'` 로 남긴다. 그대로 두면
       `clean_events_job` 이 `user_id` 를 NULL 로, `source` 를 `web` 으로 파생하고
       시뮬레이션 Mart 에서 통째로 빠진다. 게다가 synthetic 필수 properties 검증은
       `actor_type != 'synthetic'` 이면 그냥 통과시켜서 **거절도 안 되고 조용히
       잘못된 데이터**가 된다. 표시는 여기서 채운다. synthetic 필수값은
       contracts/event-schema.json, PA 보강 책임은
       docs/analytics/log-transport-contract.md §9-2를 따른다.

    `--post` 를 주면 채운 로그를 수집 API 로 대신 보낸다. 헤더에도 같은 사실을
    적어 둔다 (`X-Actor-Type`). 지금은 아무도 안 읽지만, 나중에 수집 서버가
    헤더를 보고 직접 찍는 방식(합성 트래픽의 일반적인 처리)으로 올라가도
    러너를 다시 고칠 필요가 없다.
    """

    def __init__(self, path, scenario_id, simulation_run_id, post_base=None,
                 timeout=40):
        self.path = path
        self.f = io.open(path, "w", encoding="utf-8")
        self.n = 0
        self.kinds = {}
        self.scenario_id = scenario_id
        self.simulation_run_id = simulation_run_id
        self.post_base = post_base.rstrip("/") if post_base else None
        self.timeout = timeout
        # 봉투가 어떤 상태로 들어왔는지. 프론트가 스스로 표시를 붙이게 되면
        # already 가 오르고 stamped 는 0 이 된다 — 그때 이 보정을 걷어내면 된다
        self.already = 0
        self.stamped = 0
        self.sent = 0
        self.send_failed = 0
        self.dropped = 0
        # 페르소나를 고르기 전 화면의 이벤트는 프론트 기본 페르소나(PA00001)로
        # 찍힌다. 세어 두고 버린다 — 아래 _handle 주석에 이유를 적었다
        self.pre_switch = 0
        self.foreign = 0
        self.client = None          # 첫 전송 때 만든다 (백프레셔 상태를 들고 있다)
        self.schema_version = None
        self.queue = None
        self.worker = None
        if self.post_base:
            import queue as _queue
            import threading
            self.queue = _queue.Queue()
            self.worker = threading.Thread(target=self._drain, daemon=True)
            self.worker.start()

    def attach(self, ctx, gate=None):
        """이 컨텍스트의 로그를 가로챈다.

        `gate` 는 `{"persona_id": None}` 인 dict 다. 러너가 페르소나를 고른 뒤
        거기에 이름을 채우고, 그 전에 들어온 이벤트는 버린다. 게이트를 주지
        않으면 예전처럼 전부 받는다 (리허설·스크립트 실행용).
        """
        ctx.route("**/api/events", lambda route, request:
                  self._handle(route, request, gate))

    def _stamp(self, ev):
        """봉투에 synthetic 표시를 채운다. 이미 붙어 있으면 건드리지 않는다"""
        if ev.get("actor_type") == "synthetic":
            self.already += 1
        else:
            ev["actor_type"] = "synthetic"
            self.stamped += 1

        props = ev.get("properties")
        if not isinstance(props, dict):
            props = {}
            ev["properties"] = props
        # 프론트가 넣어준 값이 있으면 존중한다. 우리 값으로 덮으면 프론트가
        # 나중에 제대로 붙였을 때 그 사실을 확인할 방법이 없어진다
        props.setdefault("scenario_id", self.scenario_id)
        props.setdefault("simulation_run_id", self.simulation_run_id)
        props.setdefault("generator_type", GENERATOR_TYPE)
        return ev

    def _gate(self, events, gate):
        """이 페르소나의 행동이 아닌 이벤트를 걸러낸다.

        러너는 화면을 먼저 열고 페르소나를 골랐다. 그 사이에 렌더된 화면의
        이벤트를 프론트는 **기본 페르소나(PA00001)** 로 남긴다. 세션이 섞이지는
        않지만 앞 세션 통째로가 PA00001 몫이 되어, 2026-09-02 100명 실행에서
        **전체 이벤트의 44%(21,767건)가 한 사람에게 쌓였다.** 사람 단위 지표가
        전부 틀어지고, `persona_id` 가 채워져 있어 전송 필터도 통과한다.

        진입 순서를 고쳐(페르소나 먼저) 원인을 없앴지만, 프론트가 배치를
        모아 보내기 때문에 전환 직후 배치에 전환 전 이벤트가 섞여 올 수 있다.
        그래서 여기서 **이벤트 단위로** 한 번 더 본다.
        """
        if gate is None:
            return events
        pid = gate.get("persona_id")
        if pid is None:
            self.pre_switch += len(events)
            return []
        keep = [ev for ev in events if ev.get("persona_id") in (pid, None)]
        self.foreign += len(events) - len(keep)
        return keep

    def _handle(self, route, request, gate=None):
        try:
            payload = json.loads(request.post_data or "{}")
            self.schema_version = payload.get("schema_version") or self.schema_version
            events = [self._stamp(ev) for ev in payload.get("events", [])]
            events = self._gate(events, gate)
            for ev in events:
                self.f.write(json.dumps(ev, ensure_ascii=False) + NL)
                self.n += 1
                k = ev.get("event_name") or ev.get("action") or "?"
                self.kinds[k] = self.kinds.get(k, 0) + 1

            # 페르소나를 고르기 전(첫 화면 로드)에 발생한 이벤트는 보내지 않는다.
            # synthetic Event 는 persona_id 가 필수라 Spark 가 invalid_properties 로
            # 격리한다. 어느 페르소나의 행동도 아니므로 격리 로그만 늘 뿐이다.
            # 실측: 1인당 2건(첫 화면 scroll_depth). 파일에는 그대로 남긴다
            sendable = [ev for ev in events if ev.get("persona_id")]
            self.dropped += len(events) - len(sendable)
            if self.queue is not None and sendable:
                self.queue.put(sendable)
        except Exception:
            pass
        # 수집 서버 응답과 무관하게 200 을 돌려준다. 실패를 그대로 전하면
        # 프론트가 같은 배치를 재전송해 파일에 중복이 쌓인다. 전송 성패는
        # 우리가 세어서 실행 끝에 보고한다
        route.fulfill(status=200, content_type="application/json",
                      body='{"ok":true}')

    def _drain(self):
        """전송은 별도 스레드에서 한다.

        route 핸들러 안에서 그대로 보내면 브라우저가 응답을 기다리며 멈춘다.
        Kafka 가 안 떠 있으면 수집 서버가 25초쯤 뒤에 503 을 주는데, 그동안
        에이전트의 한 턴이 통째로 정지한다.
        """
        while True:
            events = self.queue.get()
            if events is None:
                self.queue.task_done()
                return
            try:
                self._post(events)
            except Exception:
                self.send_failed += len(events)
            self.queue.task_done()

    def _post(self, events):
        """수집 API 로 보낸다. 백프레셔 처리는 공용 클라이언트가 한다.

        생성기(gen_behavior_logs.py)와 **같은 클라이언트**를 쓴다 — 같은 서버에
        같은 계약으로 보내면서 재시도 정책이 다르면 부하 결과를 해석할 수 없다.
        """
        if self.client is None:
            sys.path.insert(0, os.path.join(ROOT, "simulator"))
            from collector_client import CollectorClient
            self.client = CollectorClient(
                self.post_base, timeout=self.timeout, max_batch=POST_BATCH,
                log=lambda m: print(f"   {m}"))
        before = dict(self.client.stats)
        self.client.send(
            events, schema_version=self.schema_version or SCHEMA_VERSION,
            headers={"X-Actor-Type": "synthetic",
                     "X-Simulation-Run-Id": self.simulation_run_id})
        st = self.client.stats
        self.sent += st["sent"] - before["sent"]
        self.send_failed += ((st["dropped"] - before["dropped"])
                             + (st["gave_up"] - before["gave_up"]))

    def close(self):
        if self.queue is not None:
            self.queue.put(None)
            self.worker.join(timeout=self.timeout + 10)
        self.f.close()


def login_member(page, persona_id):
    """PA 회원으로 로그인한다 (Jira 321). 로그인하면 프론트가 로그의 persona_id 를 회원 id 로 쓰고
    (fe 09-15), 서버 주문(/api/orders)이 가능해진다 — 스위처만으로는 `!member` 에서 주문이 막힌다."""
    try:
        if page.locator(".account__btn--me").count():
            return True                          # 이미 로그인돼 있다
        btn = page.locator(".account__btn--login")
        if not btn.count():
            return False
        btn.first.click()
        # 폼은 지연 로딩 청크에 있다(배포본 실측: auth__ 가 products-*.js 에 22회).
        # 워커 5개가 동시에 붙으면 고정 600ms 로는 못 기다린다 — 20명 중 15명이
        # 여기서 조용히 실패했다 (Jira 360). 보일 때까지 기다린다.
        email = page.locator("form.auth input[name=email]")
        email.first.wait_for(state="visible", timeout=15000)
        email.first.fill(MEMBER_EMAIL.format(pid=persona_id.lower()))
        page.locator("form.auth input[name=password]").first.fill(MEMBER_PASSWORD)
        page.locator("form.auth button[type=submit]").first.click()
        page.locator(".account__btn--me").first.wait_for(timeout=8000)
        page.wait_for_timeout(700)
        return True
    except Exception:
        return False


def switch_persona(page, persona_id):
    """드롭다운을 열고 해당 페르소나를 고른다. 이후 모든 로그의 persona_id 가 된다"""
    try:
        page.locator('[data-log-action="persona_switcher_open"]').first.click()
        page.wait_for_timeout(500)
        item = page.get_by_text(persona_id, exact=False).first
        item.click()
        page.wait_for_timeout(900)
        return True
    except Exception:
        return False


if __name__ == "__main__":
    main()
