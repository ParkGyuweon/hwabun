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
  - 모든 synthetic Event properties 에 scenario_id / simulation_run_id /
    generator_type 을 기록한다

실행
  python gen_behavior_logs.py --limit 50                    # 맛보기. 파일로 저장
  python gen_behavior_logs.py                               # PC 9,900명
  python gen_behavior_logs.py --include-agents              # PA 100명까지 (기본 제외)
  python gen_behavior_logs.py --post http://localhost:8080  # 수집 API 로 전송
  python gen_behavior_logs.py --post http://localhost:8080 --rps 200 --limit 500
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
sys.path.insert(0, os.path.join(ROOT, "batch", "jobs"))
import behavior_weights as BW

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
DEFAULT_GENERATOR_TYPE = "python_batch"
NOW = datetime(2026, 8, 28, 12, 0, 0)
CHECKPOINT_MS = 15000                # 목록 체류 중 dwell 재발화 주기


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


def seed_session_id(context, persona_id, product_id):
    """Build a seed session key that cannot merge personas or products."""

    return f"seed:{context.simulation_run_id}:{persona_id}:{product_id}"

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
    "window_days": 120,

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

    # [미정] 유사 상품 추천을 눌러 다음 상세로 넘어가는 확률.
    #   직전 상세의 추천 노출과 같은 recommendation_id / position 을 실어야
    #   CTR 을 계산할 수 있다 (SimilarProducts.tsx 와 동일).
    "p_rec_click": 0.55,

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
    "p_variant_select": 0.40,
    "p_review_filter": 0.50,
    "p_scroll_backtrack": 0.25,
    "p_list_filter": 0.35,
    "p_list_sort": 0.20,

    # [미정] 세션 구성. 현재는 상품 하나당 목록->상세->복귀를 한 세션에서 처리한다
    #   BEHAVIOR_SCENARIO 4-2절은 "며칠에 걸친 1~3회 방문"을 권고하나 미반영
    "sessions_per_persona": 1,
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
    "ingredient":  [("p_accordion", 1.8), ("p_text_selection", 2.2), ("dwell_x_ingredients", 2.2)],
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


# ── 이벤트 intent — log.ts 의 EVENT_INTENT 를 그대로 읽는다 ────────────────
#    사본을 두면 프론트가 이벤트를 추가했을 때 조용히 어긋난다.
_W = BW.load()
INTENT = _W["intent"]


