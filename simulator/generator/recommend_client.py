# -*- coding: utf-8 -*-
"""합성 로그 생성기 ↔ 추천 서버 연동 (Jira 221).

생성기가 `--recommend-url` 을 받으면 목록 화면마다 **실제 추천 서버**를 불러
items(메인 10) · hero 를 받고, 그 응답의 recommendation_id · algorithm · banner_slot ·
banner_type · banner_value · trait_source 를 이벤트에 **그대로** 싣는다.

배너는 **히어로 하나**다 (2026-09-10, Jira 239). 배너 행 6칸(전용 칸 5·6)은 09-10 기획 검토로
화면에서 빠졌고, 히어로는 `hero=new_brand` 로 신규 상품 중 점수 최고를 받는다(Jira 237).
그래서 기본값이 banner_slots=1 · reserved=0 · hero=new_brand 이고, 화면과 같게 `hero_from_response`
가 slot 1 하나를 만든다. 응답의 `banners[]` 는 화면에 없으므로 쓰지 않는다
(`banners_from_response` 는 배너 행이 살아날 때를 위해 남긴다). 프론트 184 가 서버 응답으로 하는 것과 같은 경로라,
DATA 의 banner_daily · recommendation 유입 Mart 가 실서비스 형태의 로그로 채워진다.

세션 상태도 서버에 넘긴다 — 사람이 상세를 보고 담을 때마다 `POST /api/events` 로
보내서 다음 목록의 추천이 그 행동을 반영하게 한다 (서버 state_source=events).

서버가 없거나 죽으면 한 번 경고하고 **예전 방식(banner_axes_v0 · 가짜 id)** 으로 돈다.
생성기가 서버 때문에 멈추면 안 된다 — 부하 테스트는 서버 없이도 돌아야 한다.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

# 서버에 넘기는 이벤트 — UserVector.observe 가 보는 것들 (behavior_weights). 나머지는 상태에 영향이 없다
STATE_EVENTS = frozenset({
    "product_view", "add_to_cart", "remove_from_cart", "wishlist_toggle", "purchase",
    "checkout_start", "quick_look", "recommendation_click", "banner_click", "product_click",
    "section_dwell", "scroll_depth", "variant_select", "review_filter_apply",
})


class RecommendClient:
    def __init__(self, base_url, banner_slots=1, reserved=0, hero="new_brand", timeout=5.0, log=print, opener=None):
        # Windows 의 urllib 는 localhost 를 ::1 로 먼저 시도해 실패한 뒤 127.0.0.1 로 가느라
        # 호출마다 약 2초를 잃는다 (실측 2,090ms vs 12ms). 서버는 127.0.0.1 에만 붙어 있다
        self.base = base_url.rstrip("/").replace("://localhost", "://127.0.0.1")
        self.banner_slots = int(banner_slots)
        self.reserved = int(reserved)
        self.hero = hero                        # top | new_brand (recommendation-io-spec §5 `hero`)
        self.timeout = timeout
        self.log = log
        self.opener = opener or urllib.request.urlopen
        self.available = True
        self.stats = {"recommend": 0, "observe": 0, "events_sent": 0, "errors": 0}

    # ── HTTP ──────────────────────────────────────────────────────────────
    def _call(self, method, path, body=None):
        if not self.available:
            return None
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with self.opener(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as ex:              # 4xx/5xx — 서버는 살아 있다
            self.stats["errors"] += 1
            self.log(f"[recommend] {method} {path} -> HTTP {ex.code}")
            return None
        except Exception as ex:                           # 연결 실패 — 서버가 없다
            self.stats["errors"] += 1
            if self.available:
                self.log(f"[recommend] 서버에 붙지 못했다 ({ex.__class__.__name__}) — "
                         f"이후 목록은 예전 방식(banner_axes_v0)으로 만든다")
            self.available = False
            return None

    # ── API ───────────────────────────────────────────────────────────────
    def recommend(self, persona_id, size=10):
        q = urllib.parse.urlencode({"persona_id": persona_id, "size": size,
                                    "banner_slots": self.banner_slots, "reserved": self.reserved,
                                    "hero": self.hero})
        resp = self._call("GET", f"/api/recommend?{q}")
        if not resp:
            return None
        self.stats["recommend"] += 1
        return resp

    def observe(self, persona_id, events):
        """생성기가 방금 낸 이벤트를 서버 상태에 반영한다. 상태에 영향 없는 이벤트는 걸러 보낸다"""
        rows = [{"event_name": ev["event_name"], "product_id": ev.get("product_id"),
                 "properties": ev.get("properties") or {}}
                for ev in events if ev["event_name"] in STATE_EVENTS]
        if not rows:
            return 0
        resp = self._call("POST", "/api/events", {"persona_id": persona_id, "events": rows})
        if resp is None:
            return 0
        self.stats["observe"] += 1
        self.stats["events_sent"] += len(rows)
        return len(rows)

    def summary(self):
        s = self.stats
        return (f"[recommend] 추천 호출 {s['recommend']:,} · 상태 전송 {s['observe']:,}회 "
                f"{s['events_sent']:,}건 · 오류 {s['errors']} · "
                f"{'연결됨' if self.available else '연결 끊김 → 폴백'}")


def hero_from_response(resp):
    """서버 hero → 화면의 배너 목록(히어로 하나, slot 1). 프론트 ProductListPage 가 히어로를
    `banner_slot: 1` 로 기록하는 것과 같다 (계약상 banner_slot 은 1 이상). hero 가 없으면 []"""
    h = resp.get("hero")
    if not h:
        return []
    return [{"slot": 1, "type": h["banner_type"], "value": h.get("banner_value"),
             "product_id": h["product_id"], "trait_source": h.get("trait_source", "session"),
             "reserved": bool(h.get("reserved", h.get("hero_policy") == "new_brand"))}]


def banners_from_response(resp):
    """서버 banners[] → 생성기가 쓰는 배너 dict (배너 행이 있을 때). 이벤트 property 이름은 DATA 계약대로"""
    out = []
    for b in resp.get("banners") or []:
        out.append({"slot": b["banner_slot"], "type": b["banner_type"], "value": b.get("banner_value"),
                    "product_id": b["product_id"], "trait_source": b.get("trait_source", "session"),
                    "reserved": bool(b.get("reserved"))})
    return out
