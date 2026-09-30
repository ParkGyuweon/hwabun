# -*- coding: utf-8 -*-
"""
심은 신호 복원 검사 — "파이프라인이 생성기가 심은 신호를 그대로 복원하는가".

왜 있나
    합성 로그는 `simulator/generator/gen_behavior_logs.py` 가 **규칙으로** 만든다.
    그러니 대시보드에 "끝까지 본 방문은 전부 담았다" 가 뜨면 그건 발견이 아니라 우리가 심은 값이다.
    이 스크립트는 심은 규칙 하나하나를 **로그만 보고** 다시 재서 나란히 찍는다.

        복원 값 ≈ 기대 값   파이프라인이 신호를 왜곡 없이 옮겼다 (중복·누락·조인 오류가 없다)
        복원 값 ≠ 기대 값   정제·집계 어딘가에서 신호가 새거나 부풀었다 → 조사 대상

    심은 값은 생성기의 `SCENARIO` · `STYLE_EFFECT` 를 **직접 import 해서** 읽는다(사본을 두지 않는다).
    target(정답 상품)은 로그에 없으므로 쓰지 않는다 — 전부 로그에서 보이는 것(스크롤 깊이·담기·찜·결제·
    등록 상품 여부·페르소나 성향)으로만 잰다.

입력 (셋 중 하나)
    --events PATH           생성기 --out JSONL (LogEnvelope 한 줄 1건). 파이프라인 전 원본 — 자체 점검용
    --cleaned PATH          Q2 정제 결과 cleaned_events Parquet 디렉터리 (pyarrow 필요).
                            기본은 환경 변수 CLEANED_EVENTS_PATH (clean_events_job.py 와 같은 이름),
                            없으면 data/processed/cleaned_events
    --cleaned-jsonl PATH    cleaned_events 를 JSONL 로 뽑은 것 (properties_json · is_seeded 열)
    보조 파일: PERSONA_STYLE_PATH (기본 simulator/personas/data/persona_style.json),
               REGISTERED_PRODUCTS_PATH (기본 batch/ingest/data/serving/registered_products.jsonl)

한 번에 여러 생성기 실행(simulation_run_id)이 섞여 있으면 --run-id 로 하나만 고른다.
**rule 모드(기본) 로그 전제다.** --behavior hidden_preference 로 만든 로그는 깊이·담기를 다른 규칙이
정하므로 이 표의 기대 값이 맞지 않는다 (스크립트가 경고한다).

실행
    python simulator/generator/gen_behavior_logs.py --limit 1000 --out /tmp/gen.jsonl
    python batch/jobs/check_planted_signals.py --events /tmp/gen.jsonl
    CLEANED_EVENTS_PATH=data/processed/cleaned_events python batch/jobs/check_planted_signals.py --cleaned
    python batch/jobs/check_planted_signals.py --events /tmp/gen.jsonl --markdown   # 문서 표 행으로
"""
import argparse
import json
import math
import os
import sys
from collections import Counter, defaultdict

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
GEN_DIR = os.path.join(ROOT, "simulator", "generator")

DETAIL_SECTIONS = 7          # gen_behavior_logs.DETAIL_LAYOUT 길이 — 아래 observed_depth 에서 import 값으로 덮는다
INGREDIENTS_SECTION = "ingredients"


# ── 심은 값 ──────────────────────────────────────────────────────────────
def load_generator():
    """생성기 모듈을 import 해서 SCENARIO · STYLE_EFFECT · DETAIL_LAYOUT 을 그대로 쓴다"""
    sys.path.insert(0, GEN_DIR)
    import gen_behavior_logs as G          # noqa: E402
    return G


def observed_depth(depth_target, n_sections=DETAIL_SECTIONS):
    """visit_detail 이 depth_target 을 받았을 때 로그에 남는 최대 scroll_depth.

    상세는 섹션 7개 단위로 스크롤을 남긴다. 그래서 심은 90 은 로그에서 85, 20/30/40/50 은 14/28/40/50, 25 는 25 로 보인다.
    """
    n_sec = max(1, round(n_sections * depth_target / 100))
    return min(depth_target, int(n_sec / n_sections * 100))