# ── 화면 구조: 섹션 -> (콘텐츠 종류, content_ref) ──────────────────────────
#    프론트 실측 로그에서 역산했다. 섹션 순서 = 스크롤 순서
DETAIL_LAYOUT = [
    ("product_hero",     [("product_image", None), ("price", None),
                          ("variant_option", None), ("cta", None)]),
    ("highlights",       [("highlight_badge", None)]),
    ("about_product",    [("what_it_is", None), ("ingredient_list", "highlighted"),
                          ("what_else", None), ("ingredient_callout", None),
                          ("clinical_claim", None), ("persona_match", "skin_type"),
                          ("persona_match", "concerns"), ("product_meta", "category"),
                          ("product_meta", "size")]),
    ("ingredients",      [(None, None)]),
    ("how_to_use",       [(None, None)]),
    ("similar_products", [("recommendation_card", "__rec__")]),
    ("reviews",          [("review_stats", None), ("review_filter", None),
                          ("user_review", None)]),
]
LIST_LAYOUT = [("promo_row", "product_card"), ("list_controls", None),
               ("product_grid", "product_card")]


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
        properties = {
            k: v for k, v in props.items()
            if v is not None or k in ("content_kind", "content_ref", "section_id")
        }
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
            "intent": INTENT[name],
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
def visit_detail(e, gid, rec_ids, rng, depth_target, engaged, entry_source, SC=SCENARIO):
    """depth_target = 도달할 최대 스크롤 %. 10% 단위로 로그를 남긴다"""
    e.new_page("product_detail")
    e.tick(300, 1200)
    e.emit("page_view", gid, navigation_source=entry_source)
    # 프론트가 상세 진입에서 page_view 직후 product_view 를 같은 page_view_id 로 남긴다
    # (frontend/src/lib/logger.ts 의 trackProductView). 둘 다 가중치 1.0 이라
    # 하나만 만들면 합성 로그가 실제 로그보다 상품당 1.0 만큼 가볍다.
    e.emit("product_view", gid, navigation_source=entry_source)

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
                   visible_content_kinds=",".join(b[0] for b in blocks[:3] if b[0]),
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
                       algorithm="same_category_v0", position=pos)
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
                                 content_kind="ingredient_list", open=True)
            if rng.random() < SC["p_text_selection"]:
                tlen = int(rng.integers(20, 200))
                e.tick(); e.emit("text_selection", gid, section_id=section,
                                 content_kind="product_meta", content_ref="category",
                                 text_length=tlen, truncated=False)
                # 고른 텍스트를 실제로 복사. 프론트는 같은 선택에 대해
                # text_selection 뒤 copy 이벤트로 남긴다 (useTextSelection)
                if rng.random() < SC["p_text_copy"]:
                    e.tick(200, 2000)
                    e.emit("text_copy", gid, section_id=section,
                           content_kind="product_meta", content_ref="category",
                           text_length=tlen, truncated=False)
        # 성분 표시 방식 전환. 성분을 신경 쓰는 페르소나일수록 자주 바꿔 본다
        # (SC 의 p_accordion 이 성향 6축의 ingredient 로 이미 조정돼 있다)
        if engaged and section == "ingredients":
            if rng.random() < SC["p_ingredient_mode"]:
                for m in ("raw", "chip")[:int(rng.integers(1, 3))]:
                    e.tick(300, 3000)
                    e.emit("ingredient_view_mode_change", gid,
                           section_id=section, mode=m)

        if engaged and section == "product_hero":
            for idx in range(int(rng.integers(2, 8))):
                e.tick(150, 800)
                e.emit("media_view", gid, media_index=idx + 1, media_type="image")
            if rng.random() < SC["p_variant_select"]:
                e.tick(); e.emit("variant_select", gid, section_id=section,
                                 content_kind="variant_option")
        if engaged and section == "reviews":
            for _ in range(int(rng.integers(1, 5))):
                e.tick(); e.emit("review_expand", gid, section_id=section,
                                 content_kind="user_review")
            if rng.random() < SC["p_review_filter"]:
                e.tick(); e.emit("review_filter_apply", gid, section_id=section,
                                 content_kind="review_filter", filter_kind="same_skin_type")
        # 되돌아 읽기
        if engaged and rng.random() < SC["p_scroll_backtrack"]:
            e.tick(); e.emit("scroll_backtrack", gid, section_id=section,
                             content_kind=blocks[0][0], content_ref=blocks[0][1],
                             depth_percent=max(0, depth - int(rng.integers(2, 8))),
                             distance_px=int(rng.integers(150, 400)))
    return depth


# ── 목록 페이지 체류 ──────────────────────────────────────────────────────
def browse_list(e, promo, grid, rng, dwell_ms, first, SC=SCENARIO, qrng=None):
    e.new_page("product_list")
    e.tick(300, 1200)
    if first:
        e.emit("session_start")
    e.emit("page_view", navigation_source="in_app" if not first else "direct")

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
        e.emit("product_impression", None, product_id=g, position=pos,
               list_id="product_grid", algorithm=EXPOSURE_NAME)
        # 노출 대비 클릭을 재려면 "얼마나 보였나" 가 있어야 한다. 가중 0 이다
        if rng.random() < SC["p_impression_dwell"]:
            e.emit("impression_dwell", None, product_id=g, position=pos,
                   list_id="product_grid",
                   visible_ms=int(rng.integers(400, 5000) / (1 + 0.12 * (pos - 1))))
    # Quick Look — 카드 호버 후 버튼을 눌러 요약 창을 연다.
    # 창은 목록 위에 뜨므로 page_type / page_view_id 는 그대로다.
    # qrng 가 None 이면 이 동선 자체가 없다 (A/B 의 대조군)
    if qrng is not None:
        for pos, g in enumerate(grid, 1):
            if qrng.random() >= SC["p_quick_look"]:
                continue
            e.tick(200, 1500, rng=qrng)
            e.emit("quick_look", g, position=pos, list_id="product_grid")
            n_var = 0
            if qrng.random() < SC["p_ql_variant"]:
                n_var = int(qrng.integers(1, 4))
                for _ in range(n_var):
                    e.tick(200, 1200, rng=qrng)
                    e.emit("variant_select", g, entry_source="quick_look")
            added = qrng.random() < SC["p_ql_add"]
            wished = qrng.random() < SC["p_ql_wish"]
            if added:
                e.tick(300, 2000, rng=qrng)
                e.emit("add_to_cart", g, quantity=1, entry_source="quick_look")
            if wished:
                e.tick(200, 1200, rng=qrng)
                e.emit("wishlist_toggle", g, action="add", entry_source="quick_look")
            dwell = int(qrng.integers(1200, 25000))
            e.tick(200, 1500, rng=qrng)
            # 닫는 방식. 프론트는 backdrop / esc / button / navigate 를 남긴다
            e.emit("quick_look_close", g,
                   close_reason=str(qrng.choice(["backdrop", "esc", "button", "navigate"],
                                                p=[0.42, 0.13, 0.35, 0.10])),
                   dwell_ms=dwell, variants_viewed=n_var,
                   added_to_cart=bool(added), wishlisted=bool(wished))

    if rng.random() < SC["p_list_filter"]:
        e.tick(); e.emit("filter_change", filter_kind="category")
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

