"""
사용자 벡터 집계 — 행동 로그를 v_u⁺ / v_u⁻ 로 만든다.

이벤트를 하나씩 먹고 상태를 갱신하는 구조라, 배치로 한 번에 돌려도 되고
Kafka 컨슈머가 실시간으로 물려도 된다. 상태는 상품 단위 가중치 사전이라 작다.

집계 규칙 (측정 근거는 docs/ai/recommendation-design.md)
    1. envelope 의 product_id 가 없는 이벤트는 버린다.
       목록 화면 이벤트가 여기 걸린다 — 그리드 체류는 상품에 귀속되지 않는다.
    2. scroll_depth 는 상품별 **최대 도달 1건**만 가중한다. 누적하면 끝까지 내려간
       사용자가 장바구니보다 높은 점수를 받는다.
    3. section_dwell / section_view 도 **상품 × 섹션당 1건**만 센다.
       같은 규칙이 없으면 스크롤을 오르내릴 때마다 쌓여 add_to_cart 를 압도한다.
    4. reason=checkpoint 인 체류는 버린다. 화면에 떠 있었다는 뜻이지 봤다는 뜻이 아니다.
    5. **전환(장바구니·좋아요)한 상품만 v_u⁺ 로 간다.** 눌러봤지만 아무것도 안 한
       상품은 통째로 v_u⁻ 로 보낸다. "보긴 봤다"는 좋아한다는 뜻이 아니다.
    6. UI 좌절(rage_click, dead_click)은 전환 여부와 무관하게 항상 v_u⁻ 로 간다.
       망설임(remove_from_cart)과 비교(scroll_backtrack)는 감점이 아니라
       **관여도**로 센다 — 그 상품을 계속 붙들고 있었다는 뜻이기 때문이다.
    7. 미전환 상품의 부정 강도는 **관여도에 반비례**한다.
       오래 본 상품은 취향과 방향이 가까우므로 강하게 감점하면 자기 취향을
       스스로 깎아내린다. 담았다 뺀 상품은 구매 직전까지 간 것이라 가장 약하다.

3·5 를 적용하면 Recall@10 이 5.9% -> 12.6%, 롱테일이 6.1% -> 19.6% 가 된다.
"""
import os
import sys

import numpy as np

BD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BD)
import behavior_weights as BW

# 전환으로 보는 이벤트. 이 상품만 v_u⁺ 로 간다
CONVERT = {"add_to_cart", "quantity_change"}
UNDO = {"remove_from_cart"}

# ── 부정 축의 강도 ─────────────────────────────────────────────────────
# 미전환 상품의 부정 강도는 **관여도에 반비례**한다 (규칙 7).
#
#   neg = NEG_W0 / (1 + engagement / NEG_TAU)
#
# 오래 본 상품은 그 사람 취향과 방향이 가깝다. 그것을 강하게 감점하면
# 자기 취향을 스스로 깎아내리게 된다. 반대로 열자마자 나간 상품은
# 취향과 멀다는 뜻이므로 감점을 세게 준다.
#
#   즉시 이탈(관여 1.0)  -> 0.80    확실한 거절
#   정독 후 이탈(5.0)    -> 0.44    망설임
#   담았다 뺌(13.0)      -> 0.24    재고(再考). 구매 직전까지 갔다
NEG_W0 = 1.0
NEG_TAU = 4.0

# 감점 이벤트를 두 갈래로 가른다. 분류는 log.ts 의 EVENT_INTENT 를 그대로 따른다.
#   friction   (rage_click, dead_click) — UI 좌절. 관여의 반대이므로 절대값 그대로 감점
#   그 외      (remove_from_cart=hesitation, scroll_backtrack=comparison)
#              — "그 상품을 계속 붙들고 있었다" 는 뜻이므로 **관여도에 더한다**
FRICTION_INTENT = "friction"


