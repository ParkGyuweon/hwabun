"""
행동 로그 생성기

페르소나 PC 9,900명의 탐색 행동을 LogEnvelope 형식으로 생성한다.
프론트 실제 로그(DevToolbar 관측)의 밀도와 properties 구조를 맞췄다.

PA 100명(personas_100_agent.json)은 생성하지 않는다 — 인터랙티브 전용이다.
프론트 페르소나 전환기(드롭다운)와 LLM 에이전트가 이 100명을 직접 조종한다.
합성 로그를 같이 쏘면 1인당 약 590건이 미리 쌓여, 사람이 10번 클릭해도
벡터의 1.7% 밖에 못 움직여 "누른 대로 추천이 바뀐다" 를 보여줄 수 없다.
부하 검증 손실은 590만 건 중 5.9만 건(1%) 이라 무시할 수준이다.
  PA00001~PA00100  인터랙티브 (프론트 드롭다운 + LLM 에이전트)
  PC00001~PC09900  합성 로그 (이 스크립트)
--include-agents 로 필요할 때만 PA 를 포함한다.

합의사항 (BEHAVIOR_SCENARIO.md)
  - 리뷰 작성 이벤트를 만들지 않는다. 리뷰 상품은 add_to_cart 로 환산
  - 페르소나당 상품 1개를 목표로 떼고 나머지 전부를 시드로 사용
  - 시드는 시뮬레이션 시작 전 상태 (Persona·상품·실행 단위별 session_id)
  - 이탈 상품은 취향이 아니라 노출(같은 카테고리 / 인기순)로 고른다
  - 노출에는 impression_dwell 을, 추천 섹션에는 recommendation_snapshot 을 남긴다
    (가중 0 이지만 노출 대비 클릭과 위치 편향 보정에 필요하다)
  - dead_click 은 생성하지 않는다 (실제 UI 오작동에서만 나오는 신호).
    rage_click 은 부정 시드에서만 소량 생성한다 (300명 기준 15건)
  - scroll_depth 는 프론트와 같은 10% 단위로 남기되, 가중치는 최대 도달 1건만 적용한다
  - actor_type 은 전부 synthetic
  - 상세 진입은 page_view + product_view 를 함께 남긴다 (프론트와 동일)
  - 장바구니 화면을 방문해 view_cart 를 남기고, 일부는 담았던 이탈 상품을 뺀다
  - 목록에서 일부 상품은 Quick Look 으로 열어본다 (--no-quick-look 으로 끈다).
    전용 난수 스트림을 쓰므로 껐을 때 나머지 궤적이 완전히 동일하다
  - 직전 상세의 추천에 다음 상품이 있으면 recommendation_click 으로 넘어간다
    (노출과 같은 recommendation_id / position 을 실어 CTR 이 성립하게 한다)
  - 그렇게 들어간 상세의 product_view 에도 recommendation_id / list_id / position 을 싣는다
    (추천 경유 유입 추적, Jira 210 — 계약 선택 필드. 프론트는 아직 안 실음)
  - 모든 synthetic Event properties 에 scenario_id / simulation_run_id /
    generator_type 을 기록한다

실행
  python gen_behavior_logs.py --limit 50                    # 맛보기. 파일로 저장
  python gen_behavior_logs.py                               # PC 9,900명
  python gen_behavior_logs.py --include-agents              # PA 100명까지 (기본 제외)
  python gen_behavior_logs.py --post http://localhost:8080  # 수집 API 로 전송
  python gen_behavior_logs.py --post http://localhost:8080 --rps 200 --limit 500
  python gen_behavior_logs.py --recommend-url http://localhost:8300 --limit 200 --out logs.jsonl
      # 추천 서버 연동 (Jira 221): 목록마다 실제 추천을 받아 items·hero·banners 의
      # recommendation_id·algorithm·banner_slot·trait_source 를 그대로 싣고, 행동을 서버 상태에 넘긴다.
      # 서버가 없으면 한 번 경고하고 예전 방식(banner_axes_v0)으로 돈다
  python gen_behavior_logs.py --limit 50 --scenario-id normal_day \
      --simulation-run-id run_20260831_001

전송 모드
  수집 API(POST /api/events) 로 배치 100건씩 보낸다. 백엔드 계약은
  ActivityEvent 레코드를 그대로 따르고, 필드는 프론트 LogEnvelope 와 같다.
  --rps 로 초당 이벤트 수를 제한해 부하를 조절한다 (0 이면 제한 없음).
"""
import argparse, json, os, sys, time, uuid, zlib
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import numpy as np

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
PERSONA_DIR = os.path.join(ROOT, "simulator", "personas", "data")
PRODUCTS = os.path.join(ROOT, "batch", "ingest", "data", "products_200.json")
FRONTEND_PRODUCTS = os.path.join(ROOT, "frontend", "src", "mocks", "products.sample.json")
# 등록 상품(SSAFY Beauty 8개, Jira 216) — 사이트에 있고 추천 서버가 히어로로 내주므로 생성기 카탈로그에도
# 있어야 한다. 없으면 히어로 클릭 경로에서 KeyError (2026-09-10, Jira 239). 리뷰 0 이라 popular 꼴찌 = 폴백 new_brand 후보
REGISTERED_PRODUCTS = os.environ.get("REGISTERED_PRODUCTS_PATH") or os.path.join(
    ROOT, "batch", "ingest", "data", "serving", "registered_products.jsonl")
FRONTEND_REGISTERED = os.path.join(ROOT, "frontend", "src", "mocks", "products.ssafy-beauty.json")
# 등록 브랜드 상품 id — 카탈로그를 만들 때 채운다. 리뷰가 없어 페르소나의 구매 후보에 못 드는 상품들이다.
REGISTERED_IDS = set()
PROPERTIES_CONTRACT = os.path.join(ROOT, "contracts", "event-properties-schema.md")
# 상품별 성분 — 드래그로 긁는 성분은 **그 상품이 실제로 가진 것**이어야 한다.
# 없는 성분을 실으면 ingredient_weekly_interest 마트(matched_ingredients 를 explode)가
# "이 성분을 긁은 사람" 과 "이 성분이 든 상품" 을 엉뚱하게 잇는다.
PRODUCT_INGREDIENT = os.path.join(ROOT, "batch", "ingest", "data", "serving", "product_ingredient.csv")
# 성분 사전 — 프론트 useTextSelection.ts 와 **같은 파일**을 쓴다. 따로 만들면
# 표준 명칭이 갈려 사람 로그와 생성기 로그가 같은 성분으로 안 묶인다.
FEATURE_VOCAB = os.path.join(ROOT, "contracts", "product-feature-vocab.json")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "batch", "jobs"))
import behavior_weights as BW
sys.path.insert(0, BD)                     # 패키지로 import 될 때(테스트)도 옆 모듈이 보이게
from recommend_client import RecommendClient, hero_from_response      # noqa: E402  (Jira 221·239)

# ── 행동을 무엇이 정하는가 ──────────────────────────────────────────────────
# 기본(rule) 모드는 **평가 정답(target)을 알고 그 상품에 반드시 전환**한다.
# 트래픽·파이프라인 검증에는 문제없지만, 그 로그로 추천을 평가하면 정답이 로그에
# 심겨 있는 셈이라 자기실현 평가가 된다.
#
# --hidden-preference 모드는 추천·정답과 분리된 hidden preference 가 행동 강도를
# 정하고, **target 에 전환을 강제하지 않는다.** 평가에 쓸 로그는 이 모드로 만든다.
# 계약: docs/ai/evaluation-framework.md 2절 · 6단계
BEHAVIOR_RULE = "rule"
BEHAVIOR_HIDDEN = "hidden_preference"

SCHEMA_VERSION = "0.2.0-draft"
ENV = "simulation"
DEFAULT_SCENARIO_ID = "normal_day"
# 이벤트 금액 통화 (Jira 303, 데이터 파트 요청 09-16). 화면·카카오페이는 원화인데 이벤트만 달러였다.
# 환산은 추천 인코더 `product_encoder.price_krw_of` 와 같은 규칙(price_krw 정본, 없으면 USD × 1340.86 을 100원 단위).
# 필드 이름 결정(A/B)이 나기 전까지 기본은 USD 로 두고 `--currency KRW` 로 켠다.
CURRENCY_USD, CURRENCY_KRW = "USD", "KRW"
CURRENCY = CURRENCY_USD


def money(item_price_usd, item_price_krw):
    """이벤트에 실을 금액 — 통화 스위치대로. KRW 는 정수 원, USD 는 소수 2자리"""
    if CURRENCY == CURRENCY_KRW:
        return int(item_price_krw) if item_price_krw is not None else None
    return round(float(item_price_usd), 2)
DEFAULT_GENERATOR_TYPE = "python_batch"
# occurred_at 은 UTC 로 나간다 (`...Z`). 프론트도 `new Date().toISOString()` 로 UTC 를 싣고,
# 원천이 그대로 event_time 에 넣은 뒤 정제가 `from_utc_timestamp(event_time, KST)` 로 되돌린다.
# 예전에는 한국 시각에 `Z` 만 붙여서 **9시간 미래**가 됐고, 정오 넘는 이벤트가 다음 날로 넘어갔다
# (09-17 GEN_NOW=today 로 드러남). 사람이 주는 기준 시각은 한국 시각으로 읽고 여기서 UTC 로 바꾼다.
KST_OFFSET = timedelta(hours=9)


def _resolve_now():
    """생성기 기준 시각. 모든 이벤트 시각이 여기서 거꾸로 뻗어 나간다 (window_days 만큼).

    기본은 고정 상수다 — 평가용 로그가 재현돼야 하기 때문이다. 같은 씨앗으로 같은 파일이 나와야
    홀드아웃 비교가 성립한다.

    시연 로그는 사정이 다르다. 고정 시각으로 만들면 마트가 그 시점(2026-06-04~08-28)에 쌓이는데,
    대시보드 기본 조회창은 "어제까지 14일" 이라 영영 안 걸린다. 배치가 다 성공해도 화면이 빈다.
    그래서 시연 캐시를 만들 때만 `GEN_NOW` 로 오늘을 준다 — 로그 85일치가 통째로 따라와
    최근 14일에 날짜별 데이터가 생긴다.

        GEN_NOW=today                 오늘 12:00 (KST 자정 넘김을 피하려 정오)
        GEN_NOW=2026-09-17            그 날 12:00
        GEN_NOW=2026-09-17T09:30:00   분까지

    주의: 이 값을 바꾸면 **같은 씨앗이라도 다른 파일**이 나온다. 평가 데이터셋을 다시 만들 때는
    주지 말 것.
    """
    raw = (os.environ.get("GEN_NOW") or "").strip()
    if not raw:
        # 평가용 로그의 재현성을 위해 **바뀌지 않는다**. 예전부터 이 값이었고, 같은 씨앗이면 같은 파일이
        # 나와야 홀드아웃 비교가 성립한다. UTC 로 읽히지만 08-28 은 아무도 오늘과 비교하지 않는다.
        return datetime(2026, 8, 28, 12, 0, 0)
    if raw.lower() == "today":
        # 한국 기준 오늘 정오를 UTC 로. occurred_at 은 UTC 로 나가야 한다 (아래 KST_OFFSET 설명)
        t = datetime.now()
        return datetime(t.year, t.month, t.day, 12, 0, 0) - KST_OFFSET
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            d = datetime.strptime(raw, fmt)
            # 사람이 주는 값은 한국 시각으로 읽는다. 안에서는 UTC 로 돈다
            return (d if fmt != "%Y-%m-%d" else d.replace(hour=12)) - KST_OFFSET
        except ValueError:
            continue
    raise SystemExit(f"GEN_NOW 형식이 아닙니다: {raw!r} (today · 2026-09-17 · 2026-09-17T09:30:00)")


NOW = _resolve_now()
CHECKPOINT_MS = 15000                # 목록 체류 중 dwell 재발화 주기
LIST_IMPRESSION_HOLD_MS = 300
RECOMMENDATION_IMPRESSION_HOLD_MS = 1000
IMPRESSION_VISIBLE_RATIO = 0.5


def default_simulation_run_id(now=None):
    """Return a readable execution ID when the caller does not provide one."""

    timestamp = now or datetime.now(timezone.utc)
    return f"run_{timestamp.strftime('%Y%m%dT%H%M%SZ')}"