# 후보 구성. eval_dynamic.py 와 **같은 비율(추천 50%)** 이다 — 추천 Top 만 보면
# 추천이 자기가 고른 것만 채점하게 되므로 카테고리·무작위를 섞는다.
# 개수가 두 배인 이유는 이 pool 이 이탈 상품뿐 아니라 **목록 화면 12칸**을
# 그리는 데도 쓰이기 때문이다. 12칸을 채우고도 남아야 한다.
POOL_MIX = {"top": 12, "category_popular": 6, "random": 6}


class CbfExposure:
    """추천 점수로 방문 후보를 뽑는다. 무엇을 고를지가 아니라 무엇이 보일지를 정한다."""

    def __init__(self, catalog):
        sys.path.insert(0, os.path.join(ROOT, "batch", "jobs"))
        from product_encoder import Encoder
        from persona_feature import load as load_affinity
        from recommender import Recommender
        from user_vector import UserVector
        self.UserVector = UserVector
        enc = Encoder()
        self.M = np.asarray(enc.matrix(), np.float32)
        self.index = {x["product_id"]: i for i, x in enumerate(enc.products)}
        self.prior = np.asarray(enc.prior(), dtype=np.float32)
        self.rec = Recommender(self.M, self.index, self.prior,
                               affinity=load_affinity(self.index))
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
        visit_detail(e, g, [], rng,
                     depth_target=int(rng.choice(SC["neg_seed_depth_choices"])),
                     engaged=False, entry_source="direct", SC=SC)
        e.tick(); e.emit("scroll_backtrack", g, section_id="about_product",
                         depth_percent=int(rng.integers(10, 30)), seeded=True)
        if rng.random() < SC["neg_seed_p_rage"]:
            e.tick(); e.emit("rage_click", g, section_id="product_hero",
                             click_count=int(rng.integers(3, 6)), seeded=True)

    for i, g in enumerate(seeds):
        e = Emitter(
            sink,
            p["persona_id"],
            base + timedelta(days=step * (len(neg) + i)),
            rng,
            context,
            session_id=seed_session_id(context, p["persona_id"], g),
            is_seed=True,
        )
        e.new_page("product_detail")
        e.emit("add_to_cart", g, seeded=True, quantity=1,
               price_usd=catalog[g]["price"])

    # 이탈 상품 — **노출**로 고른다. 취향으로 고르지 않는다.
    #   popular_v0  같은 카테고리 -> 인기순. 전원이 같은 화면을 본다
    #   cbf_v1      추천 점수가 후보의 절반을 정한다. 사람마다 다른 화면을 본다
    # 어느 쪽이든 고른 뒤의 행동(체류·담기)은 hidden preference 가 정한다.
    regret = None          # 담았다 뺄 이탈 상품 (최대 1개)
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

    e = Emitter(
        sink,
        p["persona_id"],
        NOW - timedelta(days=float(rng.random() * 5)),
        rng,
        context,
    )
    promo = popular[:6]
    liked = False
    route = list(bounce) + [target]
    visited = set()
    for i in range(len(route)):
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
        if via_rec:
            rec_batch, rec_list = e.last_rec
            e.tick(); e.emit("recommendation_click", g,
                             recommendation_id=rec_batch, list_id="similar_products",
                             algorithm="same_category_v0",
                             position=rec_list.index(g) + 1)
            e.tick(); e.emit("product_click", g, entry_source="similar_products",
                             position=rec_list.index(g) + 1)
        else:
            grid = list(rng.choice([x for x in pool if x != g] or pool,
                                   size=min(12, len(pool)), replace=False))
            grid = [g] + [x for x in grid if x != g]
            browse_list(e, promo, grid[:12], rng,
                        dwell_ms=int(rng.integers(*SC["list_dwell_ms"])), first=(i == 0),
                        SC=SC, qrng=qrng)
            e.tick(); e.emit("product_click", g,
                             entry_source="grid" if rng.random() < 0.8 else "promo_pick",
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
        visit_detail(e, g, rec_ids, rng, depth_target=depth,
                     engaged=is_target, entry_source="in_app", SC=SC)
        if hidden is not None:
            if wish:
                e.tick(); e.emit("wishlist_toggle", g, action="add"); liked = True
            if convert:
                e.tick(); e.emit("add_to_cart", g, quantity=1,
                                 price_usd=catalog[g]["price"], content_kind="cta")
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
                             price_usd=catalog[g]["price"], content_kind="cta")
        elif regret is None and rng.random() < SC["p_cart_regret"]:
            # 충동적으로 담는다. 아래 장바구니 화면에서 도로 뺀다
            e.tick(); e.emit("add_to_cart", g, quantity=1,
                             price_usd=catalog[g]["price"], content_kind="cta")
            regret = g
        elif rng.random() < SC["wishlist_p_bounce"]:
            e.tick(); e.emit("wishlist_toggle", g, action="add"); liked = True

    # ── 장바구니 화면 ────────────────────────────────────────────────────
    # 프론트는 헤더 장바구니를 누를 때 view_cart 를 남긴다 (App.tsx openCart).
    # product_id 는 싣지 않는다 — 화면 단위 이벤트라 특정 상품의 증거가 아니다.
    if regret is not None or rng.random() < SC["p_view_cart"]:
        cart = [g for g in seeds] + [target] + ([regret] if regret else [])
        e.new_page("cart")
        e.tick(); e.emit("page_view", navigation_source="in_app")
        e.tick(300, 2000)
        e.emit("view_cart",
               item_count=len(cart), distinct_products=len(cart),
               cart_value=round(sum(catalog[g]["price"] for g in cart), 2))
        # 수량 조절. 프론트는 entry_source="cart" 를 싣는다 (App.tsx)
        if rng.random() < SC["p_quantity_change"]:
            q = int(rng.integers(2, 4))
            e.tick(500, 4000)
            e.emit("quantity_change", target, quantity=q, entry_source="cart")
        if regret is not None:
            # 담았다 빼기. converted 에서 빠져 v_u- 로 넘어간다
            e.tick(800, 6000)
            e.emit("remove_from_cart", regret, quantity=1,
                   price_usd=catalog[regret]["price"],
                   cart_size_after=len(cart) - 1)

    e.new_page("product_list")
    e.tick(); e.emit("page_view", navigation_source="in_app")
    e.emit("exit_summary", products_viewed=len(route),
           converted=True, wishlisted=liked)
    return {"seeds": len(seeds), "bounce": len(bounce), "regret": int(regret is not None)}