class UserVector:
    """페르소나 한 명의 누적 상태. 이벤트를 순서대로 먹인다"""

    def __init__(self, weights=None):
        self.W = weights or BW.load()
        self.pos = {}        # product_id -> 관여도 (양의 가중 + 망설임/비교의 절대값)
        self.friction = {}   # product_id -> UI 좌절 감점 (양수로 저장)
        self._depth = {}     # product_id -> 최대 스크롤 %
        self._seen = set()   # (product_id, section_id, event_name) 중복 차단
        self.converted = set()
        self.viewed = set()

    # ── 이벤트 1건 ────────────────────────────────────────────────────────
    def observe(self, ev):
        g = ev.get("product_id")
        if not g:
            return                                        # 규칙 1
        name = ev["event_name"]
        pr = ev.get("properties") or {}

        if name in UNDO:
            self.converted.discard(g)
            self.viewed.add(g)

        if name == "scroll_depth":                        # 규칙 2
            d = pr.get("depth_percent") or 0
            if d > self._depth.get(g, -1):
                self._depth[g] = d
            self.viewed.add(g)
            return

        if name in ("section_dwell", "section_view"):      # 규칙 3·4
            if name == "section_dwell" and pr.get("reason") == "checkpoint":
                return
            key = (g, pr.get("section_id"), name)
            if key in self._seen:
                return
            self._seen.add(key)
            w = (self.W["section"].get(pr.get("section_id"), 1.0)
                 if name == "section_dwell" else self.W["event"]["section_view"])
        else:
            w = self.W["event"].get(name, 0.0)

        if name in CONVERT:
            self.converted.add(g)
        elif name == "wishlist_toggle":
            (self.converted.add(g) if pr.get("action") != "remove"
             else self.converted.discard(g))

        if w > 0:
            self.pos[g] = self.pos.get(g, 0.0) + w
            self.viewed.add(g)
        elif w < 0:                                        # 규칙 6
            self.viewed.add(g)
            if self.W["intent"].get(name) == FRICTION_INTENT:
                # UI 좌절 — 상품이 싫은 것이 아니라 화면이 말을 안 들은 것이지만,
                # product_id 가 실린 이상 그 상품에 귀속시킨다. 관여와 무관하다
                self.friction[g] = self.friction.get(g, 0.0) - w
            else:
                # 망설임(담았다 뺌) · 비교(되돌아 읽기) — 그 상품을 붙들고 있었다는
                # 뜻이므로 관여도로 센다. 결과적으로 부정 강도가 **약해진다**
                self.pos[g] = self.pos.get(g, 0.0) - w

    def observe_all(self, events):
        for e in events:
            self.observe(e)
        return self

    # ── 상품별 가중치 ─────────────────────────────────────────────────────
    def weights(self):
        """(긍정 상품 가중치, 부정 상품 가중치). 규칙 5·7 을 여기서 적용한다"""
        eng = dict(self.pos)                               # 관여도
        for g, d in self._depth.items():                   # 규칙 2
            eng[g] = eng.get(g, 0.0) + BW.scroll_weight(d, self.W["scroll"])

        p, n = {}, dict(self.friction)                     # 규칙 6 (UI 좌절)
        for g, w in eng.items():
            if g in self.converted:
                p[g] = w                                   # 규칙 5 — 전환한 상품
            else:
                # 규칙 7 — 미전환 감점은 관여도에 반비례한다
                n[g] = n.get(g, 0.0) + NEG_W0 / (1.0 + w / NEG_TAU)
        return p, n

    # ── 상품 공간 벡터 ─────────────────────────────────────────────────────
    def vectors(self, index, matrix):
        """index: product_id -> 행 번호,  matrix: (상품수, 차원)
           반환 (v_u⁺, v_u⁻). 신호가 없으면 None"""
        p, n = self.weights()

        def build(ws):
            v = np.zeros(matrix.shape[1], dtype=np.float64)
            s = 0.0
            for g, w in ws.items():
                i = index.get(g)
                if i is not None:
                    v += w * matrix[i]
                    s += w
            if s <= 0:
                return None
            nrm = np.linalg.norm(v)
            return None if nrm < 1e-9 else v / nrm

        return build(p), build(n)

    def __repr__(self):
        p, n = self.weights()
        return (f"<UserVector 긍정 {len(p)}개(합 {sum(p.values()):.1f}) "
                f"부정 {len(n)}개(합 {sum(n.values()):.1f})>")


if __name__ == "__main__":
    import json
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    path = sys.argv[1] if len(sys.argv) > 1 else None
    if not path:
        print("사용법: python user_vector.py <행동로그.jsonl>")
        raise SystemExit(0)
    from collections import defaultdict
    states = defaultdict(UserVector)
    n = 0
    for line in open(path, encoding="utf-8"):
        e = json.loads(line)
        states[e["persona_id"]].observe(e)
        n += 1
    print(f"이벤트 {n:,}건 -> 사용자 {len(states):,}명")
    pw = [len(s.weights()[0]) for s in states.values()]
    nw = [len(s.weights()[1]) for s in states.values()]
    print(f"1인당 긍정 상품 {np.mean(pw):.2f}개 / 부정 상품 {np.mean(nw):.2f}개")
    for pid, s in list(states.items())[:3]:
        print(f"  {pid}  {s}")