def style_factor(score, max_mult):
    """gen_behavior_logs.persona_style 과 같은 식 — 0.5 에서 1.0배, 1.0 에서 max_mult 배"""
    return 1.0 + (max_mult - 1.0) * max(0.0, (score - 0.5) * 2)


def effect_of(G, axis, key):
    for k, mx in G.STYLE_EFFECT.get(axis, []):
        if k == key:
            return mx
    return 1.0


# ── 입력 ────────────────────────────────────────────────────────────────
def normalize(row):
    """생성기 LogEnvelope 와 cleaned_events 행을 같은 모양으로"""
    props = row.get("properties")
    if props is None:
        pj = row.get("properties_json")
        props = json.loads(pj) if isinstance(pj, str) and pj else {}
    seeded = row.get("is_seeded")
    if seeded is None:
        seeded = props.get("seeded") is True
    return {"event_name": row.get("event_name"), "persona_id": row.get("persona_id"),
            "session_id": str(row.get("session_id") or ""), "page_view_id": row.get("page_view_id"),
            "product_id": row.get("product_id"), "props": props, "seeded": bool(seeded),
            "run_id": props.get("simulation_run_id") or row.get("simulation_run_id")}


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield normalize(json.loads(line))


def read_parquet(path):
    try:
        import pyarrow.dataset as ds
    except ImportError:
        raise SystemExit("--cleaned 는 pyarrow 가 필요하다 (pip install pyarrow). "
                         "또는 cleaned_events 를 JSONL 로 뽑아 --cleaned-jsonl 로 준다")
    cols = ["event_name", "persona_id", "session_id", "page_view_id", "product_id",
            "is_seeded", "simulation_run_id", "properties_json", "actor_type"]
    dataset = ds.dataset(path, format="parquet")
    have = [c for c in cols if c in dataset.schema.names]
    for batch in dataset.to_batches(columns=have):
        for row in batch.to_pylist():
            if row.get("actor_type", "synthetic") == "synthetic":
                yield normalize(row)


# ── 집계 ────────────────────────────────────────────────────────────────
def is_main_session(sid):
    """시드(seed:)·과거 구매(hist:) 세션이 아닌 본 탐색 세션"""
    return not (sid.startswith("seed:") or sid.startswith("hist:"))


def collect(events, run_id=None):
    """상세 방문(page_view_id) 단위로 모은다. 한 번 훑고 끝난다 — 순서가 섞여도 된다"""
    visits = defaultdict(lambda: {"depth": 0, "cart": False, "wish": False, "ing_sel": False,
                                  "rage": False, "nav": None, "pid": None, "persona": None,
                                  "session": None, "seeded": False, "pv": False})
    purchases = defaultdict(set)            # session -> 결제된 상품
    removed = set()                         # (persona, product) — 장바구니에서 뺀 것
    sessions = defaultdict(set)             # persona -> 본 탐색 세션
    runs = Counter()
    for ev in events:
        runs[ev["run_id"]] += 1
        if run_id and ev["run_id"] != run_id:
            continue
        name, sid = ev["event_name"], ev["session_id"]
        if ev["persona_id"] and is_main_session(sid) and not ev["seeded"]:
            sessions[ev["persona_id"]].add(sid)
        if name == "remove_from_cart":
            removed.add((ev["persona_id"], ev["product_id"]))
            continue
        if name == "purchase":
            for it in ev["props"].get("items") or []:
                purchases[sid].add(it.get("product_id"))
            continue
        pv = ev["page_view_id"]
        if not pv or not ev["product_id"]:
            continue
        if name not in ("product_view", "scroll_depth", "add_to_cart", "wishlist_toggle",
                        "text_selection", "rage_click"):
            continue
        v = visits[pv]
        v["pid"] = v["pid"] or ev["product_id"]
        v["persona"] = v["persona"] or ev["persona_id"]
        v["session"] = v["session"] or sid
        v["seeded"] = v["seeded"] or ev["seeded"]
        if name == "product_view":
            v["pv"] = True
            v["nav"] = ev["props"].get("navigation_source")
        elif name == "scroll_depth":
            v["depth"] = max(v["depth"], int(ev["props"].get("depth_percent") or 0))
        elif name == "add_to_cart":
            v["cart"] = True
        elif name == "wishlist_toggle" and ev["props"].get("action") == "add":
            v["wish"] = True
        elif name == "text_selection" and ev["props"].get("section_id") == INGREDIENTS_SECTION:
            v["ing_sel"] = True
        elif name == "rage_click":
            v["rage"] = True
    out = [v for v in visits.values() if v["pv"]]
    for v in out:
        v["removed"] = (v["persona"], v["pid"]) in removed
    return out, purchases, sessions, runs