def main(limit, show, out, post=None, rps=0, include_agents=False, quick_look=True,
         scenario_id=DEFAULT_SCENARIO_ID, simulation_run_id=None,
         generator_type=DEFAULT_GENERATOR_TYPE, behavior=BEHAVIOR_RULE,
         pref_profile="default", pref_seed=0, exposure=EXPOSURE_POPULAR):
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
    catalog = {p["product_id"]: {"cat": p["secondary_category"], "name": p["product_name"],
                                 "price": p["price_usd"], "n": p["_review_stats"]["review_count"]}
               for p in prods}
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
    people = (P + A) if not limit else (P[:limit] + A[:2])
    log(f"페르소나 PC {len(P):,}명" + (f" + 에이전트 PA {len(A)}명" if A else " (PA 제외)")
        + f" -> 대상 {len(people):,}명")

    load_style()
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
            # target(마지막 긍정 리뷰)은 입력에서 빼고 점수를 만든다 — 누출 방지
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
    ap.add_argument("--show", type=int, default=0)
    ap.add_argument("--out", default=None,
                    help="jsonl 저장 경로. 생략하면 파일로 안 쓴다")
    ap.add_argument("--post", default=None, metavar="URL",
                    help="수집 API 베이스 URL. 예) http://localhost:8080")
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
    a = ap.parse_args()
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
    )