@dataclass(frozen=True)
class SimulationContext:
    """Metadata shared by every synthetic Event in one generator run."""

    scenario_id: str
    simulation_run_id: str
    generator_type: str

    def __post_init__(self):
        for name, value in (
            ("scenario_id", self.scenario_id),
            ("simulation_run_id", self.simulation_run_id),
            ("generator_type", self.generator_type),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")


def history_session_id(context, persona_id, product_id):
    """비시드 과거 구매 세션 id (Jira 327). 재구매 쌍은 마트가 실제 주문으로 세야 하므로 seed: 접두를 안 쓴다"""
    return f"hist:{context.simulation_run_id}:{persona_id}:{product_id}"


def seed_session_id(context, persona_id, product_id):
    """Build a seed session key that cannot merge personas or products."""

    return f"seed:{context.simulation_run_id}:{persona_id}:{product_id}"


def history_detail_entry(e, g):
    """hist: 과거 구매 세션의 상세 진입 — 목록 노출부터 조회까지 (Jira 345·349).

    hist: 세션은 마트가 실제 주문으로 세는데(327), 이 앞단이 없으면 마트 불변식이 두 번 깨진다.
      * 상세 조회가 없으면  add_to_cart_sessions > detail_view_sessions   (345 에서 product_view 로 해소)
      * 노출이 없으면       impression_sessions=0 인데 detail_view_sessions=1 → detail_entry_rate > 1
        (349. 데이터 336 본 실행에서 노출 없이 상세 도달한 (세션,상품) 1,493건 = hist: 세션 수)

    그래서 목록에서 카드를 보고(노출) 상세로 들어간 흐름을 만든다 — 노출 → 조회 → 담기 → 구매.
    퍼널 단계 귀속이 `event_time` 순서로 정해지므로 **노출이 조회보다 앞서야 한다**.
    navigation_source 는 계약 §3.4 — 세션 첫 page_view 는 session_start, 상세 진입은 in_app 이고
    같은 상세 진입의 product_view 는 그 page_view 와 같은 값이어야 한다.
    시드(seed:) 세션은 여기 오지 않는다 — 계약대로 "긍정 시드는 조회 없이 add_to_cart 만" 이고 마트는 seeded 를 뺀다."""
    e.new_page("product_list")
    e.emit("page_view", navigation_source="session_start")   # 목록 페이지라 product_id 는 싣지 않는다
    e.tick(20, 120)
    e.emit("product_impression", g, position=1, list_id="list_grid",
           hold_ms=LIST_IMPRESSION_HOLD_MS, visible_ratio=IMPRESSION_VISIBLE_RATIO)
    e.tick(200, 900)
    e.new_page("product_detail")
    e.emit("page_view", g, navigation_source="in_app")
    e.tick(300, 1200)
    e.emit("product_view", g, navigation_source="in_app")
    e.tick(500, 3000)

# ══════════════════════════════════════════════════════════════════════════
#  시나리오 파라미터 — ⚠️ 전부 자리표시자다. 팀 합의 전이므로 튜닝하지 않는다.
#
#  아래 값들은 BEHAVIOR_SCENARIO.md 의 "결정이 필요한 것"에 걸려 있다.
#  회의에서 정해지면 이 블록만 고치면 되고 아래 로직은 건드릴 필요가 없다.
# ══════════════════════════════════════════════════════════════════════════
# 상품별 평점 평균 기준. build_personas.py / eval_polarity.py 와 같은 값을 쓴다
POS_MIN, NEG_MAX = 3.5, 2.5

SCENARIO = {
    # [회의 안건 4-4] 목표 상품 1개당 조회만 하고 나갈 상품 수
    #   실제 이커머스 전환율 2~3%를 그대로 쓰면 200개 카탈로그를 다 훑게 되므로 낮춘 값
    "bounce_range": (2, 6),

    # [회의 안건 4-4] 시간축 압축 폭 (일)
    #   리뷰가 2019~2023년에 걸쳐 있어 그대로 쓰면 시간 감쇠(tau=30일)가 소멸한다
    # 시드(과거 구매) 세션을 흩어 놓는 기간. 첫 구매와 재구매(S2, restock_gap_days)가 **둘 다** 데이터 마트의
    # 재구매 창(build_marts_job --repurchase-window-days 기본 90일, NOW 기준) 안에 들어야 재구매율이 잡힌다.
    # 120일이었을 때 시드 결제가 창 밖(4~5월)에 몰려 repeat_buyer 가 전부 0 이었다 (09-15 실측, Jira 313).
    # 85일 × 0.7 = 약 60일에 걸쳐 첫 구매를 놓고, 재구매 간격 14~30일이면 대부분 창 안에서 두 번째 구매가 난다.
    "window_days": 85,

    # [미정] 목록 페이지 체류 시간 (ms). checkpoint dwell 발생량을 좌우한다
    "list_dwell_ms": (8000, 70000),

    # [미정] 이탈 상품의 스크롤 도달 깊이 (%). 목표 상품은 항상 100
    "bounce_depth_choices": (20, 30, 40, 50),

    # [미정] 부정 시드(별점 1~2점 상품) 재현 파라미터
    #   실제로 산 상품이므로 상세는 봤다. 다만 얕게 보고 감점 신호를 남기고 나간다
    "neg_seed_depth_choices": (20, 30, 40),
    "neg_seed_p_rage": 0.35,

    # [미정] 찜 확률
    "wishlist_p_target": 0.45,
    "wishlist_p_bounce": 0.08,

    # [미정] 장바구니 화면 방문·후회 재현
    #   p_cart_regret: 이탈 상품 하나를 충동적으로 담았다가 장바구니에서 빼는 확률.
    #     "담았다 빼기" 는 가장 명확한 부정 신호이고, user_vector 의 UNDO 경로
    #     (converted 에서 제거 -> v_u- 로 이동) 를 실제로 태우는 유일한 동선이다.
    #   빼는 대상을 **이탈 상품**으로 고른 이유: 시드는 별점 4~5점을 준 상품이라
    #     "담았다 뺐다" 가 데이터와 모순된다. 이탈 상품은 평점이 없어 모순이 없다.
    "p_cart_regret": 0.22,
    #   장바구니 화면 자체를 열어보는 확률 (후회가 없어도 확인차 들어간다)
    "p_view_cart": 0.70,
    #   장바구니에서 수량을 조절하는 확률
    "p_quantity_change": 0.18,

    # [추정] 결제 (Jira 312). 09-15 로컬 마트 스냅샷에서 구매 마트 3종이 0 이었다 — 이 생성기가 purchase 를
    #   안 만들었기 때문. 결제 이벤트는 프론트 화면(포트원·카카오페이 테스트 채널, 09-14)에서만 나오고 있었다.
    #   p_purchase_after_cart: 목표 상품을 담은 세션이 결제까지 가는 비율. 프론트 가중치 원칙
    #     "purchase : add_to_cart ≥ 2 : 1" 은 가중치 얘기지 전환율이 아니다 — 여기 값은 첫 실측(구매 로그 1,000건)
    #     전까지의 가설이다. 시드(과거 구매)는 확률 없이 전부 결제한다: 리뷰를 썼다 = 샀다.
    #   p_payment_failed: 결제창에서 실패·취소. 전환 마찰의 마지막 칸(계약 §2 payment_failed).
    #   p_reason_answer: 구매 직후 이유 설문에 답하는 비율. 나머지는 skipped=true·reasons=[] (계약 §3.9).
    "p_purchase_after_cart": 0.45,
    "p_payment_failed": 0.05,
    "p_reason_answer": 0.70,
    "p_discount": 0.20,            # 쿠폰·프로모션으로 paid_value < order_value 인 주문 비율
    "payment_methods": (("kakaopay", 0.6), ("card", 0.4)),   # `test` 는 시연 주문 전용이라 합성 로그에 안 쓴다

    # [미정] 유사 상품 추천을 눌러 다음 상세로 넘어가는 확률.
    #   직전 상세의 추천 노출과 같은 recommendation_id / position 을 실어야
    #   CTR 을 계산할 수 있다 (SimilarProducts.tsx 와 동일).
    "p_rec_click": 0.55,
    "p_banner_click": 0.12,     # 목록에서 다음 상품을 배너로 들어가는 비율
    "p_banner_explore": 0.20,   # trait_source=explore 비율 (배너 계획 §3)

    # [미정] 이탈 상품을 끝까지 훑어보는 확률 ("진지하게 봤지만 안 샀다").
    #   similar_products 는 7개 섹션 중 6번째라 스크롤 79% 이상이어야 도달한다.
    #   기본 이탈 깊이(20~50%)로는 추천이 노출조차 되지 않아
    #   recommendation_click 이 구조적으로 발생할 수 없다.
    "p_deep_bounce": 0.30,
    "deep_bounce_depth": 90,

    # [미정] Quick Look — 목록 카드에서 요약 창을 여는 동선.
    #   A/B 측정을 위해 **전용 난수 스트림**을 쓴다. 본 동선의 rng 를 건드리면
    #   Quick Look 을 켠 것만으로 이후 궤적이 통째로 달라져 비교가 불가능해진다.
    # [미정] 성분 표시 방식 전환 — 칩(요약) <-> 원문. 검증 행동의 대표 신호다.
    #   "성분을 보고 샀나 리뷰를 보고 샀나" 를 가르는 축이라 대시보드 핵심 화면에 쓰인다
    "p_ingredient_mode": 0.30,
    # [미정] 선택한 텍스트를 실제로 복사하는 확률 (text_selection 이 난 뒤)
    #   페이지 밖으로 들고 나갈 만큼 관심이 있었다는 뜻이라 selection 보다 무겁다
    "p_text_copy": 0.28,
    # [미정] 담기 직전 버튼 위에서 망설이는 확률
    "p_hover_before_cart": 0.40,
    # [미정] 노출된 상품이 화면에 머문 시간을 남길 확률 (분모용, 가중 0)
    "p_impression_dwell": 0.55,

    "p_quick_look": 0.18,     # 노출된 상품 하나를 열어볼 확률
    "p_ql_variant": 0.45,     # 창 안에서 옵션을 바꿔볼 확률
    "p_ql_add": 0.12,         # 창 안에서 바로 담을 확률
    "p_ql_wish": 0.10,

    # [미정] 상세 페이지 내 상호작용 확률
    "p_scroll_pause": 0.55,
    "p_accordion": 0.50,
    "p_text_selection": 0.35,
    # [미정] 성분 섹션에서 성분명을 긁을 확률. p_text_selection(설명 문구를 긁는 것)과
    #   나눈 이유는 성향이 다른 축을 타기 때문이다 — 성분 성향은 이쪽, 향 성향은 저쪽.
    "p_ingredient_selection": 0.40,
    "p_variant_select": 0.40,
    "p_review_filter": 0.50,
    "p_scroll_backtrack": 0.25,
    "p_list_filter": 0.35,
    "p_list_sort": 0.20,

    # 세션 구성 — BEHAVIOR_SCENARIO 4-2절의 "며칠에 걸친 1~3회 방문" (S3).
    # 한 세션에 다 몰아넣으면 세션당 체류·전환·재방문 지표가 전부 한 덩어리가 되어
    # 대시보드에서 "다시 온 사람" 을 셀 수 없다.
    "visit_weights": (0.35, 0.40, 0.25),   # 1회 / 2회 / 3회
    "revisit_window_days": 5,              # 최근 이 기간 안에 나눠 담는다
    # 등록 브랜드(SSAFY Beauty) 상세를 보고 담는 비율. 리뷰 이력과 무관한 "발견 구매" 다.
    # 페르소나의 담기·구매는 본인 리뷰 이력(pos)에서만 나오는데, 등록 상품은 우리가 만든
    # 가상 브랜드라 세포라 원천 리뷰에 있을 수가 없다. 그래서 노출·조회는 되는데 **한 번도 안 팔렸다**
    # (09-17 실측: 노출 39,013 · 조회 1,290 · 구매 0). 판매자 대시보드가 보여 줄 브랜드가
    # 그 브랜드인데 재생 로그로는 구매 지표가 영영 안 찬다.
    # 실제 쇼핑몰에서도 신규 브랜드는 리뷰 이력 없이 팔린다 — 상세를 보고 마음에 들면 담는 경로다.
    "p_new_brand_cart": 0.12,
    # 담은 것을 결제까지 가져가는 비율. 목표 상품 결제에 얹는다
    "p_new_brand_buy": 0.55,
    # 상세를 보고 목록으로 돌아갔다가 같은 상품을 다시 여는 비율 (Jira 350).
    # 새 진입이 아니라 재조회라 마트가 건수 집계에서 빼야 하고, 그 제외 로직을 재려면 로그에 있어야 한다.
    "p_history_back": 0.06,

    # 재구매 (S2) — 같은 상품에 리뷰가 2건 이상이면 재구매로 본다.
    # 실측: 9,900명 중 60.6% 가 해당하고 리뷰 간격 중앙값이 264일이다.
    # 시드 창(120일) 안에 넣어야 하므로 간격은 압축한다.
    "restock_gap_days": (14, 30),           # 재구매 간격. 상한을 낮춰 두 번째 구매가 NOW 를 넘지 않게 (Jira 313)
}

# ══════════════════════════════════════════════════════════════════════════
#  페르소나별 성향 — 리뷰 텍스트에서 도출 (BEHAVIOR_SCENARIO.md 10-7절)
#
#  build_persona_style.py 가 각 페르소나의 리뷰를 6개 축에 투영해 0~1 점수를 낸다.
#      ingredient / price / texture / scent / sensitivity / review_lean
#
#  ⚠️ 성향은 "어떻게 보는가"만 결정한다. "무엇을 고르는가"에는 관여하지 않는다.
#     후자를 건드리면 추천 점수가 쓰는 축과 겹쳐 순환이 된다.
#
#     ❌ "성분 민감하니 성분 좋은 상품을 고르게 하자"
#     ✅ "성분 민감하니 ingredients 섹션을 오래 보고 텍스트를 긁게 하자"
#
#  파일이 없으면 전원 동일 분포로 동작한다(성향 미적용).
# ══════════════════════════════════════════════════════════════════════════
STYLE_EFFECT = {
    # 축 -> (확률 키, 최대 배율). 점수 0.5 에서 1.0배, 1.0 에서 최대 배율이 된다
    "ingredient":  [("p_accordion", 1.8), ("p_ingredient_selection", 2.2), ("dwell_x_ingredients", 2.2)],
    "price":       [("p_variant_select", 2.0), ("dwell_x_product_hero", 1.6)],
    "texture":     [("p_scroll_pause", 1.4), ("dwell_x_about_product", 1.5)],
    "scent":       [("p_text_selection", 1.4), ("dwell_x_about_product", 1.4)],
    "sensitivity": [("p_accordion", 1.6), ("dwell_x_ingredients", 2.0), ("p_scroll_backtrack", 1.5)],
    "review_lean": [("p_review_filter", 2.0), ("dwell_x_reviews", 2.2)],
}
_STYLE = {}


def load_style():
    global _STYLE
    fp = os.path.join(PERSONA_DIR, "persona_style.json")
    if os.path.exists(fp):
        _STYLE = json.load(open(fp, encoding="utf-8"))
        log(f"페르소나 성향 로드 {len(_STYLE):,}명 (6개 축)")
    else:
        log("persona_style.json 없음 — 전원 동일 분포로 진행")


def persona_style(p):
    """페르소나 성향을 확률·체류 배율로 변환한다"""
    sc = dict(SCENARIO)
    sc.update({f"dwell_x_{k}": 1.0 for k in
               ("product_hero", "highlights", "about_product", "ingredients",
                "how_to_use", "similar_products", "reviews")})
    st = _STYLE.get(p["persona_id"])
    if not st:
        return sc
    for axis, effects in STYLE_EFFECT.items():
        v = st.get(axis, 0.5)
        for key, mx in effects:
            # 0.5 -> 1.0배, 1.0 -> mx배. 0.5 미만은 완만히 감소
            f = 1.0 + (mx - 1.0) * max(0.0, (v - 0.5) * 2)
            if key.startswith("p_"):
                sc[key] = min(0.95, sc[key] * f)
            else:
                sc[key] = sc[key] * f
    return sc


# ── 성분 드래그 (Jira 351) ────────────────────────────────────────────────
#  화장품에서 성분은 구매 판단의 상위 요인이라, 사용자는 모르는 성분명을 만나면
#  그 부분만 긁어 따로 검색한다. "어느 문장을 긁었는가" 는 클릭보다 관심 대상을
#  정확히 짚는 신호다. 프론트 useTextSelection.ts 가 실사용자에게서 이걸 받고,
#  생성기는 같은 모양을 페르소나에게서 만든다.
#
#  ⚠ 두 가지를 프론트와 반드시 맞춘다.
#    1) 사전은 contracts/product-feature-vocab.json **하나**를 같이 쓴다. 따로 만들면
#       표준 명칭이 갈려 "이 성분을 긁은 사람" 과 "이 성분이 든 상품" 이 조인되지 않는다.
#    2) matched_ingredients 는 **그 상품이 실제로 가진 성분**에서만 고른다. 없는 성분을
#       실으면 ingredient_weekly_interest 마트(matched_ingredients 를 explode)가 거짓이 된다.
_PRODUCT_INGREDIENTS = {}   # product_id -> [(표준 성분명, position_weight)]
_VOCAB_VERSION = None


def load_ingredients():
    """상품별 성분과 어휘집 판을 읽는다. 없으면 드래그는 성분 없이 난다."""
    global _VOCAB_VERSION
    if os.path.exists(FEATURE_VOCAB):
        _VOCAB_VERSION = json.load(open(FEATURE_VOCAB, encoding="utf-8")).get("version")
    if not os.path.exists(PRODUCT_INGREDIENT):
        log("product_ingredient.csv 없음 — 드래그에 성분을 싣지 않는다")
        return
    import csv
    with open(PRODUCT_INGREDIENT, encoding="utf-8", newline="") as fp:
        for row in csv.DictReader(fp):
            try:
                weight = float(row.get("position_weight") or 0.0)
            except ValueError:
                weight = 0.0
            _PRODUCT_INGREDIENTS.setdefault(row["product_id"], []).append(
                (row["ingredient"], max(weight, 0.01)))
    log(f"상품별 성분 로드 {len(_PRODUCT_INGREDIENTS):,}개 상품 (어휘집 {_VOCAB_VERSION})")


def pick_ingredients(product_id, rng):
    """긁은 구간에 걸린 성분. 전성분에서 앞에 놓인 것일수록 자주 걸린다.

    position_weight 는 전성분 배합 순서 기반이라 그대로 뽑기 가중치로 쓴다.
    한 번 긁으면 보통 성분 하나지만, 나란히 적힌 둘이 같이 걸리기도 한다.
    """
    pool = _PRODUCT_INGREDIENTS.get(product_id)
    if not pool:
        return []
    weights = np.array([w for _, w in pool], dtype=float)
    take = min(len(pool), 1 if rng.random() < 0.78 else 2)
    idx = rng.choice(len(pool), size=take, replace=False, p=weights / weights.sum())
    return sorted({pool[int(i)][0] for i in np.atleast_1d(idx)})


def selection_kind(content_kind, matched_count):
    """계약 §3.6. 프론트 useTextSelection.ts 의 selectionKindOf 와 같은 규칙이다.

    사전 매칭이 있으면 그것이 우선이다 — 리뷰 문장에서 성분명을 긁어도 성분 관심이다.
    성향 표(user-trait-weights.json)가 이 값으로 가격·고민·성분 성향을 센다.
    """
    if matched_count > 0:
        return "ingredient"
    return {
        "ingredient_list": "ingredient", "ingredient_callout": "ingredient",
        "price": "price",
        "clinical_claim": "claim", "highlight_badge": "claim", "what_it_is": "claim",
        "usage_guide": "usage",
    }.get(content_kind, "other")


def emit_selection(e, gid, rng, SC, section, content_kind, content_ref, with_ingredients):
    """드래그 한 번, 그리고 확률로 복사까지.

    프론트는 같은 선택에 대해 text_selection 뒤 text_copy 를 남긴다(useTextSelection).
    복사는 페이지 밖으로 들고 나갈 만큼 관심이 있었다는 뜻이라 더 무겁게 본다.
    긁은 원문은 계약상 보내지 않는다 — 사전에 걸린 표준 명칭만 싣는다.
    """
    matched = pick_ingredients(gid, rng) if with_ingredients else []
    props = dict(section_id=section, content_kind=content_kind, content_ref=content_ref,
                 text_length=int(rng.integers(20, 200)), truncated=False,
                 selection_kind=selection_kind(content_kind, len(matched)))
    if matched:
        props.update(matched_ingredients=matched, matched_count=len(matched),
                     vocab_version=_VOCAB_VERSION)
    e.tick()
    e.emit("text_selection", gid, **props)
    if rng.random() < SC["p_text_copy"]:
        e.tick(200, 2000)
        e.emit("text_copy", gid, **props)


# ── 이벤트 intent — log.ts 의 EVENT_INTENT 를 그대로 읽는다 ────────────────
#    사본을 두면 프론트가 이벤트를 추가했을 때 조용히 어긋난다.
_W = BW.load()
INTENT = _W["intent"]
# 배너 2종은 dev 의 frontend log.ts EVENT_INTENT 에 아직 없다 (FE 184 브랜치에 있음).
# 프론트가 머지되면 log.ts 값이 이긴다 — 여기는 그때까지의 대체값, FE 184 log.ts 와 같은 값
BANNER_INTENT = {"banner_impression": "session", "banner_click": "interest"}


# ── 화면 구조: 섹션 -> (콘텐츠 종류, content_ref) ──────────────────────────
#    프론트 실측 로그에서 역산했다. 섹션 순서 = 스크롤 순서
# 상세를 이 깊이(%) 이상 본 세션을 "정독" 으로 본다. 성분 모드 전환·아코디언·본문 드래그
# 같은 미세 상호작용은 이 세션에서만 난다.
ENGAGED_DEPTH_MIN = int(os.environ.get("GEN_ENGAGED_DEPTH_MIN", "75"))
# 옛 규칙(engaged = target 여부)으로 되돌리는 스위치. A/B 와 즉시 롤백용이다.
ENGAGED_RULE = os.environ.get("GEN_ENGAGED_RULE", "depth")   # depth | target

DETAIL_LAYOUT = [
    ("product_hero",     [("product_image", None), ("price", None),
                          ("variant_option", None), ("cta", None)]),
    ("highlights",       [("highlight_badge", None)]),
    ("about_product",    [("what_it_is", None), ("ingredient_list", "highlighted"),
                          ("what_else", None), ("ingredient_callout", None),
                          ("clinical_claim", None), ("persona_match", "skin_type"),
                          ("persona_match", "concerns"), ("product_meta", "category"),
                          ("product_meta", "size")]),
    # 전성분 아코디언은 실제 화면도 contentKind 를 안 싣는다
    # (frontend/src/pages/ProductDetailPage.tsx:141~150) — None 이 맞다.
    ("ingredients",      [(None, None)]),
    # 사용법 아코디언은 실제 화면이 usage_guide 를 싣는다 (같은 파일 153행,
    # `<Accordion title="How to Use" sectionId="how_to_use" contentKind="usage_guide">`).
    # 여기가 None 이면 합성 로그에만 usage_guide 가 없어 대시보드 콘텐츠 화면의
    # '사용법' 행이 통째로 빈다 (Jira 364, 09-19 dw 실측 0건).
    ("how_to_use",       [("usage_guide", None)]),
    ("similar_products", [("recommendation_card", "__rec__")]),
    ("reviews",          [("review_stats", None), ("review_filter", None),
                          ("user_review", None)]),
]
# 목록 화면 크기 — **프론트와 같은 값을 쓴다** (frontend/src/pages/ProductListPage.tsx).
# 여기가 어긋나면 합성 로그와 실제 화면 로그의 노출 수가 달라져서, 노출 대비 클릭
# 같은 지표를 두 출처에서 같이 볼 수 없다.
PROMO_SIZE = 10        # 맞춤 기획전 칸 수
PAGE_SIZE = 25         # 목록 첫 화면 카드 수 ("더 보기" 로 25씩 늘어난다)

LIST_LAYOUT = [("promo_row", "product_card"), ("list_controls", None),
               ("product_grid", "product_card")]

# ── 배너 (Jira 212, DATA E2E 검증용) ────────────────────────────────────
# 화면은 **히어로 배너 하나**다 (2026-09-10, Jira 239). 배너 행 6칸(축 4 + new_brand 2)은 09-10
# 기획 검토로 빠졌고, 히어로는 추천 서버 `hero=new_brand` 로 신규 상품 중 점수 최고를 받는다.
# 값은 frontend/src/pages/ProductListPage.tsx 의 히어로 기록과 같다 — list_id `hero_banner`,
# `banner_slot` 1 (계약상 1 이상), `policy_version` 동봉(event-properties-schema §3.13).
# property 이름은 DATA 계약 그대로 `banner_slot` 이다 — `slot` 은 스키마·클렌징 양쪽에서 거부된다.
# 서버가 없을 때(폴백)는 리뷰가 가장 적은 상품을 new_brand 히어로로 세운다 — 자리와 이벤트 형태
# 검증용이지 신규 브랜드 노출 실측이 아니다. 배너 행이 살아나면 SLOTS/RESERVED 와 list_id 만 되돌린다.
BANNER_EVENTS = True
BANNER_SLOTS = 1
BANNER_RESERVED = 1
BANNER_HERO = "new_brand"        # 추천 서버 `hero` 파라미터 (top | new_brand)
BANNER_AXES = ("concern", "segment", "price_bin")
BANNER_ALGO = "banner_axes_v0"
BANNER_LIST_ID = "hero_banner"
# 프론트 bannerConfig.BANNER_POLICY_VERSION 과 같은 값을 싣는다 — banner_daily 에서 정책 전후를 자르는 키.
# 프론트가 올리면 여기도 올린다 (09-10 프론트 공유: banner-2026-09-10.2 = 히어로 신규 우선 + 성분 축 위치순)
BANNER_POLICY_VERSION = "banner-2026-09-10.2"
MAIN_LIST_ID = "main"            # 추천 서버 응답의 list_id (recommendation-io-spec §5)
# 추천 서버 클라이언트 (Jira 221). main() 이 --recommend-url 로 만든다. None 이면 예전 방식
RECO = None
# DATA 계약이 required 로 두되 null 을 허용하는 property — emit 의 None 제거에서 제외
NULLABLE_REQUIRED_PROPS = frozenset({"banner_value"})
PRICE_BINS = ((20, "~20"), (35, "20-35"), (50, "35-50"), (80, "50-80"), (10**9, "80+"))


def price_bin(price):
    for edge, label in PRICE_BINS:
        if price is None or price < edge:
            return label
    return "80+"


def banner_value(kind, persona, item):
    """축별 banner_value — 어휘집 원문. new_brand 는 None (키는 남기고 null 로 싣는다)"""
    if kind == "concern":
        return item.get("concern")
    if kind == "segment":
        return persona.get("skin_type")
    if kind == "price_bin":
        return price_bin(item.get("price"))
    return None


def make_banners(persona, catalog, pool, popular, rng, force=None, exclude=()):
    """이 화면의 배너 BANNER_SLOTS 칸 (지금은 히어로 1칸). `force` 를 주면 그 상품을 배너에 넣는다 —
    그래야 banner_click 이 항상 노출된 배너에서 나온다 (CTR 성립).

    앞 (BANNER_SLOTS - BANNER_RESERVED) 칸은 축 배너, 뒤 BANNER_RESERVED 칸은 new_brand.
    new_brand 칸은 카탈로그에 신규 브랜드 표식이 없어 **리뷰가 가장 적은 상품**으로 채운다 —
    자리와 이벤트 형태를 검증하는 용도지 신규 브랜드 노출 실측이 아니다.
    축 칸이 0 개인데 force 가 있으면(히어로 단독 화면) force 가 new_brand 히어로 자리를 차지한다.
    """
    n_axis = BANNER_SLOTS - BANNER_RESERVED
    cand = [g for g in pool if g not in exclude and g != force]
    axis_items = list(rng.choice(cand, size=min(n_axis, len(cand)), replace=False)) if cand else []
    forced_reserved = False
    if force is not None:
        if n_axis >= 1:
            axis_items = axis_items[:n_axis - 1]
            axis_items.insert(int(rng.integers(0, len(axis_items) + 1)), force)
        else:
            forced_reserved = True
    used = set(axis_items) | set(exclude) | ({force} if force is not None else set())
    n_fresh = BANNER_RESERVED - (1 if forced_reserved else 0)
    fresh = ([force] if forced_reserved else []) + [g for g in reversed(popular) if g not in used][:n_fresh]
    out = []
    for slot, g in enumerate(axis_items, 1):
        # 축 칸의 banner_value 는 계약상 string 필수 — 이 상품에 값이 있는 축만 고른다
        # (concern 이 비어 있는 상품이 있다). price_bin 은 항상 값이 있어 빈 후보가 안 나온다
        kinds = [k for k in BANNER_AXES if banner_value(k, persona, catalog[g]) is not None]
        kind = str(rng.choice(kinds))
        out.append({"slot": slot, "type": kind, "product_id": g,
                    "value": banner_value(kind, persona, catalog[g])})
    for k, g in enumerate(fresh, 1):
        out.append({"slot": n_axis + k, "type": "new_brand", "product_id": g, "value": None})
    return out


def trait_source_of(first, rng, SC=None):
    """성향을 어디서 얻었나. 첫 방문은 coldstart, 재방문은 profile, 일부는 explore
    (성향을 알아도 다른 축을 주는 A/B 표본 — personalized-banner-plan §3)"""
    p_explore = (SC or SCENARIO)["p_banner_explore"]
    if rng.random() < p_explore:
        return "explore"
    return "coldstart" if first else "profile"


def log(m): print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


SEED_PREFIX = "seed-"


def seed_sid(persona_id, product_id):
    """시드 세션 id. 상품마다 별개 세션으로 나눈다.

    시드는 **서로 다른 시점에 일어난 과거 구매**다. 원본 리뷰의
    submission_time 이 몇 달씩 벌어져 있고 이 생성기도 날짜를 벌려놓는다.
    전원이 session_id="seed" 하나를 공유하면 세션당 체류시간·전환율 같은
    지표가 통째로 왜곡되고, 상품마다 Emitter 를 새로 만들기 때문에
    sequence_no 도 1 부터 다시 시작해 세션 단위 집계가 깨진다.
    """
    return f"{SEED_PREFIX}{persona_id}-{product_id}"


def is_seed(ev):
    """시드 이벤트인가. 명시적인 metadata를 우선하고 legacy prefix도 읽는다."""
    return (ev.get("properties", {}).get("seeded") is True
            or str(ev.get("session_id", "")).startswith(SEED_PREFIX)
            or str(ev.get("session_id", "")).startswith("seed:"))


class Emitter:
    """이벤트 봉투와 synthetic 실행 메타데이터를 조립한다."""

    def __init__(self, sink, persona_id, start, rng, context,
                 session_id=None, is_seed=False):
        self.sink, self.pid, self.t, self.rng = sink, persona_id, start, rng
        self.context = context
        self.sid = session_id or f"{context.simulation_run_id}:{uuid.uuid4().hex[:16]}"
        self.is_seed = is_seed
        self.pvid = ""
        self.n = 0
        self.page = "product_list"
        self.last_rec = None      # 직전 상세에서 노출한 (recommendation_id, [상품])
        self.last_banner = None   # 직전 목록에서 노출한 (recommendation_id, [배너], trait_source, algorithm)
        self.last_main = None     # 직전 목록의 추천 서버 메인 10 (recommendation_id, algorithm, [상품]) — Jira 221

    def tick(self, lo=200, hi=1500, rng=None):
        """시간을 흘린다.

        rng 를 넘기면 그 스트림에서 뽑는다. Quick Look 처럼 A/B 로 켜고 끄는
        동선은 반드시 전용 스트림을 넘겨야 한다 — 기본 스트림을 소비하면
        기능을 켠 것만으로 이후 궤적이 통째로 달라져 비교가 불가능해진다.
        """
        self.t += timedelta(milliseconds=int((rng or self.rng).integers(lo, hi)))

    def new_page(self, page_type):
        self.pvid = uuid.uuid4().hex[:16]
        self.page = page_type

    def emit(self, name, _pid=None, **props):
        self.n += 1
        # 선택 property가 없으면 key 자체를 보내지 않는다. ``string``으로 선언된
        # 선택값을 null로 보내는 것은 "미제공"이 아니라 타입 위반이다.
        # 예외: 배너 이벤트의 ``banner_value`` 는 DATA 계약(event-schema.json)이
        # required 로 두고 new_brand 칸은 null 을 요구한다 — 키를 남긴다 (Jira 213)
        properties = {k: v for k, v in props.items()
                      if v is not None or k in NULLABLE_REQUIRED_PROPS}
        # These fields are required for every synthetic Event.  Assign rather
        # than setdefault so an event-specific property cannot contradict the
        # run metadata carried by its Emitter.
        properties.update({
            "scenario_id": self.context.scenario_id,
            "simulation_run_id": self.context.simulation_run_id,
            "generator_type": self.context.generator_type,
        })
        if self.is_seed:
            properties["seeded"] = True

        self.sink.append({
            "schema_version": SCHEMA_VERSION,
            "event_id": uuid.uuid4().hex,
            "event_name": name,
            "intent": INTENT.get(name) or BANNER_INTENT[name],
            "occurred_at": self.t.isoformat(timespec="milliseconds") + "Z",
            "persona_id": self.pid,
            "session_id": self.sid,
            "page_view_id": self.pvid,
            "sequence_no": self.n,
            "page_type": self.page,
            "product_id": _pid,
            "actor_type": "synthetic",
            "environment": ENV,
            "properties": properties,
        })


# ── 상세 페이지 방문 ──────────────────────────────────────────────────────
def selectable_variants(product):
    """Return variants that can produce the same selection event as the Frontend.

    VariantPicker starts with the first variant selected and does not emit when it is
    clicked again, so only the remaining variants are valid simulated selections.
    """

    return list(product.get("variants") or [])[1:]


def visit_detail(e, gid, product, rec_ids, rng, depth_target, engaged,
                 entry_source, SC=SCENARIO, rec_meta=None):
    """depth_target = 도달할 최대 스크롤 %. 10% 단위로 로그를 남긴다

    rec_meta: 추천 카드를 눌러 들어왔을 때 {recommendation_id, list_id, position}.
              product_view 에 그대로 싣는다 (event-properties 의 선택 필드). 이게 있어야
              "추천에서 넘어온 고객" 을 세션 순서 추정 없이 셀 수 있다 (교차 브랜드 유입 · Jira 210).
              ⚠ 프론트(SimilarProducts -> startPageView) 는 아직 안 싣는다 — 계약이 허용하는 형태를
              생성기가 먼저 채운 것이고, 프론트가 따라오면 같은 모양이 된다.
    """
    e.new_page("product_detail")
    e.tick(300, 1200)
    e.emit("page_view", gid, navigation_source=entry_source)
    # 프론트가 상세 진입에서 page_view 직후 product_view 를 같은 page_view_id 로 남긴다
    # (frontend/src/lib/logger.ts 의 trackProductView). 둘 다 가중치 1.0 이라
    # 하나만 만들면 합성 로그가 실제 로그보다 상품당 1.0 만큼 가볍다.
    e.emit("product_view", gid, navigation_source=entry_source, **(rec_meta or {}))

    n_sec = max(1, round(len(DETAIL_LAYOUT) * depth_target / 100))
    depth = 0
    for si, (section, blocks) in enumerate(DETAIL_LAYOUT[:n_sec]):
        depth = min(depth_target, int((si + 1) / len(DETAIL_LAYOUT) * 100))
        e.tick(400, 2500)
        # 스크롤 진행 (10% 단위)
        e.emit("scroll_depth", gid, depth_percent=depth, section_id=section,
               content_kind=blocks[0][0], content_ref=blocks[0][1])
        # 스크롤 정지 — 읽고 있다는 신호
        if rng.random() < SC["p_scroll_pause"]:
            e.emit("scroll_pause", gid, section_id=section,
                   content_kind=blocks[0][0], content_ref=blocks[0][1],
                   visible_content_kinds=[b[0] for b in blocks[:3] if b[0]],
                   depth_percent=depth, direction="down",
                   distance_px=int(rng.integers(100, 1500)),
                   duration_ms=int(rng.integers(400, 2500)),
                   velocity_px_per_sec=int(rng.integers(200, 1200)))
        # 섹션 노출 — content_kind 단위로 쪼갠다
        expanded = []
        for kind, ref in blocks:
            if ref == "__rec__":
                for pos, rid in enumerate(rec_ids, 1):
                    expanded.append((kind, rid, pos))
            else:
                expanded.append((kind, ref, None))
        for kind, ref, pos in expanded:
            e.tick(30, 200)
            e.emit("section_view", gid, section_id=section, content_kind=kind,
                   content_ref=ref, visible_duration_ms=int(rng.integers(380, 1100)))
        # 유사 상품 섹션에 도달하면 추천 노출
        if section == "similar_products" and rec_ids:
            rec_batch = "rec-%s-%d" % (gid, int(rng.integers(10**10, 10**11)))
            # 무엇이 몇 번째로 노출됐는지 통째로 남긴다. 가중 0 이지만
            # 위치 편향 보정에 필요하다 — 아래 놓인 좋은 상품은 선호와 무관하게
            # 클릭이 적으므로, 클릭 로그를 그대로 학습에 쓰면 추천이 편향된다
            e.emit("recommendation_snapshot", None,
                   recommendation_id=rec_batch, list_id="similar_products",
                   algorithm="same_category_v0", size=len(rec_ids),
                   ranking=[{"product_id": r, "position": i}
                            for i, r in enumerate(rec_ids, 1)])
            for pos, rid in enumerate(rec_ids, 1):
                e.tick(20, 120)
                e.emit("recommendation_impression", rid,
                       recommendation_id=rec_batch, list_id="similar_products",
                       algorithm="same_category_v0", position=pos,
                       hold_ms=RECOMMENDATION_IMPRESSION_HOLD_MS,
                       visible_ratio=IMPRESSION_VISIBLE_RATIO)
                # 화면에 얼마나 머물렀나. 위쪽일수록 오래 보인다
                if rng.random() < SC["p_impression_dwell"]:
                    e.emit("impression_dwell", rid,
                           recommendation_id=rec_batch, list_id="similar_products",
                           algorithm="same_category_v0", position=pos,
                           visible_ms=int(rng.integers(400, 6000) / (1 + 0.15 * (pos - 1))))
            # 다음 상품을 추천으로 들어갈 수 있게 배치를 기억해 둔다.
            # 노출과 클릭이 같은 recommendation_id / position 을 써야 CTR 이 성립한다
            e.last_rec = (rec_batch, list(rec_ids))
        # 섹션 이탈 시 체류 시간 확정
        for kind, ref, pos in expanded:
            e.tick(30, 250)
            base_ms = rng.integers(800, 12000) if engaged else rng.integers(400, 3000)
            e.emit("section_dwell", gid, section_id=section, content_kind=kind,
                   content_ref=ref,
                   dwell_ms=int(base_ms * SC.get(f"dwell_x_{section}", 1.0)),
                   co_visible_blocks=len(expanded),
                   reason="left_viewport")

        if engaged and section == "about_product":
            if rng.random() < SC["p_accordion"]:
                e.tick(); e.emit("accordion_toggle", gid, section_id=section,
                                 content_kind="ingredient_list", action="expand")
            # 설명 문구를 긁는다. 이 섹션의 블록 중 하나를 고른다 — 향·제형 성향이
            # 오래 머무는 자리다(STYLE_EFFECT 의 scent 가 p_text_selection 을 올린다).
            # 성분 상자(ingredient_list·ingredient_callout)에 걸리면 성분이 같이 잡힌다.
            if rng.random() < SC["p_text_selection"]:
                kind, ref = blocks[int(rng.integers(0, len(blocks)))]
                emit_selection(e, gid, rng, SC, section, kind, ref,
                               with_ingredients=kind in ("ingredient_list", "ingredient_callout"))
        # 성분 표시 방식 전환. 성분을 신경 쓰는 페르소나일수록 자주 바꿔 본다
        # (SC 의 p_accordion 이 성향 6축의 ingredient 로 이미 조정돼 있다)
        if engaged and section == "ingredients":
            if rng.random() < SC["p_ingredient_mode"]:
                for m in ("raw", "chip")[:int(rng.integers(1, 3))]:
                    e.tick(300, 3000)
                    e.emit("ingredient_view_mode_change", gid,
                           section_id=section, mode=m)
            # 전성분에서 모르는 성분명을 긁는다. 성분을 따지는 페르소나일수록 자주
            # 긁는다 (STYLE_EFFECT 의 ingredient 가 p_ingredient_selection 을 2.2배까지).
            # 프론트 실측에서도 이 섹션의 드래그는 content_kind=ingredient_list 로 잡힌다.
            if rng.random() < SC["p_ingredient_selection"]:
                emit_selection(e, gid, rng, SC, section, "ingredient_list", None,
                               with_ingredients=True)

        if engaged and section == "product_hero":
            for idx in range(int(rng.integers(2, 8))):
                e.tick(150, 800)
                e.emit("media_view", gid, media_index=idx + 1, media_type="image")
            variants = selectable_variants(product)
            if variants and rng.random() < SC["p_variant_select"]:
                variant = variants[int(rng.integers(0, len(variants)))]
                e.tick(); e.emit("variant_select", gid,
                                 sku_id=variant["sku_id"], label=variant["label"],
                                 section_id=section, content_kind="variant_option")
        if engaged and section == "reviews":
            for _ in range(int(rng.integers(1, 5))):
                e.tick(); e.emit("review_expand", gid, section_id=section,
                                 content_kind="user_review", target="review_text")
            if rng.random() < SC["p_review_filter"]:
                e.tick(); e.emit("review_filter_apply", gid, section_id=section,
                                 content_kind="review_filter", filter="same_skin_type")
        # 되돌아 읽기
        if engaged and rng.random() < SC["p_scroll_backtrack"]:
            e.tick(); e.emit("scroll_backtrack", gid, section_id=section,
                             content_kind=blocks[0][0], content_ref=blocks[0][1],
                             depth_percent=max(0, depth - int(rng.integers(2, 8))),
                             distance_px=int(rng.integers(150, 400)))
    return depth


# ── 목록 페이지 체류 ──────────────────────────────────────────────────────
def browse_list(e, promo, grid, catalog, rng, dwell_ms, first,
                SC=SCENARIO, qrng=None, banners=None, reco=None, carted=None):
    """reco: 추천 서버 응답 (Jira 221). 주면 promo_row 가 서버 items 가 되고
    recommendation_snapshot · recommendation_impression(list_id=main) 을 서버 식별자로 낸다.
    banners 도 서버 값(banner_slot·trait_source 포함)이면 그대로 싣는다.

    carted: 주면 Quick Look 으로 담은 상품 id 를 여기에 넣는다. 세션이 결제할 때 장바구니에
            함께 올리기 위한 것이다 — 예전에는 담기만 하고 결제 목록에 못 들어가 **담았는데
            영영 안 사지는** 상품이 됐다 (09-17 실측: 등록 상품 담기 27건 중 20건이 이 경로)."""
    e.new_page("product_list")
    e.tick(300, 1200)
    if first:
        e.emit("session_start")
    e.emit("page_view", navigation_source="in_app" if not first else "session_start")

    blocks = []
    for section, kind in LIST_LAYOUT:
        refs = promo if section == "promo_row" else (grid if section == "product_grid" else [None])
        for r in refs:
            blocks.append((section, kind if r else None, r))
    for section, kind, ref in blocks:
        e.tick(30, 200)
        # 목록 페이지의 envelope product_id 는 null 이다 (logger.ts:149 — 페이지 컨텍스트에서 채움).
        # 카드 식별은 content_ref 로만 남는다. 그리드 체류는 상품에 귀속되지 않는다.
        e.emit("section_view", None, section_id=section, content_kind=kind,
               content_ref=ref, visible_duration_ms=int(rng.integers(380, 900)))
    # 목록 노출 — 화면에 보이는 상품 전부
    for pos, g in enumerate(grid, 1):
        e.tick(20, 120)
        e.emit("product_impression", g, position=pos, list_id="list_grid",
               hold_ms=LIST_IMPRESSION_HOLD_MS,
               visible_ratio=IMPRESSION_VISIBLE_RATIO)
        # 노출 대비 클릭을 재려면 "얼마나 보였나" 가 있어야 한다. 가중 0 이다.
        # 노출 정책은 여기에 싣는다 — 계약이 impression_dwell 의 선택 필드로
        # algorithm 을 허용한다 (product_impression 에는 그 필드가 없다).
        if rng.random() < SC["p_impression_dwell"]:
            e.emit("impression_dwell", g, position=pos,
                   list_id="list_grid", algorithm=EXPOSURE_NAME,
                   visible_ms=int(rng.integers(400, 5000) / (1 + 0.12 * (pos - 1))))
    # 추천 서버의 메인 목록 (Jira 221) — 프론트 184 와 같은 자리(맞춤 기획전 행 = items 10).
    # recommendation_snapshot 1건 + 칸마다 recommendation_impression. 식별자는 서버 응답 그대로
    if reco:
        items = reco.get("items") or []
        e.emit("recommendation_snapshot", None,
               recommendation_id=reco["recommendation_id"], list_id=MAIN_LIST_ID,
               algorithm=reco["algorithm"], size=len(items),
               ranking=[{"product_id": it["product_id"], "position": it["position"],
                         "score": it.get("score")} for it in items])
        for it in items:
            e.tick(20, 120)
            e.emit("recommendation_impression", it["product_id"],
                   recommendation_id=reco["recommendation_id"], list_id=MAIN_LIST_ID,
                   algorithm=reco["algorithm"], position=it["position"],
                   hold_ms=LIST_IMPRESSION_HOLD_MS, visible_ratio=IMPRESSION_VISIBLE_RATIO)
        e.last_main = (reco["recommendation_id"], reco["algorithm"],
                       [it["product_id"] for it in items])
    # 배너 노출 — 칸마다 banner_impression. 클릭과 같은 recommendation_id / banner_slot 을
    # 써야 배너 CTR(banner_daily) 이 성립한다. 프론트 useImpression.ts 의 property 와 같다.
    # 서버 응답(reco)이 있으면 recommendation_id·algorithm·trait_source 는 서버 값이다
    if banners:
        if reco:
            batch, algo = reco["recommendation_id"], reco["algorithm"]
            source = None                       # 칸마다 서버가 준 trait_source
        else:
            batch, algo = "banner-%d" % int(rng.integers(10**10, 10**11)), BANNER_ALGO
            source = trait_source_of(first, rng, SC)
        e.last_banner = (batch, banners, source, algo)
        for b in banners:
            e.tick(20, 120)
            e.emit("banner_impression", b["product_id"],
                   recommendation_id=batch, list_id=BANNER_LIST_ID, algorithm=algo,
                   position=b["slot"], banner_type=b["type"], banner_value=b["value"],
                   banner_slot=b["slot"], trait_source=source or b.get("trait_source"),
                   policy_version=BANNER_POLICY_VERSION,
                   hold_ms=LIST_IMPRESSION_HOLD_MS, visible_ratio=IMPRESSION_VISIBLE_RATIO)
    # Quick Look — 카드 호버 후 버튼을 눌러 요약 창을 연다.
    # 창은 목록 위에 뜨므로 page_type / page_view_id 는 그대로다.
    # qrng 가 None 이면 이 동선 자체가 없다 (A/B 의 대조군)
    if qrng is not None:
        for pos, g in enumerate(grid, 1):
            if qrng.random() >= SC["p_quick_look"]:
                continue
            e.tick(200, 1500, rng=qrng)
            # 계약상 quick_look 의 필수 property 는 entry_source 와 position 이다.
            # 프론트도 목록에서 열면 entry_source=list_grid 를 싣는다
            e.emit("quick_look", g, position=pos,
                   entry_source="list_grid", list_id="list_grid")
            variants = selectable_variants(catalog[g])
            selected_variants = []
            if variants and qrng.random() < SC["p_ql_variant"]:
                n_var = min(int(qrng.integers(1, 4)), len(variants))
                indexes = qrng.choice(len(variants), size=n_var, replace=False)
                selected_variants = [variants[int(index)] for index in np.atleast_1d(indexes)]
                for variant in selected_variants:
                    e.tick(200, 1200, rng=qrng)
                    e.emit("variant_select", g, sku_id=variant["sku_id"],
                           label=variant["label"], entry_source="quick_look")
            n_var = len(selected_variants)
            added = qrng.random() < SC["p_ql_add"]
            wished = qrng.random() < SC["p_ql_wish"]
            if added:
                e.tick(300, 2000, rng=qrng)
                e.emit("add_to_cart", g, quantity=1, **price_props(catalog, g),
                       entry_source="quick_look")   # 다른 담기 5곳과 같이 가격 속성 (Jira 342)
                if carted is not None:
                    # 결제 목록에 올릴 수 있게 알린다. **어느 세션에서 담았는지 같이** 남긴다 —
                    # 앞선 방문에서 담은 것을 마지막 세션에서 결제하면 마트가 (상품,날짜) 단위로
                    # 담기 세션 0 · 결제 세션 1 을 보게 된다 (Jira 371)
                    carted.append((g, e.sid))
            if wished:
                e.tick(200, 1200, rng=qrng)
                e.emit("wishlist_toggle", g, action="add", entry_source="quick_look")
            dwell = int(qrng.integers(1200, 25000))
            e.tick(200, 1500, rng=qrng)
            # 닫는 방식. Frontend QuickLook과 같은 enum을 사용한다.
            e.emit("quick_look_close", g,
                   close_reason=str(qrng.choice(["backdrop", "escape", "close_button", "open_detail"],
                                                p=[0.42, 0.13, 0.35, 0.10])),
                   dwell_ms=dwell, variants_viewed=n_var,
                   added_to_cart=bool(added), wishlisted=bool(wished))

    if rng.random() < SC["p_list_filter"]:
        e.tick(); e.emit("filter_change", filter_kind="category", filter_value="all")
    if rng.random() < SC["p_list_sort"]:
        e.tick(); e.emit("sort_change", sort_key="popular")

    # 15초마다 checkpoint dwell 재발화 (프론트 실측 동작)
    for _ in range(int(dwell_ms // CHECKPOINT_MS)):
        for section, kind, ref in blocks:
            e.tick(5, 40)
            e.emit("section_dwell", None, section_id=section, content_kind=kind,
                   content_ref=ref, dwell_ms=CHECKPOINT_MS,
                   co_visible_blocks=len(blocks), reason="checkpoint")
    for section, kind, ref in blocks:
        e.tick(5, 40)
        e.emit("section_dwell", None, section_id=section, content_kind=kind,
               content_ref=ref, dwell_ms=int(dwell_ms % CHECKPOINT_MS) + 500,
               co_visible_blocks=len(blocks), reason="page_leave")


# ── 수집 API 전송 ─────────────────────────────────────────────────────────
BATCH = 100          # 백엔드 EventBatchRequest 의 @Size(max = 100)


def post_events(base_url, events, rps=0, timeout=40):
    """수집 API 로 배치 전송. (성공 건수, 실패 건수, 초) 를 돌려준다

    백프레셔 처리는 simulator/collector_client.py 가 한다 — 429 의 Retry-After 를
    존중하고, 503 은 지수 백오프로 재시도하고, 413 이면 배치를 반으로 줄인다.
    에이전트 러너도 같은 클라이언트를 쓴다. 같은 서버에 같은 계약으로 보내면서
    클라이언트마다 다르게 굴면 부하 테스트 결과를 해석할 수 없다.

    타임아웃이 넉넉한 이유 — Kafka 가 안 떠 있으면 백엔드가 발행을 기다리다
    25초쯤 뒤에 503 을 준다. 짧게 잡으면 클라이언트가 먼저 끊어져서
    "타임아웃" 으로만 보이고 진짜 원인(503)을 못 본다.
    """
    sys.path.insert(0, os.path.join(ROOT, "simulator"))
    from collector_client import CollectorClient

    client = CollectorClient(base_url, timeout=timeout, rps=rps,
                             max_batch=BATCH, log=log)
    t0 = time.time()
    client.send(events, schema_version=SCHEMA_VERSION)
    st = client.stats
    log(client.summary())
    return st["sent"], st["dropped"] + st["gave_up"], time.time() - t0


# ── 결제 (Jira 312) ────────────────────────────────────────────────────────
#
# 담기까지만 만들면 퍼널의 끝과 재구매·구매 사유 마트가 빈다. 프론트가 결제할 때 남기는 순서를 그대로 따른다:
#   cart 화면 → begin_checkout(items·cart_value·currency) → purchase(order_id·items·payment_method·paid_value·
#   order_channel·order_value·currency) → purchase_reason_select(order_id·reasons·primary_reason | skipped)
# 금액 단위는 이벤트 계약대로 USD (데이터 티켓 303 이 원화로 옮기기 전까지). order_channel 은 `backend` —
# 합성 로그는 백엔드 주문 API 를 거친 것으로 본다(`local` 은 브라우저만의 시연 주문이라 매출 집계에서 빠진다).
PURCHASE_REASONS = ("ingredient", "skin_fit", "reviews", "review_same_skin", "price",
                    "brand_trust", "texture_finish", "clean_claim", "recommendation", "restock")
# 재구매가 아닐 때의 이유 분포 [추정] — 성분·피부 적합·리뷰가 앞, 추천은 낮게(추천 경유 비율은 노출 정책이 정한다)
REASON_WEIGHTS = (0.20, 0.18, 0.16, 0.10, 0.12, 0.08, 0.07, 0.04, 0.05, 0.0)


def _pick_reasons(rng, restock):
    """1~2개. 재구매면 restock 이 첫 번째. 같은 값을 두 번 넣지 않는다."""
    if restock:
        picked = ["restock"]
    else:
        w = np.array(REASON_WEIGHTS) / sum(REASON_WEIGHTS)
        picked = [str(rng.choice(PURCHASE_REASONS, p=w))]
    if rng.random() < 0.35:
        rest = [r for r in PURCHASE_REASONS if r not in picked and r != "restock"]
        picked.append(str(rng.choice(rest)))
    return picked


def price_props(catalog, g):
    """add_to_cart / remove_from_cart 의 가격 속성. 계약 §4.5 선택 필드 안에서 통화를 가른다 (Jira 303).
    USD: price_usd (예전 그대로) · KRW: unit_price + currency="KRW" — 필드 이름을 새로 만들지 않는다"""
    if CURRENCY == CURRENCY_KRW:
        return {"unit_price": money(catalog[g]["price"], catalog[g].get("price_krw")), "currency": CURRENCY_KRW}
    return {"price_usd": catalog[g]["price"]}


def checkout(e, catalog, gids, rng, SC, quantities=None, restock=False):
    """cart 화면에서 결제까지. 돌려주는 것: 구매했으면 order_id, 실패·취소면 None.

    gids 는 결제할 상품 id 들(장바구니 전체가 아니다 — 시드 상품은 이미 과거에 산 것이라 다시 결제하지 않는다).
    quantities 는 {gid: n}, 없으면 1. Emitter 가 시드면 seeded=True 가 자동으로 붙는다.
    """
    quantities = quantities or {}
    items = [{"product_id": g, "quantity": int(quantities.get(g, 1)),
              "unit_price": money(catalog[g]["price"], catalog[g].get("price_krw"))} for g in gids]
    order_value = round(sum(it["quantity"] * it["unit_price"] for it in items), 2)
    order_id = f"ord-{uuid.uuid4().hex[:16]}"
    methods, weights = zip(*SC["payment_methods"])
    method = str(rng.choice(methods, p=np.array(weights) / sum(weights)))

    if e.page != "cart":
        e.new_page("cart")
        e.tick(); e.emit("page_view", navigation_source="in_app")
    e.tick(800, 5000)
    e.emit("begin_checkout", items=items, cart_value=order_value, currency=CURRENCY)
    e.tick(3000, 20000)                      # 결제창
    if rng.random() < SC["p_payment_failed"]:
        e.emit("payment_failed", order_id=order_id, reason_code="user_cancel", payment_method=method)
        return None
    if rng.random() < SC["p_discount"]:
        paid = (int(round(order_value * 0.9 / 100) * 100) if CURRENCY == CURRENCY_KRW      # 원화는 100원 단위 할인
                else round(order_value * 0.9, 2))
    else:
        paid = order_value
    e.emit("purchase", order_id=order_id, items=items, payment_method=method, paid_value=paid,
           order_channel="backend", order_value=order_value, currency=CURRENCY)
    e.tick(1500, 8000)
    if rng.random() < SC["p_reason_answer"]:
        reasons = _pick_reasons(rng, restock)
        e.emit("purchase_reason_select", order_id=order_id, reasons=reasons,
               primary_reason=reasons[0], skipped=False)
    else:
        e.emit("purchase_reason_select", order_id=order_id, reasons=[], skipped=True)
    return order_id


def validate_property_contract(events):
    """Fail before file output or HTTP delivery when generated properties drift."""

    from contracts.coverage_report import check_properties, parse_property_contract

    spec, enums, source = parse_property_contract(PROPERTIES_CONTRACT)
    if source is None:
        raise RuntimeError(f"Properties contract not found: {PROPERTIES_CONTRACT}")

    result = check_properties(events, spec, enums)
    violation_count = sum(result["events_with_violations"].values())
    if violation_count:
        details = []
        if result["missing"]:
            (event_name, field), count = result["missing"][0]
            details.append(f"missing {event_name}.{field} ({count})")
        if result["invalid_types"]:
            (event_name, field, expected, actual), count = result["invalid_types"][0]
            details.append(
                f"type {event_name}.{field} {expected}/{actual} ({count})"
            )
        if result["invalid_enums"]:
            (event_name, field, value), count = result["invalid_enums"][0]
            details.append(f"enum {event_name}.{field}={value} ({count})")
        raise ValueError(
            f"Event Properties 계약 위반 {violation_count:,}건: " + "; ".join(details)
        )
    return result


# ── grain 단위 노출·클릭 가드 (Jira 358, 데이터 파트 요청 2026-09-18) ──────
#
# 총량이 맞아도 특정 grain 에서 클릭 > 노출이 날 수 있다. Q5 는 마트 grain
# (event_date_kst, brand_id, product_id, 실행축) 으로 보므로 총량 점검으로는 안 잡힌다.
# 09-18 리포트의 banner_daily ctr>1 1행이 python_batch 로 잡힌 것이 그 예다.
#
# 분자가 분모보다 크면 대시보드에 "클릭률 233%" 가 뜨고 사장님이 그 화면 전체를 못 믿는다.
# 같은 사고가 Jira 277 에서 이미 났다 (add_to_cart_rate 1,248행 중 323행이 1.0 초과).
#
# 프론트는 A안(클릭이 있으면 노출 1을 합성)으로 이 문제를 로거에서 막지만, 생성기는
# 프론트 로거를 타지 않으므로 여기서 직접 막는다.
# 분모는 **마트와 같게** 잡는다 (dw-schema.md §4.1 — "노출 Event는 셋이고 분모는 그 합이다").
# product_click 을 product_impression 하나와만 짝지으면 가드가 실제 화면보다 엄격해진다 —
# 유사 상품 레일은 카드 하나에 recommendation_impression 만 내고 product_click 을 함께 내기
# 때문이다(frontend SimilarProducts.tsx select(): confirmImpressionByClick 은 recommendation_impression,
# 그 뒤 track('product_click')). 그 화면 동선을 생성기가 그대로 만들면 1:1 가드에만 걸린다.
# recommendation_click · banner_click 은 각자의 CTR 분모가 따로 있으므로 1:1 그대로 둔다.
IMPRESSION_EVENTS_FOR_CTR = ("product_impression", "recommendation_impression", "banner_impression")
CTR_PAIRS = (
    (IMPRESSION_EVENTS_FOR_CTR, "product_click"),
    (("recommendation_impression",), "recommendation_click"),
    (("banner_impression",), "banner_click"),
)


def _grain_of(event):
    """Q5·마트가 보는 grain. 날짜는 occurred_at 의 날짜 부분으로 근사한다.

    정제가 KST 로 옮기므로 경계에서 하루가 어긋날 수 있다. 여기서 잡고 싶은 것은
    "같은 상품·같은 날에 노출 없이 클릭이 났다" 이고 경계 오차는 그 판정을 뒤집지 않는다.
    """
    p = event.get("properties") or {}
    return (
        (event.get("occurred_at") or "")[:10],
        p.get("brand_id"),
        event.get("product_id") or p.get("product_id"),
        p.get("actor_type"), p.get("source"), p.get("generator_type"),
        p.get("scenario_id"), p.get("simulation_run_id"),
    )


def check_ctr_grains(events):
    """grain 마다 노출 >= 클릭 인지 본다. 어긋난 grain 목록을 돌려준다."""
    from collections import Counter

    bad = []
    for impression_names, click_name in CTR_PAIRS:
        imps, clks = Counter(), Counter()
        for e in events:
            name = e.get("event_name")
            if name in impression_names:
                imps[_grain_of(e)] += 1
            elif name == click_name:
                clks[_grain_of(e)] += 1
        label = "+".join(impression_names)
        for grain, n_click in clks.items():
            n_imp = imps.get(grain, 0)
            if n_click > n_imp:
                bad.append({"pair": f"{click_name} > {label}",
                            "grain": grain, "clicks": n_click, "impressions": n_imp})
    return bad


def validate_ctr_grains(events, strict=True):
    """클릭이 노출을 넘는 grain 이 있으면 파일로 내보내기 전에 멈춘다.

    계약 위반(validate_property_contract)과 같은 강도로 다룬다 — 어긋난 로그가 파일에
    들어가면 3시간 뒤 Q5 에서야 드러나고, 그때는 마트를 다시 만들어야 한다.
    """
    bad = check_ctr_grains(events)
    if not bad:
        return bad
    head = bad[0]
    detail = (f"{head['pair']} — 클릭 {head['clicks']} vs 노출 {head['impressions']}"
              f" · grain {head['grain']}")
    if strict:
        raise ValueError(
            f"grain 단위 노출·클릭 위반 {len(bad):,}건: {detail}"
            " (허용하려면 --allow-ctr-grain-violations)"
        )
    log(f"[경고] grain 단위 노출·클릭 위반 {len(bad):,}건 — {detail}")
    return bad


# ── 노출 정책 ────────────────────────────────────────────────────────────
#
# 사람은 위에 있는 것을 본다. 그런데 지금까지 이 생성기는 전원에게 같은 인기순
# 화면을 보여줬다 — 건성인 사람과 지성인 사람이 같은 상품을 봤다. 실제 쇼핑몰은
# 추천이 진열에 영향을 주므로, 노출을 추천 점수로 정하는 정책을 함께 둔다.
#
# **노출만 추천이 정한다. 행동은 hidden preference 가 정한다.**
# 둘 다 추천이 정하면 추천이 자기가 띄운 것을 자기가 맞히는 로그가 되어
# 아무것도 측정할 수 없다.
#
# 이렇게 만든 로그로 추천 정확도를 재지 않는다. 정책이 바뀌면 숫자가 같이
# 움직여서 "추천이 좋아졌는가" 와 "노출을 많이 했는가" 가 섞이기 때문이다.
# 대표 정확도는 리뷰 이력 기반 오프라인 평가가 계속 담당한다.
# 이 로그는 노출 대비 클릭·전환·커버리지를 정책끼리 비교하는 데 쓴다.
EXPOSURE_POPULAR = "popular_v0"
EXPOSURE_CBF = "cbf_v1"
# 이번 실행의 정책. 노출 이벤트에 실어 두지 않으면 나중에 정책이 다른 로그를
# 구분할 방법이 없다 (properties 는 계약상 자유 필드라 스키마 변경이 없다)
EXPOSURE_NAME = EXPOSURE_POPULAR

# 후보 구성. eval_dynamic.py 와 **같은 비율(추천 50% + 카테고리 25% + 무작위 25%)**
# 이다 — 추천 Top 만 보면 추천이 자기가 고른 것만 채점하게 된다.
# 개수는 목록 화면 크기에서 유도한다. 이 pool 이 이탈 상품뿐 아니라 **목록 카드
# PAGE_SIZE 칸**을 그리는 데도 쓰이므로, 한 칸을 빼고도 남아야 한다.
POOL_SIZE = PAGE_SIZE * 2
POOL_MIX = {"top": POOL_SIZE // 2,
            "category_popular": POOL_SIZE // 4,
            "random": POOL_SIZE - POOL_SIZE // 2 - POOL_SIZE // 4}


class CbfExposure:
    """추천 점수로 방문 후보를 뽑는다. 무엇을 고를지가 아니라 무엇이 보일지를 정한다.

    **정본 서빙과 같은 점수를 써야 한다** (2026-09-07). 여기가 CBF 단독이면
    생성기는 **이미 없는 시스템의 화면**을 만든다 — 그 로그로 잰 노출 정책·퍼널
    수치가 전부 다른 알고리즘 이야기가 된다. 그래서 브랜드 폴백과 CF 가점을
    정본과 똑같이 켠다 (계약 §4-1).

    산출물(`item_cooc.npz`)이 없으면 CF 항이 통째로 꺼지고 경고를 찍는다.
    조용히 꺼지면 "CF 를 켠 로그" 라고 부른 것이 사실은 CBF 로그가 된다.
    """

    def __init__(self, catalog):
        sys.path.insert(0, os.path.join(ROOT, "batch", "jobs"))
        from product_encoder import Encoder, brand_key
        from persona_feature import load as load_affinity
        from recommender import Recommender, load_cooc
        from user_vector import UserVector
        self.UserVector = UserVector
        enc = Encoder()
        self.M = np.asarray(enc.matrix(), np.float32)
        self.index = {x["product_id"]: i for i, x in enumerate(enc.products)}
        self.prior = np.asarray(enc.prior(), dtype=np.float32)
        cooc, supporters = load_cooc()
        if cooc is None:
            print("⚠️ item_cooc.npz 가 없어 CF 가점 없이 노출을 만듭니다 — "
                  "`python batch/jobs/build_cooc.py` 를 먼저 도십시오",
                  file=sys.stderr)
        self.rec = Recommender(self.M, self.index, self.prior,
                               affinity=load_affinity(self.index),
                               brands=[brand_key(x) for x in enc.products],
                               known_brands=set(enc.blk["brand"]["vocab"]),
                               cooc=cooc, supporters=supporters)
        self.ids = [None] * len(self.index)
        for g, i in self.index.items():
            self.ids[i] = g

    def pool(self, persona, seeds, seen, cat, by_cat, rng, n):
        """seen 은 후보에서 제외할 상품(시드·정답 등). cat 은 같은 카테고리 축이다."""
        state = self.UserVector()
        for gid in seeds:                       # 시드는 이미 좋아한 상품이다
            if gid in self.index:
                state.observe({"event_name": "add_to_cart", "product_id": gid,
                               "properties": {}})
        scores = self.rec.score(state, persona=persona)
        order = [self.ids[i] for i in np.argsort(-scores)]
        order = [g for g in order if g not in seen]

        pool = order[:POOL_MIX["top"]]
        same_cat = [g for g in order if g in set(by_cat.get(cat, [])) and g not in pool][:20]
        if same_cat:
            pool += list(rng.choice(same_cat,
                                    size=min(POOL_MIX["category_popular"], len(same_cat)),
                                    replace=False))
        rest = [g for g in order if g not in pool]
        if rest:
            pool += list(rng.choice(rest, size=min(POOL_MIX["random"], len(rest)),
                                    replace=False))
        pool = list(dict.fromkeys(pool))
        return pool[:n] if n else pool


# ── 페르소나 1명 ─────────────────────────────────────────────────────────
def gen_persona(p, catalog, by_cat, popular, rng, sink, context,
                quick_look=True, hidden=None, exposure=None):
    SC = persona_style(p)
    # Quick Look 전용 난수. persona_id 로만 결정되므로 본 동선 rng 와 독립이다.
    # 덕분에 quick_look=False 로 껐을 때 나머지 궤적이 **완전히 동일**하고,
    # 두 조건의 차이가 Quick Look 하나로만 설명된다 (대응 설계).
    qrng = (np.random.default_rng(zlib.crc32(p["persona_id"].encode()))
            if quick_look else None)
    # 상품별 평점 평균으로 극성을 가른다. 4~5점 긍정 / 1~2점 부정 / 3점 중립
    #   긍정 시드 -> add_to_cart 로 환산해 v_u+ 에 넣는다
    #   부정 시드 -> "들어갔다 그냥 나감" 으로 재현한다. v_u+ 에 넣지 않는다
    #   중립     -> 아무 데도 넣지 않는다 (본 적 있는 상품으로만 취급)
    rat = {}
    for r in p["reviews"]:
        g = r["group_id"]
        if g in catalog:
            rat.setdefault(g, []).append(r["rating"])
    seq = [g for g in dict.fromkeys(r["group_id"] for r in p["reviews"]) if g in catalog]
    pos = [g for g in seq if sum(rat[g]) / len(rat[g]) >= POS_MIN]
    neg = [g for g in seq if sum(rat[g]) / len(rat[g]) <= NEG_MAX]
    if len(pos) < 3:
        return None
    seeds, target = pos[:-1], pos[-1]

    # 시드 — 시뮬레이션 시작 전 상태. 상대 순서 유지하며 최근 WINDOW_DAYS 로 압축
    base = NOW - timedelta(days=SC["window_days"])
    step = SC["window_days"] * 0.7 / max(len(seeds) + len(neg), 1)

    # 부정 시드 — 상세를 얕게 보고 이탈. 감점 이벤트가 v_u- 를 채운다
    for j, g in enumerate(neg):
        e = Emitter(
            sink,
            p["persona_id"],
            base + timedelta(days=step * j),
            rng,
            context,
            session_id=seed_session_id(context, p["persona_id"], g),
            is_seed=True,
        )
        # new_page / page_view 는 visit_detail 이 낸다. 여기서 또 내면 상세 진입 한 번에
        # page_view 가 2건, page_view_id 가 2개 생겨 프론트와 어긋난다.
        # 시드 표시는 Emitter가 모든 seed Event에 seeded=true로 남긴다.
        visit_detail(e, g, catalog[g], [], rng,
                     depth_target=int(rng.choice(SC["neg_seed_depth_choices"])),
                     engaged=False, entry_source="direct", SC=SC)
        e.tick(); e.emit("scroll_backtrack", g, section_id="about_product",
                         depth_percent=int(rng.integers(10, 30)),
                         distance_px=int(rng.integers(150, 400)), seeded=True)
        if rng.random() < SC["neg_seed_p_rage"]:
            e.tick(); e.emit("rage_click", g, section_id="product_hero",
                             click_count=int(rng.integers(3, 6)), seeded=True)

    # 같은 상품에 리뷰가 몇 건인지 — 2건 이상이면 재구매다 (S2)
    n_reviews_of = Counter(r["group_id"] for r in p["reviews"])

    for i, g in enumerate(seeds):
        first_at = base + timedelta(days=step * (len(neg) + i))
        # 재구매 쌍(같은 상품 리뷰 2건+)은 **시드 표시 없이** 낸다 (Jira 327). 마트 계약이 is_seeded 행을
        # 빼기 때문에 시드로 두면 재구매율이 영원히 0 이다. 추천 서버는 seeded 를 안 보므로 상태는 같다.
        # 날짜는 그대로 과거(85일 창 안)라 마트의 90일 재구매 창에 첫 구매·재구매가 함께 든다.
        repurchase = n_reviews_of.get(g, 1) >= 2
        sid = (history_session_id if repurchase else seed_session_id)(context, p["persona_id"], g)
        e = Emitter(
            sink,
            p["persona_id"],
            first_at,
            rng,
            context,
            session_id=sid,
            is_seed=not repurchase,
        )
        if repurchase:
            history_detail_entry(e, g)          # hist: 세션은 상세를 열고 담는다 (Jira 345)
        else:
            e.new_page("product_detail")        # 시드는 조회 없이 담기만 (계약 event-properties-schema §시드)
        e.emit("add_to_cart", g, quantity=1, **price_props(catalog, g),
               **({} if repurchase else {"seeded": True}))
        # 시드는 과거 구매다(리뷰를 썼다 = 샀다). 담기에서 끝내면 purchase_fact 가 비어 재구매 마트가 0 이 된다 (Jira 312)
        checkout(e, catalog, [g], rng, SC)

        # ── S2. 재구매 — 같은 상품을 시간 간격을 두고 다시 산다 ──────────────
        # 리뷰를 두 번 쓴 것은 두 번 샀다는 뜻이다. 지금까지 `dict.fromkeys` 가
        # 중복을 뭉개 **한 번 산 것으로 보이고 있었다.**
        #
        # 세션을 **따로** 만든다. 같은 세션에서 두 번 담으면 그것은 재구매가
        # 아니라 수량 변경이다.
        for k in range(1, min(n_reviews_of.get(g, 1), 3)):
            gap = float(rng.integers(*SC["restock_gap_days"])) * k
            at = first_at + timedelta(days=gap)
            if at >= NOW:
                break                       # 창 밖으로 나가면 만들지 않는다
            re = Emitter(
                sink,
                p["persona_id"],
                at,
                rng,
                context,
                session_id=history_session_id(context, p["persona_id"], f"{g}#restock{k}"),
                is_seed=False,                  # 재구매는 비시드 (Jira 327)
            )
            history_detail_entry(re, g)         # 재구매도 hist: 세션 — 상세를 열고 담는다 (Jira 345)
            re.emit("add_to_cart", g, quantity=1, **price_props(catalog, g))
            checkout(re, catalog, [g], rng, SC, restock=True)     # 재구매 = 두 번째 결제, 사유는 restock

    # 이탈 상품 — **노출**로 고른다. 취향으로 고르지 않는다.
    #   popular_v0  같은 카테고리 -> 인기순. 전원이 같은 화면을 본다
    #   cbf_v1      추천 점수가 후보의 절반을 정한다. 사람마다 다른 화면을 본다
    # 어느 쪽이든 고른 뒤의 행동(체류·담기)은 hidden preference 가 정한다.
    regret = None          # 담았다 뺄 이탈 상품 (최대 1개)
    discovered = []        # 리뷰 이력 없이 담은 등록 브랜드 상품 (신규 브랜드 발견 구매)
    ql_carted = []         # Quick Look 으로 담은 상품 — 결제 목록에 올린다
    cat = catalog[target]["cat"]
    n_bounce = int(rng.integers(*SC["bounce_range"]))
    if exposure is not None:
        # 시드만 준다 — target 은 정답이라 노출 계산에 넣지 않는다
        pool = exposure.pool(p, seeds, set(seq), cat, by_cat, rng, n=None)
        bounce = pool[:n_bounce]
    else:
        pool = [g for g in by_cat.get(cat, []) if g not in seq]
        pool += [g for g in popular if g not in seq and g not in pool]
        bounce = list(rng.choice(pool, size=min(n_bounce, len(pool)), replace=False))

    # ── S3. 최근 며칠에 걸친 1~3회 방문 ─────────────────────────────────
    # 한 세션에 다 몰아넣으면 "다시 온 사람" 을 셀 수 없다. route 를 쪼개
    # 세션 경계를 만들고, 각 세션을 최근 `revisit_window_days` 안에 흩는다.
    #
    # **장바구니와 찜은 세션을 넘어 유지된다** — 그게 재방문의 의미다.
    # 반면 `last_rec` 은 끊는다. 지난 세션에 뜬 추천을 이번 세션에서 누를 수 없다.
    route = list(bounce) + [target]
    n_visits = int(rng.choice([1, 2, 3], p=SC["visit_weights"]))
    n_visits = min(n_visits, len(route))
    splits = set()
    if n_visits > 1:
        splits = {int(x) for x in rng.choice(range(1, len(route)),
                                             size=n_visits - 1, replace=False)}
    # 세션 시작 시각 — 오래된 것부터. 마지막 방문이 가장 최근이다
    starts = sorted((float(x) for x in
                     rng.random(n_visits) * SC["revisit_window_days"]),
                    reverse=True)

    def new_visit(day_offset):
        return Emitter(sink, p["persona_id"],
                       NOW - timedelta(days=day_offset), rng, context)

    visit_i = 0
    e = new_visit(starts[0])
    promo = popular[:PROMO_SIZE]
    liked = False
    visited = set()
    sync_from = len(sink)          # 추천 서버에 아직 안 넘긴 이벤트의 시작 (Jira 221)
    for i in range(len(route)):
        if i in splits:
            visit_i += 1
            e = new_visit(starts[min(visit_i, len(starts) - 1)])
        g = route[i]
        # 직전 상세에서 추천이 노출됐다면, 목록으로 돌아가는 대신 그 추천을 눌러
        # 다음 상품으로 넘어간다. 이때 다음 상품을 **추천 목록에서 고른다** —
        # 이탈 상품은 원래 노출로 고르기로 한 것이고, 추천도 노출이다.
        # 목표 상품은 반드시 마지막에 와야 하므로 바꾸지 않는다.
        via_rec = False
        if (e.last_rec is not None and g != target
                and rng.random() < SC["p_rec_click"]):
            cand = [x for x in e.last_rec[1]
                    if x not in seq and x not in visited and x != target]
            if cand:
                g = cand[0]          # 추천 목록 상위부터 (위치 편향을 그대로 재현)
                route[i] = g
                via_rec = True
        visited.add(g)
        rec_meta = None
        if via_rec:
            rec_batch, rec_list = e.last_rec
            pos = rec_list.index(g) + 1
            e.tick(); e.emit("recommendation_click", g,
                             recommendation_id=rec_batch, list_id="similar_products",
                             algorithm="same_category_v0",
                             position=pos)
            e.tick(); e.emit("product_click", g, entry_source="similar_products",
                             position=pos)
            # 상세 진입 product_view 에도 같은 식별자를 싣는다 — 추천 경유 추적 (Jira 210)
            rec_meta = {"recommendation_id": rec_batch, "list_id": "similar_products",
                        "position": pos}
        else:
            # size 를 pool 길이로 잡으면 g 를 뺀 만큼 모자라 죽는다
            cards = [x for x in pool if x != g] or list(pool)
            grid = list(rng.choice(cards, size=min(PAGE_SIZE, len(cards)),
                                   replace=False))
            grid = [g] + [x for x in grid if x != g]
            # ── 추천 서버 연동 (Jira 221) ──
            # 지금까지의 행동을 서버 상태에 넘기고 실제 추천을 받는다. 배너·메인 카드 클릭은
            # **서버가 실제로 노출한 상품** 중에서 고른다 — 프론트와 같은 경로.
            reco, via_main = None, False
            if RECO is not None and RECO.available:
                RECO.observe(p["persona_id"], sink[sync_from:])
                sync_from = len(sink)
                reco = RECO.recommend(p["persona_id"])
            if reco:
                banners = hero_from_response(reco) if BANNER_EVENTS else None   # 화면 = 히어로 하나
                shown_b = [b["product_id"] for b in (banners or [])
                           if b["product_id"] not in seq and b["product_id"] not in visited]
                shown_m = [it["product_id"] for it in reco.get("items") or []
                           if it["product_id"] not in seq and it["product_id"] not in visited]
                via_banner = bool(shown_b) and g != target and rng.random() < SC["p_banner_click"]
                if via_banner:
                    g = shown_b[0]; route[i] = g
                elif shown_m and g != target and rng.random() < SC["p_rec_click"]:
                    via_main = True
                    g = shown_m[0]; route[i] = g          # 메인 상위부터 (위치 편향 재현)
                visited.add(g)
                grid = [g] + [x for x in grid if x != g]
                promo_now = [it["product_id"] for it in reco.get("items") or []] or promo
            else:
                # 배너 경유 — 이번 상품을 배너 축 칸에 넣어 두고 그 배너를 누른다 (Jira 212)
                via_banner = BANNER_EVENTS and g != target and rng.random() < SC["p_banner_click"]
                banners = (make_banners(p, catalog, pool, popular, rng,
                                        force=g if via_banner else None, exclude=set(seq))
                           if BANNER_EVENTS else None)
                promo_now = promo
            browse_list(e, promo_now, grid[:PAGE_SIZE], catalog, rng,
                        dwell_ms=int(rng.integers(*SC["list_dwell_ms"])),
                        first=(i == 0 or i in splits),
                        SC=SC, qrng=qrng, banners=banners, reco=reco,
                        carted=ql_carted)
            if via_banner:
                batch, shown, source, algo = e.last_banner
                b = next(x for x in shown if x["product_id"] == g)
                e.tick(); e.emit("banner_click", g,
                                 recommendation_id=batch, list_id=BANNER_LIST_ID,
                                 algorithm=algo, position=b["slot"],
                                 banner_type=b["type"], banner_value=b["value"],
                                 banner_slot=b["slot"],
                                 trait_source=source or b.get("trait_source"),
                                 policy_version=BANNER_POLICY_VERSION)
                # entry_source enum(§3.3) 에 배너 값이 없어 promo_pick 을 쓴다 — 히어로는
                # 맞춤 기획전 자리다(프론트도 promo_pick). list_id 로 배너인지 가른다
                e.tick(); e.emit("product_click", g, entry_source="promo_pick",
                                 list_id=BANNER_LIST_ID, position=b["slot"])
                rec_meta = {"recommendation_id": batch, "list_id": BANNER_LIST_ID,
                            "position": b["slot"]}
            elif via_main:
                rid, algo, ids = e.last_main
                pos_m = ids.index(g) + 1
                e.tick(); e.emit("recommendation_click", g,
                                 recommendation_id=rid, list_id=MAIN_LIST_ID,
                                 algorithm=algo, position=pos_m)
                e.tick(); e.emit("product_click", g, entry_source="promo_pick",
                                 list_id=MAIN_LIST_ID, position=pos_m)
                rec_meta = {"recommendation_id": rid, "list_id": MAIN_LIST_ID,
                            "position": pos_m}
            else:
                e.tick(); e.emit("product_click", g,
                                 entry_source="list_grid" if rng.random() < 0.8 else "promo_pick",
                                 position=1)
        rec_ids = [x for x in by_cat.get(catalog[g]["cat"], []) if x != g][:6]
        is_target = g == target
        if hidden is not None:
            # **행동을 정답이 아니라 hidden preference 가 정한다.**
            # target 이라고 해서 더 깊이 보거나 반드시 담지 않는다
            pref = float(hidden.get(g, 0.5))
            is_target = False
            if pref >= 0.80:
                depth, convert, wish = 100, rng.random() < 0.75, rng.random() < 0.7
            elif pref >= 0.60:
                depth, convert, wish = 75, rng.random() < 0.25, rng.random() < 0.3
            elif pref >= 0.40:
                depth, convert, wish = 50, False, False
            elif pref >= 0.20:
                depth, convert, wish = 25, False, False
            else:
                depth, convert, wish = 25, False, False
        # 이탈 상품 일부는 끝까지 훑는다. 그래야 추천 섹션이 노출되고,
        # "진지하게 봤지만 안 샀다" 는 v_u- 의 가장 강한 재료가 된다.
        elif is_target:
            depth = 100
        elif rng.random() < SC["p_deep_bounce"]:
            depth = SC["deep_bounce_depth"]
        else:
            depth = int(rng.choice(SC["bounce_depth_choices"]))
        # **`engaged` 는 "깊이 본 세션" 이다 — target 여부가 아니다 (2026-09-21).**
        # 예전에는 `engaged=is_target` 이었다. `target` 은 페르소나의 마지막 긍정 리뷰 상품
        # (1345행)이라 **세포라 리뷰 이력에 있는 상품만** 될 수 있고, hidden 경로에서는
        # 아예 `is_target=False` 로 끈다(1582행). 그래서 등록 상품(SSAFY Beauty 8개)은
        # 구조적으로 영원히 engaged 가 아니었다 — 09-20 실측으로 python_batch 864 세션에서
        # accordion_toggle·ingredient_view_mode_change·text_copy·review_filter_apply 가
        # **네 개 모두 정확히 0** 이었다(전체 브랜드는 13.63/7.08/4.92/13.23%).
        # 대시보드의 '전성분을 펼쳐 본 방문 0.0%' 가 그 결과다.
        #
        # 깊이(depth)는 hidden 경로에서 pref 가, 아닌 경로에서 target·p_deep_bounce 가 정한다.
        # 둘 다 "이 사람이 이 상품을 진지하게 봤나" 를 이미 담고 있으므로 그것을 그대로 쓴다.
        # 평가와 무관하다 — eval_dynamic 은 자기 이벤트 표(`events_for`)를 쓰고 이 로그를
        # 읽지 않는다. 생성기 로그를 입력으로 받는 평가는 eval_cbf_flow 하나뿐이다.
        engaged = is_target if ENGAGED_RULE == "target" else (depth >= ENGAGED_DEPTH_MIN)
        visit_detail(e, g, catalog[g], rec_ids, rng, depth_target=depth,
                     engaged=engaged, entry_source="in_app", SC=SC, rec_meta=rec_meta)
        if hidden is not None:
            if wish:
                e.tick(); e.emit("wishlist_toggle", g, action="add"); liked = True
            if convert:
                e.tick(); e.emit("add_to_cart", g, quantity=1,
                                 **price_props(catalog, g), content_kind="cta")
                if g in REGISTERED_IDS:
                    discovered.append((g, e.sid))   # 등록 상품은 결제 후보로 (아래 p_new_brand_buy)
            elif g in REGISTERED_IDS and rng.random() < SC["p_new_brand_cart"]:
                # ── 신규 브랜드 발견 구매 — hidden 경로에도 같은 문을 둔다 (2026-09-29) ──
                # hidden preference 는 리뷰 이력에서 만든 취향이라 리뷰가 없는 등록 브랜드(SSAFY Beauty)를
                # 판단할 재료가 없다. 09-29 실측(1,000명·LTR 노출): 등록 상품 상세 353건에 담기 3·구매 1.
                # 규칙 경로의 근거 그대로 — 실제 쇼핑몰에서도 신규 브랜드는 리뷰 없이 상세를 보고 팔린다.
                if rng.random() < SC["wishlist_p_target"]:
                    e.tick(); e.emit("wishlist_toggle", g, action="add"); liked = True
                e.tick(); e.emit("add_to_cart", g, quantity=1,
                                 **price_props(catalog, g), content_kind="cta")
                discovered.append((g, e.sid))
        elif is_target:
            if rng.random() < SC["wishlist_p_target"]:
                e.tick(); e.emit("wishlist_toggle", g, action="add"); liked = True
            # 담을까 말까 재는 구간. 버튼 위에 올려두고 안 누른 시간이다
            if rng.random() < SC["p_hover_before_cart"]:
                e.tick(300, 2500)
                e.emit("hover_dwell", g, section_id="product_hero",
                       content_kind="cta", action="add_to_cart",
                       dwell_ms=int(rng.integers(600, 9000)))
            e.tick(); e.emit("add_to_cart", g, quantity=1,
                             **price_props(catalog, g), content_kind="cta")
        elif regret is None and rng.random() < SC["p_cart_regret"]:
            # 충동적으로 담는다. 아래 장바구니 화면에서 도로 뺀다
            e.tick(); e.emit("add_to_cart", g, quantity=1,
                             **price_props(catalog, g), content_kind="cta")
            regret = g
        elif g in REGISTERED_IDS and rng.random() < SC["p_new_brand_cart"]:
            # ── 신규 브랜드 발견 구매 ────────────────────────────────────────
            # 등록 상품은 리뷰가 없어 pos(구매 후보)에 절대 못 든다. 그래서 배너·추천으로 상세까지
            # 와도 담기 분기가 하나도 안 걸렸다. 리뷰 이력과 무관하게, 본 김에 담는 경로를 준다.
            if rng.random() < SC["wishlist_p_target"]:
                e.tick(); e.emit("wishlist_toggle", g, action="add"); liked = True
            e.tick(); e.emit("add_to_cart", g, quantity=1,
                             **price_props(catalog, g), content_kind="cta")
            discovered.append((g, e.sid))       # 담은 세션까지 (Jira 371)
        elif rng.random() < SC["wishlist_p_bounce"]:
            e.tick(); e.emit("wishlist_toggle", g, action="add"); liked = True

        # ── 뒤로가기 재조회 (Jira 350, 데이터·프론트 요청) ──────────────────
        # 목록으로 돌아갔다가 같은 상품을 다시 연다. 프론트도 이때 product_view 를 다시 남긴다.
        # **새 진입이 아니라 재조회다** — 마트는 건수 집계에서 빼야 하고, 그 제외 로직을 검증하려면
        # 로그에 이 모양이 있어야 한다. 계약 §3.4 의 navigation_source 4종 중 history_back 이 이 자리다.
        # 목표 상품에는 걸지 않는다 — 마지막에 와야 하고 전환이 붙어 있다.
        if not is_target and rng.random() < SC["p_history_back"]:
            e.new_page("product_list")
            e.tick(200, 900)
            e.emit("page_view", navigation_source="history_back")   # 목록 복귀
            e.tick(300, 1500)
            # 다시 상세로. page_view·product_view 둘 다 history_back 이다 (§3.4: 같은 진입은 같은 값)
            visit_detail(e, g, catalog[g], rec_ids, rng, depth_target=25,
                         engaged=False, entry_source="history_back", SC=SC)

    # ── 장바구니 화면 ────────────────────────────────────────────────────
    # 프론트는 헤더 장바구니를 누를 때 view_cart 를 남긴다 (App.tsx openCart).
    # product_id 는 싣지 않는다 — 화면 단위 이벤트라 특정 상품의 증거가 아니다.
    # 결제까지 가는 세션 (Jira 312). 목표 상품만 결제한다 — 시드는 과거에 이미 산 것이고, 이탈 상품은 빼는 중이다
    buy = rng.random() < SC["p_purchase_after_cart"]
    # 발견 구매한 등록 상품 중 결제까지 가는 것 (위 p_new_brand_cart 로 담긴 것들)
    # 담은 것 중 결제까지 가는 것. 목표 상품 외에 담긴 것들(발견 구매 · Quick Look)이 대상이다.
    # 시드는 과거에 이미 산 것이라 뺀다.
    # `extra` 는 장바구니 화면에 보이는 것 — 앞선 방문에서 담은 것도 들어 있다(장바구니는 세션을 넘는다)
    extra = list(dict.fromkeys([g for g, _ in discovered]
                               + [g for g, _ in ql_carted if g not in seeds and g != target]))
    # **살 수 있는 것은 이 세션에서 담은 것뿐이다** (Jira 371). 앞선 방문에서 담은 것은
    # 장바구니에 그대로 남는다 — 담아 두고 안 사는 것도 실제 동선이다.
    # 이걸 안 가르면 결제일에 담기 세션이 0 인 (상품,날짜) 행이 생겨
    # funnel_daily 의 checkout <= add_to_cart 와 persona_segment 의 purchase <= detail 이 깨진다.
    # target 은 route 마지막이라 담기와 결제가 이미 같은 세션이다 — 안 바뀐다.
    here_now = {g for g, sid in discovered if sid == e.sid} | {g for g, sid in ql_carted if sid == e.sid}
    # **추첨을 먼저 하고 거른다.** `g in here_now` 를 앞에 두면 추첨 횟수가 줄어 기본 RNG 스트림이
    # 밀리고, 그 뒤 궤적이 통째로 달라진다 (노출·클릭까지 바뀌어 grain 검사가 깨졌다).
    buy_new = [g for g in extra if rng.random() < SC["p_new_brand_buy"] and g in here_now]
    if regret is not None or buy or buy_new or rng.random() < SC["p_view_cart"]:
        cart = [g for g in seeds] + [target] + extra + ([regret] if regret else [])
        e.new_page("cart")
        e.tick(); e.emit("page_view", navigation_source="in_app")
        e.tick(300, 2000)
        e.emit("view_cart",
               item_count=len(cart), distinct_products=len(cart),
               cart_value=(sum(money(catalog[g]["price"], catalog[g].get("price_krw")) for g in cart)
                           if CURRENCY == CURRENCY_KRW else round(sum(catalog[g]["price"] for g in cart), 2)),
               currency=CURRENCY)   # 계약 §3.2: 금액은 currency 와 함께 (Jira 303·340)
        # 수량 조절. 프론트는 entry_source="cart" 를 싣는다 (App.tsx)
        q = 1
        if rng.random() < SC["p_quantity_change"]:
            q = int(rng.integers(2, 4))
            e.tick(500, 4000)
            e.emit("quantity_change", target, quantity=q, entry_source="cart")
        if regret is not None:
            # 담았다 빼기. converted 에서 빠져 v_u- 로 넘어간다
            e.tick(800, 6000)
            e.emit("remove_from_cart", regret, quantity=1,
                   **price_props(catalog, regret),
                   cart_size_after=len(cart) - 1)
        if buy or buy_new:
            # 목표 상품은 buy 일 때만. 발견한 등록 상품은 제 확률로 따로 붙는다 —
            # 신규 브랜드만 사고 나가는 세션도 실제로 있다
            gids = ([target] if buy else []) + buy_new
            checkout(e, catalog, gids, rng, SC, quantities={target: q} if buy else None)

    e.new_page("product_list")
    e.tick(); e.emit("page_view", navigation_source="in_app")
    exit_started = e.t
    e.tick(300, 1500)
    e.emit("exit_summary",
           dwell_ms=int((e.t - exit_started).total_seconds() * 1000),
           max_scroll_percent=0,
           products_viewed=len(route),
           converted=True, wishlisted=liked)
    return {"seeds": len(seeds), "bounce": len(bounce),
            "regret": int(regret is not None), "visits": n_visits}


SAMPLE_STRATIFIED, SAMPLE_HEAD = "stratified", "head"


def sample_personas(P, limit, how=SAMPLE_STRATIFIED, seed=42, key="stratum"):
    """`--limit N` 에 쓸 페르소나 N명을 고른다 (Jira 318).

    personas_9900.json 은 stratum(skin_type|skin_tone|review_bucket) 순으로 정렬돼 있어
    앞에서 자르면 (`head`) 1,000명이 전부 combination|light|3 이 된다 — 고객군 마트의
    skin_type × skin_tone 격자가 한 칸만 찬다 (데이터 파트 09-16 지적).
    `stratified` 는 stratum 별 비례 배분(최대 잔여법)으로 N명을 고른다. 각 층 안에서는
    고정 시드로 뽑고, 결과는 persona_id 순이라 같은 인자면 같은 사람이 나온다.
    """
    if not limit or limit >= len(P):
        return list(P)
    if how == SAMPLE_HEAD:
        return P[:limit]
    groups = {}
    for p in P:
        groups.setdefault(p.get(key) or "", []).append(p)
    total = len(P)
    quota = {g: len(v) * limit / total for g, v in groups.items()}
    alloc = {g: int(q) for g, q in quota.items()}
    rest = limit - sum(alloc.values())
    # 잔여 자리는 소수부가 큰 층부터. 동률은 층 이름으로 고정
    for g in sorted(quota, key=lambda g: (-(quota[g] - alloc[g]), g))[:rest]:
        alloc[g] += 1
    rng = np.random.default_rng(seed)
    picked = []
    for g in sorted(groups):
        n = min(alloc[g], len(groups[g]))
        if n:
            idx = rng.choice(len(groups[g]), size=n, replace=False)
            picked.extend(groups[g][i] for i in idx)
    picked.sort(key=lambda p: p["persona_id"])
    return picked


def _price_krw_of(p):
    """추천 인코더의 환산 규칙을 그대로 쓴다. 인코더를 못 불러오면 같은 공식으로 대신한다"""
    try:
        sys.path.insert(0, os.path.join(ROOT, "batch", "jobs"))
        from product_encoder import price_krw_of
        return price_krw_of(p)
    except Exception:
        krw = p.get("price_krw")
        if krw is not None:
            return float(krw)
        usd = p.get("price_usd")
        return None if usd is None else float(round(float(usd) * 1340.86 / 100) * 100)


def main(limit, show, out, post=None, rps=0, include_agents=False, quick_look=True,
         scenario_id=DEFAULT_SCENARIO_ID, simulation_run_id=None,
         generator_type=DEFAULT_GENERATOR_TYPE, behavior=BEHAVIOR_RULE,
         pref_profile="default", pref_seed=0, exposure=EXPOSURE_POPULAR,
         recommend_url=None, banner_slots=BANNER_SLOTS, reserved=0, hero=BANNER_HERO,
         sample=SAMPLE_STRATIFIED, allow_ctr_grain_violations=False):
    global RECO
    RECO = None
    if recommend_url:
        RECO = RecommendClient(recommend_url, banner_slots=banner_slots, reserved=reserved, hero=hero, log=log)
        h = RECO._call("GET", "/health")
        if h:
            log(f"추천 서버 연동: {recommend_url} — 상품 {h.get('products')}개 · {h.get('scorer')} · "
                f"히어로 정책 {hero} (banner_slots {banner_slots}, reserved {reserved}). "
                f"메인·히어로 식별자는 서버 응답 그대로 (Jira 221·239)")
        else:
            log(f"추천 서버 {recommend_url} 에 붙지 못했다 — 예전 방식({BANNER_ALGO})으로 돈다")
    context = SimulationContext(
        scenario_id=scenario_id,
        simulation_run_id=simulation_run_id or default_simulation_run_id(),
        generator_type=generator_type,
    )
    log(
        f"실행 메타데이터 scenario_id={context.scenario_id} "
        f"simulation_run_id={context.simulation_run_id} "
        f"generator_type={context.generator_type}"
    )
    prods = json.load(open(PRODUCTS, encoding="utf-8"))
    frontend_products = {
        product["product_id"]: product
        for product in json.load(open(FRONTEND_PRODUCTS, encoding="utf-8"))
    }
    if os.path.exists(REGISTERED_PRODUCTS):
        reg = [json.loads(ln) for ln in open(REGISTERED_PRODUCTS, encoding="utf-8") if ln.strip()]
        reg = [r for r in reg if r.get("product_id") not in {p["product_id"] for p in prods}]
        for r in reg:                      # 스키마 맞춤: 생성기가 읽는 키만 채운다
            r.setdefault("_review_stats", {}).setdefault("review_count", 0)
        prods = prods + reg
        REGISTERED_IDS.update(r["product_id"] for r in reg)
        if os.path.exists(FRONTEND_REGISTERED):
            for product in json.load(open(FRONTEND_REGISTERED, encoding="utf-8")):
                frontend_products.setdefault(product["product_id"], product)
        for r in reg:
            frontend_products.setdefault(r["product_id"], {"sku_id": None, "variants": []})
        log(f"등록 상품 {len(reg)}개를 카탈로그에 포함 (리뷰 0 → 인기순 꼴찌, 히어로 new_brand 후보)")
    catalog = {
        p["product_id"]: {
            "cat": p["secondary_category"],
            "name": p["product_name"],
            "price": p["price_usd"],
            "price_krw": _price_krw_of(p),      # 어휘집 0.7 규칙 (Jira 302·303)
            # 배너 축 값 — highlights 의 첫 "Good for: X". 없으면 None
            "concern": next((h.split(":", 1)[1].strip() for h in (p.get("highlights") or [])
                             if h.startswith("Good for:")), None),
            "n": p["_review_stats"]["review_count"],
            "sku_id": frontend_products[p["product_id"]]["sku_id"],
            "variants": frontend_products[p["product_id"]].get("variants") or [],
        }
        for p in prods
    }
    by_cat = {}
    for g, v in catalog.items():
        by_cat.setdefault(v["cat"], []).append(g)
    popular = [g for g, _ in sorted(catalog.items(), key=lambda x: -x[1]["n"])]

    P = json.load(open(os.path.join(PERSONA_DIR, "personas_9900.json"), encoding="utf-8"))
    # PA 100명은 기본 제외 — 프론트 드롭다운과 LLM 에이전트가 직접 조종하는 계정이다.
    # 합성 로그를 미리 쌓아두면 사람의 행동이 묻혀 시연이 안 된다.
    A = []
    if include_agents:
        A = json.load(open(os.path.join(PERSONA_DIR, "personas_100_agent.json"),
                           encoding="utf-8"))
    # --include-agents 면 --limit 이 있어도 PA 100명 전원 (Jira 328). 에이전트가 라이브에서 재구매하려면
    # 마트에 그 사람의 과거 구매·재구매 쌍(327)이 있어야 한다 — 2명만 넣던 옛 동작은 맛보기용이었다
    people = (P + A) if not limit else (sample_personas(P, limit, how=sample) + A)
    log(f"페르소나 PC {len(P):,}명" + (f" + 에이전트 PA {len(A)}명" if A else " (PA 제외)")
        + f" -> 대상 {len(people):,}명" + (f" ({sample} 표본)" if limit else ""))
    if limit:
        from collections import Counter
        st = Counter(p.get("skin_type") for p in people if p.get("persona_id", "").startswith("PC"))
        log("  skin_type 분포: " + " · ".join(f"{k} {v}" for k, v in sorted(st.items(), key=lambda x: -x[1])))

    load_style()
    load_ingredients()
    hp = None
    if behavior == BEHAVIOR_HIDDEN:
        sys.path.insert(0, os.path.join(ROOT, "batch", "jobs"))
        from hidden_preference import PROFILES, HiddenPreference
        hp = HiddenPreference(products=prods, weights=PROFILES[pref_profile],
                              noise_seed=pref_seed)
        log(f"행동 결정: hidden preference ({pref_profile}, seed {pref_seed})"
            f" — target 에 전환을 강제하지 않는다")
    else:
        log("행동 결정: 규칙 기반 (target 에 전환을 강제한다)."
            " 평가용 로그라면 --behavior hidden_preference 를 쓸 것")
    globals()["EXPOSURE_NAME"] = exposure
    exp = None
    if exposure == EXPOSURE_CBF:
        exp = CbfExposure(catalog)
        log(f"노출 정책: {EXPOSURE_CBF} — 추천 점수가 방문 후보의 절반을 정한다."
            " 이 로그로 추천 정확도를 재지 않는다")
    else:
        log(f"노출 정책: {EXPOSURE_POPULAR} — 같은 카테고리 -> 인기순 (전원 같은 화면)")

    rng = np.random.default_rng(42)
    sink, meta, t0 = [], [], time.time()
    for i, p in enumerate(people):
        hidden = None
        if hp is not None:
            seeds = [g for g in dict.fromkeys(r["group_id"] for r in p["reviews"])
                     if g in hp.index]
            # 마지막 상품을 입력에서 빼고 점수를 만든다 — 누출 방지.
            # 평가의 target 정의(계약 §7.1)와 정확히 같지는 않은 근사다.
            # 여기서 필요한 것은 "정답을 그대로 먹이지 않는다" 뿐이다
            scores = hp.score_all(p, seeds[:-1] if len(seeds) > 1 else seeds)
            hidden = {gid: float(scores[hp.index[gid]]) for gid in hp.index}
        r = gen_persona(
            p,
            catalog,
            by_cat,
            popular,
            rng,
            sink,
            context,
            quick_look=quick_look,
            hidden=hidden,
            exposure=exp,
        )
        if r: meta.append(r)
        if not limit and (i + 1) % 2000 == 0:
            log(f"  {i+1:,}명 / 이벤트 {len(sink):,}건")
    log(f"이벤트 {len(sink):,}건 — {time.time()-t0:.1f}초")

    property_result = validate_property_contract(sink)
    ctr_grain_bad = validate_ctr_grains(sink, strict=not allow_ctr_grain_violations)
    log(f"Event Properties 계약 {property_result['checked']:,}건 통과")
    if not ctr_grain_bad:
        log("grain 단위 노출·클릭 통과 (상품·추천·배너 3종)")

    if out:
        with open(out, "w", encoding="utf-8") as f:
            for x in sink:
                f.write(json.dumps(x, ensure_ascii=False) + chr(10))
        log(f"저장 {out}  ({os.path.getsize(out)/1024/1024:.1f}MB)")

    c, ci = Counter(x["event_name"] for x in sink), Counter(x["intent"] for x in sink)
    seed_n = sum(1 for x in sink if x["properties"].get("seeded") is True)
    seed_cart = sum(1 for x in sink if x["properties"].get("seeded")
                    and x["event_name"] == "add_to_cart")
    seed_neg = sum(1 for x in sink if x["properties"].get("seeded")
                   and x["event_name"] in ("scroll_backtrack", "rage_click"))
    ckpt = sum(1 for x in sink if x["properties"].get("reason") == "checkpoint")
    print("\n" + "=" * 64)
    print(f"이벤트 {len(sink):,}건 / 페르소나 {len(meta):,}명 / 평균 {len(sink)/len(meta):.0f}건")
    print("=" * 64)
    for k, v in c.most_common():
        print(f"  {k:<28} {v:>10,}  {v/len(sink)*100:5.1f}%")
    print("\n의도별")
    for k, v in ci.most_common():
        print(f"  {k:<28} {v:>10,}  {v/len(sink)*100:5.1f}%")
    print()
    print(f"시드 {seed_n:,}건 (긍정 장바구니 {seed_cart:,} / 부정 감점 {seed_neg:,})"
          f" / 시뮬레이션 {len(sink)-seed_n:,}건")
    print(f"checkpoint dwell {ckpt:,}건 ({ckpt/len(sink)*100:.1f}%)  <- 사용자 벡터에서 제외 대상")
    imp, clk = c["product_impression"], c["product_click"]
    print(f"퍼널  노출 {imp:,} -> 클릭 {clk:,} ({clk/imp*100:.1f}%) "
          f"-> 장바구니 {c['add_to_cart']-seed_cart:,}")
    if RECO is not None:
        rec_imp = c.get("recommendation_impression", 0); rec_clk = c.get("recommendation_click", 0)
        b_imp = c.get("banner_impression", 0); b_clk = c.get("banner_click", 0)
        algos = sorted({x["properties"].get("algorithm") for x in sink
                        if x["event_name"] in ("banner_impression", "recommendation_impression")} - {None})
        print(f"추천 서버 연동  메인 노출 {rec_imp:,} -> 클릭 {rec_clk:,} · 배너 노출 {b_imp:,} -> 클릭 {b_clk:,} "
              f"· algorithm {algos}")
        log(RECO.summary())

    if post:
        log(f"수집 API 전송 시작 -> {post}  (배치 {BATCH}건"
            + (f", {rps}건/초 제한)" if rps else ", 제한 없음)"))
        ok, fail, sec = post_events(post, sink, rps)
        print()
        print("=" * 64)
        print(f"전송 결과  성공 {ok:,}건 / 실패 {fail:,}건 / {sec:.1f}초"
              f"  ({ok/max(sec,1e-9):,.0f}건/초)")
        print("=" * 64)
        if fail:
            print("  400 이면 계약 불일치입니다 (재시도하지 않고 버림).")
            print("  429/503 은 재시도했는데도 안 된 경우입니다 — 수집 서버와")
            print("  Kafka 가 떠 있는지, --rps 를 낮춰야 하는지 확인하세요.")

    if show:
        pid = sink[0]["persona_id"]
        ev = [x for x in sink if x["persona_id"] == pid]
        print("\n" + "=" * 64)
        print(f"세션 샘플 — {pid} (총 {len(ev)}건 중 앞 {show}건)")
        print("=" * 64)
        for x in ev[:show]:
            tag = "SEED" if x["properties"].get("seeded") is True else f"#{x['sequence_no']:<4}"
            pr = " ".join(f"{k}={v}" for k, v in list(x["properties"].items())[:4])
            print(f"  {tag} {x['event_name']:<24} {x['intent']:<11} {pr[:78]}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--currency", choices=(CURRENCY_USD, CURRENCY_KRW), default=CURRENCY_USD,
                    help="이벤트 금액 통화 (Jira 303). KRW 면 unit_price·cart_value·paid_value 를 원화 정수로, "
                         "add_to_cart 는 price_usd 대신 unit_price+currency. 기본 USD (계약 필드 이름 결정 전)")
    ap.add_argument("--sample", choices=(SAMPLE_STRATIFIED, SAMPLE_HEAD), default=SAMPLE_STRATIFIED,
                    help="--limit 표본 방식. stratified: stratum 비례 층화(기본, Jira 318). head: 파일 앞 N명(옛 동작)")
    ap.add_argument("--show", type=int, default=0)
    ap.add_argument("--allow-ctr-grain-violations", action="store_true",
                    help="grain 단위 노출<클릭 을 경고만 하고 통과 (기본은 중단, Jira 358)")
    ap.add_argument("--out", default=None,
                    help="jsonl 저장 경로. 생략하면 파일로 안 쓴다")
    ap.add_argument("--post", default=None, metavar="URL",
                    help="수집 API 베이스 URL. 예) http://localhost:8080")
    ap.add_argument("--no-banner-events", action="store_true",
                    help="banner_impression / banner_click 을 내지 않는다 (Jira 212)")
    ap.add_argument("--no-quick-look", action="store_true",
                    help="Quick Look 동선을 끈다 (A/B 대조군)")
    ap.add_argument("--scenario-id", default=DEFAULT_SCENARIO_ID,
                    help="시뮬레이션 시나리오 ID")
    ap.add_argument("--simulation-run-id", default=None,
                    help="실행 단위 ID. 생략하면 UTC 시각 기반으로 생성")
    ap.add_argument("--generator-type", default=DEFAULT_GENERATOR_TYPE,
                    help="synthetic 생성 방식 (기본: python_batch)")
    ap.add_argument("--include-agents", action="store_true",
                    help="PA 100명(인터랙티브 전용)도 생성 대상에 넣는다. 기본은 제외")
    ap.add_argument("--behavior", choices=(BEHAVIOR_RULE, BEHAVIOR_HIDDEN),
                    default=BEHAVIOR_RULE,
                    help="행동을 무엇이 정하는가. 평가용 로그는 hidden_preference "
                         "(target 에 전환을 강제하지 않는다)")
    ap.add_argument("--exposure", choices=(EXPOSURE_POPULAR, EXPOSURE_CBF),
                    default=EXPOSURE_POPULAR,
                    help="무엇이 화면에 노출되는가. popular_v0 은 같은 카테고리->인기순 "
                         "(전원 같은 화면), cbf_v1 은 추천 점수가 후보의 절반을 정한다. "
                         "**노출만 정하고 행동은 hidden preference 가 정한다.** "
                         "정책이 다른 로그의 수치를 나란히 비교하지 말 것")
    ap.add_argument("--pref-profile", default="default",
                    help="hidden preference 가중치 조합 (강건성 평가용)")
    ap.add_argument("--pref-seed", type=int, default=0,
                    help="hidden preference 잡음 seed")
    ap.add_argument("--rps", type=int, default=0,
                    help="초당 이벤트 수 제한. 0 이면 제한 없음")
    ap.add_argument("--recommend-url", default=None, metavar="URL",
                    help="추천 서버 베이스 URL (Jira 221). 예) http://localhost:8300. 주면 목록마다 "
                         "실제 추천(items·banners)을 받아 그 식별자로 이벤트를 만들고 행동을 서버 상태에 넘긴다. "
                         "서버가 없으면 경고 뒤 예전 방식")
    ap.add_argument("--banner-slots", type=int, default=BANNER_SLOTS,
                    help="추천 서버에 요청할 배너 칸 수 (기본 1 = 히어로만. 응답 banners[] 는 화면에 없어 쓰지 않는다)")
    ap.add_argument("--reserved", type=int, default=0,
                    help="추천 서버에 요청할 신규 브랜드 전용 배너 칸 수 (기본 0 — 전용 칸은 히어로 정책으로 대신한다)")
    ap.add_argument("--hero", choices=("top", "new_brand"), default=BANNER_HERO,
                    help="추천 서버 히어로 정책 (Jira 237). 기본 new_brand = 화면과 같음")
    a = ap.parse_args()
    CURRENCY = a.currency          # 모듈 전역 (여기는 __main__ 블록)
    BANNER_EVENTS = not a.no_banner_events      # 모듈 전역 (if __name__ 블록)
    if not a.out and not a.post:
        a.out = os.path.join(BD, "behavior_logs.jsonl")
    main(
        a.limit,
        a.show,
        a.out,
        a.post,
        a.rps,
        a.include_agents,
        quick_look=not a.no_quick_look,
        scenario_id=a.scenario_id,
        simulation_run_id=a.simulation_run_id,
        generator_type=a.generator_type,
        behavior=a.behavior,
        pref_profile=a.pref_profile,
        pref_seed=a.pref_seed,
        exposure=a.exposure,
        recommend_url=a.recommend_url,
        banner_slots=a.banner_slots,
        reserved=a.reserved,
        hero=a.hero,
        sample=a.sample,
        allow_ctr_grain_violations=a.allow_ctr_grain_violations,
    )