def rate(flags):
    flags = list(flags)
    return (sum(flags) / len(flags) if flags else float("nan")), len(flags)


def within(obs, exp, n, lo=None, hi=None):
    """이항 3σ (또는 주어진 범위) 안인가"""
    if n == 0 or obs != obs:
        return None
    if lo is not None:
        s = 3 * math.sqrt(max(lo * (1 - lo), 1e-9) / n)
        return lo - s <= obs <= hi + s
    s = 3 * math.sqrt(max(exp * (1 - exp), 1e-9) / n)
    return abs(obs - exp) <= max(s, 1e-9)


def check(visits, purchases, sessions, G, style, registered):
    """(심은 규칙, 심은 값, 기대 결과, 복원 값, n, 판정) 행들"""
    SC = G.SCENARIO
    nsec = len(G.DETAIL_LAYOUT)
    d_full = observed_depth(100, nsec)
    d_deep = observed_depth(SC["deep_bounce_depth"], nsec)
    d_bounce = sorted({observed_depth(x, nsec) for x in SC["bounce_depth_choices"]})
    d_hist = observed_depth(25, nsec)
    rows = []

    main = [v for v in visits if not v["seeded"] and is_main_session(v["session"])]
    first = [v for v in main if v["nav"] != "history_back"]
    full = [v for v in first if v["depth"] >= d_full]
    rest = [v for v in first if v["depth"] < d_full]

    # 1. 목표 상품: 깊이 100 · 반드시 담는다
    r, n = rate(v["cart"] for v in full)
    rows.append(("목표 상품은 끝까지(100%) 보고 반드시 담는다 (target → depth=100, add_to_cart 항상)",
                 "depth 100 · 담기 1.0", f"끝까지 본 방문의 담기율 = 1.00", r, n, within(r, 1.0, n)))
    per = Counter(v["persona"] for v in full)
    r1 = sum(per.values()) / max(len(sessions), 1)
    rows.append(("  └ 목표 상품은 페르소나당 1개", "1개", "끝까지 본 방문 / 페르소나 = 1.00",
                 r1, len(sessions), abs(r1 - 1.0) < 0.02 if sessions else None))

    # 2. 이탈 상품: p_deep_bounce 로 깊이 90, 아니면 20~50
    r, n = rate(v["depth"] == d_deep for v in rest)
    rows.append((f"이탈 상품의 {SC['p_deep_bounce']:.0%} 는 깊이 {SC['deep_bounce_depth']} 까지 본다 (p_deep_bounce)",
                 f"p={SC['p_deep_bounce']}", f"이탈 방문 중 최대 스크롤 {d_deep}% 비율 = {SC['p_deep_bounce']:.2f}"
                 f" (7섹션 격자라 {SC['deep_bounce_depth']}→{d_deep})", r, n, within(r, SC["p_deep_bounce"], n)))
    each = (1 - SC["p_deep_bounce"]) / len(d_bounce)
    shares = " / ".join(f"{sum(v['depth'] == d for v in rest) / max(len(rest), 1):.3f}" for d in d_bounce)
    ok = all(within(sum(v["depth"] == d for v in rest) / max(len(rest), 1), each, len(rest)) for d in d_bounce) \
        if rest else None
    rows.append((f"  └ 나머지는 깊이 {SC['bounce_depth_choices']} 중 균등", "균등",
                 f"{d_bounce}% 각 {each:.3f}", shares, len(rest), ok))
    r, n = rate(v["depth"] < d_full for v in rest)
    rows.append(("  └ 이탈 상품은 100% 에 닿지 않는다", "depth<100", "이탈 방문 중 100% 미만 = 1.00",
                 r, n, within(r, 1.0, n)))

    # 3. 찜
    r, n = rate(v["wish"] for v in full)
    rows.append(("목표 상품 찜 확률 (wishlist_p_target)", f"p={SC['wishlist_p_target']}",
                 f"끝까지 본 방문의 찜 비율 = {SC['wishlist_p_target']:.2f}", r, n,
                 within(r, SC["wishlist_p_target"], n)))
    plain = [v for v in rest if not v["cart"] and v["pid"] not in registered]
    r, n = rate(v["wish"] for v in plain)
    rows.append(("이탈 상품 찜 확률 (wishlist_p_bounce)", f"p={SC['wishlist_p_bounce']}",
                 f"담지 않은 이탈 방문(등록 상품 제외)의 찜 비율 = {SC['wishlist_p_bounce']:.2f}", r, n,
                 within(r, SC["wishlist_p_bounce"], n)))

    # 4. 결제
    carted_full = [v for v in full if v["cart"]]
    r, n = rate(v["pid"] in purchases.get(v["session"], ()) for v in carted_full)
    exp = SC["p_purchase_after_cart"] * (1 - SC["p_payment_failed"])
    rows.append(("목표 상품 담은 뒤 결제 (p_purchase_after_cart × (1 − p_payment_failed))",
                 f"{SC['p_purchase_after_cart']} × (1−{SC['p_payment_failed']})",
                 f"같은 세션 결제율 = {exp:.3f}", r, n, within(r, exp, n)))

    # 5. 신규 브랜드(등록 상품) 발견 담기.
    #    담기 분기 순서가 target → 담았다 빼기(p_cart_regret, 1인 1회) → 등록 상품(p_new_brand_cart) 이라
    #    "나중에 빼지 않은 담기" 만 발견 구매다. 담았다 빼기가 먼저 걸리면 발견 추첨을 못 하므로
    #    기대 값은 p_new_brand_cart × (1 − p_cart_regret) ~ p_new_brand_cart 사이다.
    reg = [v for v in rest if v["pid"] in registered]
    r, n = rate(v["cart"] and not v["removed"] for v in reg)
    lo = SC["p_new_brand_cart"] * (1 - SC["p_cart_regret"])
    hi = SC["p_new_brand_cart"]
    rows.append(("등록 브랜드 상세에서 발견 담기 (p_new_brand_cart)", f"p={SC['p_new_brand_cart']}",
                 f"등록 상품 이탈 방문 중 담고 안 뺀 비율 {lo:.3f}~{hi:.3f}", r, n,
                 within(r, None, n, lo, hi)))
    other = [v for v in rest if v["pid"] not in registered]
    r2, n2 = rate(v["cart"] and not v["removed"] for v in other)
    rows.append(("  └ 비교: 일반 상품 이탈 방문에서 담고 안 뺀 비율", "경로 없음",
                 "0.00 (일반 이탈 상품은 담았다 빼기로만 담긴다)", r2, n2, within(r2, 0.0, n2) if n2 else None))
    n_rest = Counter(v["persona"] for v in rest)
    regret_p = {v["persona"] for v in rest if v["cart"] and v["removed"]}
    got = len(regret_p) / max(len(sessions), 1)
    exp = sum(1 - (1 - SC["p_cart_regret"]) ** n_rest.get(pid, 0) for pid in sessions) / max(len(sessions), 1)
    rows.append(("이탈 상품 하나를 담았다 뺀다 (p_cart_regret, 1인 최대 1회)", f"p={SC['p_cart_regret']} / 이탈 방문",
                 f"담았다 뺀 페르소나 비율 = 평균[1 − (1−{SC['p_cart_regret']})^이탈 방문 수] = {exp:.3f}",
                 got, len(sessions), within(got, exp, len(sessions)) if sessions else None))
    final = {v["persona"]: v["session"] for v in full}
    disc = [v for v in reg if v["cart"] and not v["removed"] and final.get(v["persona"]) == v["session"]]
    r, n = rate(v["pid"] in purchases.get(v["session"], ()) for v in disc)
    exp = SC["p_new_brand_buy"] * (1 - SC["p_payment_failed"])
    rows.append(("  └ 마지막 방문에서 발견 담은 등록 상품의 결제 (p_new_brand_buy × (1 − p_payment_failed))",
                 f"{SC['p_new_brand_buy']} × (1−{SC['p_payment_failed']})", f"같은 세션 결제율 = {exp:.3f}",
                 r, n, within(r, exp, n)))

    # 6. 성분 성향 → 전성분 드래그
    mx = effect_of(G, "ingredient", "p_ingredient_selection")
    base = SC["p_ingredient_selection"]
    engaged = [v for v in first if v["depth"] >= d_deep and v["persona"] in style]
    if engaged:
        scores = sorted(style[v["persona"]].get("ingredient", 0.5) for v in engaged)
        q75 = scores[int(len(scores) * 0.75)]
        groups = {"성분 성향 ≤0.5": [v for v in engaged if style[v["persona"]].get("ingredient", 0.5) <= 0.5],
                  f"성분 성향 상위 25% (≥{q75:.2f})":
                      [v for v in engaged if style[v["persona"]].get("ingredient", 0.5) >= q75]}
        got = {}
        for label, vs in groups.items():
            exp = (sum(min(0.95, base * style_factor(style[v["persona"]].get("ingredient", 0.5), mx))
                       for v in vs) / len(vs)) if vs else float("nan")
            r, n = rate(v["ing_sel"] for v in vs)
            got[label] = (r, exp)
            rows.append((f"성분 성향이 전성분 드래그를 올린다 (p_ingredient_selection {base} × 최대 {mx}배) — {label}",
                         f"{base} × f(성향)", f"정독 방문의 전성분 드래그율 = {exp:.3f}", r, n, within(r, exp, n)))
        (ra, ea), (rb, eb) = got.values()
        rows.append(("  └ 상위 25% / ≤0.5 배율", f"최대 {mx}배", f"{eb / ea:.2f}배",
                     rb / ra if ra else float("nan"), None,
                     (abs(rb / ra - eb / ea) < 0.25 * eb / ea) if ra else None))
    else:
        rows.append(("성분 성향이 전성분 드래그를 올린다", f"{base} × 최대 {mx}배",
                     "persona_style.json 필요", float("nan"), 0, None))

    # 7. 부정 시드 → rage_click
    neg = [v for v in visits if v["seeded"]]
    r, n = rate(v["rage"] for v in neg)
    rows.append(("부정 시드(별점 1~2) 상세에서 rage_click (neg_seed_p_rage)", f"p={SC['neg_seed_p_rage']}",
                 f"시드 상세 방문의 rage_click 비율 = {SC['neg_seed_p_rage']:.2f}", r, n,
                 within(r, SC["neg_seed_p_rage"], n)))

    # 8. 뒤로가기 재조회
    back = [v for v in main if v["nav"] == "history_back"]
    n_nontarget = len(rest)
    r = len(back) / n_nontarget if n_nontarget else float("nan")
    rows.append(("이탈 상품의 뒤로가기 재조회 (p_history_back)", f"p={SC['p_history_back']}",
                 f"재조회 수 / 이탈 방문 = {SC['p_history_back']:.2f}", r, n_nontarget,
                 within(r, SC["p_history_back"], n_nontarget)))
    r, n = rate(v["depth"] == d_hist for v in back)
    rows.append(("  └ 재조회는 얕게 (깊이 25)", "depth 25", f"최대 스크롤 {d_hist}% = 1.00", r, n,
                 within(r, 1.0, n)))

    # 9. 방문 횟수·탐색 상품 수
    dist = Counter(min(len(s), 3) for s in sessions.values())
    tot = sum(dist.values())
    shares = " / ".join(f"{dist.get(k, 0) / max(tot, 1):.3f}" for k in (1, 2, 3))
    ok = all(within(dist.get(k, 0) / max(tot, 1), w, tot) for k, w in zip((1, 2, 3), SC["visit_weights"])) \
        if tot else None
    rows.append(("페르소나 방문 횟수 1/2/3회 (visit_weights)", str(SC["visit_weights"]),
                 " / ".join(f"{w:.2f}" for w in SC["visit_weights"]), shares, tot, ok))
    lo_b, hi_b = SC["bounce_range"]
    exp = (lo_b + hi_b - 1) / 2
    per_p = Counter(v["persona"] for v in rest)
    r = sum(per_p.values()) / max(len(sessions), 1)
    rows.append((f"이탈 상품 수 {lo_b}~{hi_b - 1}개 균등 (bounce_range)", str(SC["bounce_range"]),
                 f"페르소나당 이탈 방문 평균 {exp:.2f} (+추천 경유로 바뀌어도 개수는 같다)", r, len(sessions),
                 abs(r - exp) < 0.1 if sessions else None))
    return rows


