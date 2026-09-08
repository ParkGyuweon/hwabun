"""PA 에이전트 실행의 품질 지표를 잰다 — 재진입·커버리지·담기·교정률.

프롬프트를 고친 효과를 보려면 실행 두 개를 같은 잣대로 재야 한다. 사람 수가
다르면 건수는 못 비교하므로 **1인당·비율**을 함께 낸다.

사용:
    python simulator/agents/analyze_run_quality.py 이전.jsonl [나중.jsonl]
    ... --exclude=PA00001      # 2026-09-03 이전 로그는 이 사람이 오염돼 있다
판단 기록(*_decisions.jsonl)은 이벤트 파일 이름에서 유도해 있으면 같이 읽는다.
"""
import json
import os
import sys
from collections import Counter, defaultdict


def load(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def decisions_path(events_path):
    base, ext = os.path.splitext(events_path)
    return f"{base}_decisions{ext}"


_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
PRODUCTS_FILE = os.path.join(_ROOT, "batch", "ingest", "data", "products_200.json")
PERSONA_FILE = os.path.join(_ROOT, "simulator", "personas", "data", "personas_100_agent.json")


def persona_fit(ev, event_name):
    """페르소나가 행동을 이끄는가 — 그 행동의 상품이 **본인 리뷰 카테고리 안**인 비율과,
    카탈로그에서 무작위로 골랐을 때의 기대치, 그 비(lift).

    형식 지표(재진입·교정률)가 좋아도 이 값이 1.0 근처면 100명이 같은 사람처럼
    움직인 것이다. 2026-09-07 본실행: 담기 57% / 기대 56% = lift 1.02x.
    반환 (건수, 안 비율, 기대 비율, lift). 카탈로그·페르소나 파일이 없으면 None.
    """
    try:
        with open(PRODUCTS_FILE, encoding="utf-8") as f:
            cat = {q["product_id"]: q.get("secondary_category") for q in json.load(f)
                   if q.get("product_id") and q.get("secondary_category")}
        with open(PERSONA_FILE, encoding="utf-8") as f:
            pers = {q["persona_id"]: q for q in json.load(f)}
    except OSError:
        return None
    share = Counter(cat.values())
    total = len(cat)
    own = {}
    for pid, q in pers.items():
        own[pid] = {cat[r["product_id"]] for r in q.get("reviews", ())
                    if r.get("product_id") in cat}
    n = hit = 0
    exp = 0.0
    for e in ev:
        if e.get("event_name") != event_name:
            continue
        c = cat.get(e.get("product_id"))
        mine = own.get(e.get("persona_id"))
        if c is None or not mine:
            continue
        n += 1
        hit += c in mine
        exp += sum(share[k] for k in mine) / total
    if not n or not exp:
        return None
    return n, hit / n, exp / n, hit / exp


def measure(events_path, exclude=()):
    """exclude 에 준 persona_id 는 빼고 잰다.

    러너가 **페르소나를 고르기 전에** 페이지를 먼저 열어서, 그 화면의 이벤트가
    프론트 기본 페르소나(PA00001)로 찍힌다. 다른 사람 몫이 한 사람에게 쌓이므로
    사람 단위 지표를 그대로 재면 틀린다.
    """
    ev = [e for e in load(events_path) if e.get("persona_id") not in exclude]
    m = {"파일": os.path.basename(events_path), "이벤트": len(ev)}

    names = Counter(e.get("event_name") for e in ev)
    personas = {e.get("persona_id") for e in ev if e.get("persona_id")}
    n = len(personas) or 1
    m["사람"] = len(personas)

    # 상세 진입 — 사람마다 어떤 상품을 몇 번 열었는가
    views = defaultdict(Counter)
    for e in ev:
        if e.get("event_name") == "product_view" and e.get("persona_id") and e.get("product_id"):
            views[e["persona_id"]][e["product_id"]] += 1
    total_views = sum(sum(c.values()) for c in views.values())
    repeat_views = sum(sum(v - 1 for v in c.values() if v > 1) for c in views.values())
    revisitors = sum(1 for c in views.values() if any(v > 1 for v in c.values()))
    detail_uniq = {p for c in views.values() for p in c}

    m["상세 진입"] = total_views
    m["상세 진입 고유 상품"] = len(detail_uniq)
    m["재진입률"] = repeat_views / total_views if total_views else 0.0
    m["재진입한 사람"] = revisitors
    m["재진입한 사람 비율"] = revisitors / n

    imp = {e.get("product_id") for e in ev
           if e.get("event_name") == "product_impression" and e.get("product_id")}
    m["노출 고유 상품"] = len(imp)

    carts = [e for e in ev if e.get("event_name") == "add_to_cart"]
    m["add_to_cart"] = len(carts)
    m["담은 사람"] = len({e.get("persona_id") for e in carts if e.get("persona_id")})
    m["1인당 담기"] = len(carts) / n
    m["담긴 고유 상품"] = len({e.get("product_id") for e in carts if e.get("product_id")})

    for k in ("quick_look", "wishlist_toggle", "scroll_backtrack"):
        m[k] = names.get(k, 0)

    # 페르소나 적합 — 사람 사이 차이가 나는가. 1.0x 면 무작위와 같다
    for label, name in (("담기", "add_to_cart"), ("상세 진입", "product_view")):
        fit = persona_fit(ev, name)
        if fit:
            k, in_cat, expect, lift = fit
            m[f"{label} 리뷰카테고리 안"] = in_cat
            m[f"{label} 무작위 기대"] = expect
            m[f"{label} lift"] = f"{lift:.2f}x (n={k})"

    # 판단 기록 — 모델이 무엇을 골랐고 코드가 얼마나 고쳤는가
    dpath = decisions_path(events_path)
    if os.path.exists(dpath):
        dec = load(dpath)
        m["판단 기록"] = len(dec)
        if dec:
            acts = Counter(d.get("action") for d in dec)
            m["교정률"] = sum(1 for d in dec if d.get("corrected")) / len(dec)
            m["조작 실패"] = sum(1 for d in dec if d.get("succeeded") is False)
            m["reason 누락"] = sum(1 for d in dec if not (d.get("reason") or "").strip())
            m["행동 분포"] = dict(acts.most_common())
            clicks = acts.get("click_product", 0)
            m["click_product"] = clicks
            m["back_to_list"] = acts.get("back_to_list", 0)
            m["왕복비(back/click)"] = acts.get("back_to_list", 0) / clicks if clicks else 0.0
            # 상세에서 담을 때 target 을 비우던 문제
            cart_dec = [d for d in dec if d.get("action") == "add_to_cart"]
            if cart_dec:
                m["담기 target 누락"] = sum(1 for d in cart_dec if not d.get("llm_target"))
                m["담기 판단"] = len(cart_dec)
            m["모델"] = next((d.get("model") for d in dec if d.get("model")), "?")
    return m


def show(ms):
    keys = []
    for m in ms:
        for k in m:
            if k not in keys:
                keys.append(k)
    w = max(len(k) for k in keys)
    head = "".join(f"{m['파일'][:26]:>28}" for m in ms)
    print(f"{'':{w}}{head}")
    for k in keys:
        if k == "파일":
            continue
        cells = ""
        for m in ms:
            v = m.get(k, "-")
            if isinstance(v, float):
                pct = k.endswith("률") or k.endswith("비율") or k.endswith("안") or k.endswith("기대")
                v = f"{v*100:.1f}%" if pct else f"{v:.2f}"
            elif isinstance(v, dict):
                v = " ".join(f"{a}:{b}" for a, b in list(v.items())[:4])
            cells += f"{str(v):>28}"
        print(f"{k:{w}}{cells}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    args = [a for a in sys.argv[1:] if not a.startswith("--exclude=")]
    ex = tuple(v for a in sys.argv[1:] if a.startswith("--exclude=")
               for v in a.split("=", 1)[1].split(","))
    show([measure(p, ex) for p in args])