def fmt(x):
    if isinstance(x, str):
        return x
    if x != x:
        return "—"
    return f"{x:.3f}"


def main():
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--events", help="생성기 --out JSONL")
    src.add_argument("--cleaned", nargs="?", const="__env__",
                     help="cleaned_events Parquet 디렉터리 (생략하면 CLEANED_EVENTS_PATH)")
    src.add_argument("--cleaned-jsonl", help="cleaned_events 를 JSONL 로 뽑은 것")
    ap.add_argument("--run-id", default=None, help="simulation_run_id 하나만 본다")
    ap.add_argument("--markdown", action="store_true", help="문서 표 행으로 찍는다")
    a = ap.parse_args()

    if a.events:
        events, label = read_jsonl(a.events), f"생성기 원본 {a.events}"
    elif a.cleaned_jsonl:
        events, label = read_jsonl(a.cleaned_jsonl), f"cleaned_events JSONL {a.cleaned_jsonl}"
    else:
        path = a.cleaned if a.cleaned and a.cleaned != "__env__" else \
            os.environ.get("CLEANED_EVENTS_PATH") or os.path.join(ROOT, "data", "processed", "cleaned_events")
        if not os.path.exists(path):
            raise SystemExit(f"{path} 가 없다 — CLEANED_EVENTS_PATH 를 주거나 --events 로 생성기 JSONL 을 준다")
        events, label = read_parquet(path), f"cleaned_events Parquet {path}"

    G = load_generator()
    style_path = os.environ.get("PERSONA_STYLE_PATH") or os.path.join(
        ROOT, "simulator", "personas", "data", "persona_style.json")
    style = json.load(open(style_path, encoding="utf-8")) if os.path.exists(style_path) else {}
    reg_path = os.environ.get("REGISTERED_PRODUCTS_PATH") or G.REGISTERED_PRODUCTS
    registered = set()
    if os.path.exists(reg_path):
        with open(reg_path, encoding="utf-8") as f:
            registered = {json.loads(x)["product_id"] for x in f if x.strip()}

    visits, purchases, sessions, runs = collect(events, a.run_id)
    if len([r for r in runs if r]) > 1 and not a.run_id:
        print(f"⚠ 생성기 실행이 {len(runs)}개 섞여 있다 — --run-id 로 하나를 고르는 것이 맞다: "
              + ", ".join(f"{k}({v:,})" for k, v in runs.most_common(5)))
    print(f"입력: {label}")
    print(f"페르소나 {len(sessions):,}명 · 상세 방문 {len(visits):,}건 · 등록 상품 {len(registered)}개 · "
          f"성향 {len(style):,}명\n")
    rows = check(visits, purchases, sessions, G, style, registered)
    if a.markdown:
        print("| 심은 규칙 | 심은 값 | 기대 결과 | 복원 값 | n | 판정 |")
        print("|---|---|---|---:|---:|---|")
    for rule, planted, expect, got, n, ok in rows:
        mark = {True: "일치", False: "**어긋남**", None: "—"}[ok]
        if a.markdown:
            print(f"| {rule} | {planted} | {expect} | {fmt(got)} | {'' if n is None else f'{n:,}'} | {mark} |")
        else:
            print(f"[{mark:^5}] {rule}\n         심은 값 {planted} · 기대 {expect} · 복원 {fmt(got)}"
                  + ("" if n is None else f" (n={n:,})"))
    bad = sum(1 for r in rows if r[5] is False)
    print(f"\n{len(rows)}개 중 어긋남 {bad}개" + (" — 정제·집계 단계를 조사한다" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
