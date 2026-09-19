import os
import unittest
from datetime import datetime, timezone

from simulator.generator import gen_behavior_logs as gen

try:
    import numpy as np
except ModuleNotFoundError:
    np = None

if np is not None:
    from simulator.generator.gen_behavior_logs import (
        DEFAULT_GENERATOR_TYPE,
        DEFAULT_SCENARIO_ID,
        Emitter,
        SimulationContext,
        browse_list,
        BANNER_POLICY_VERSION,
        SCENARIO,
        checkout,
        make_banners,
        sample_personas,
        default_simulation_run_id,
        seed_session_id,
        selectable_variants,
        validate_property_contract,
        visit_detail,
    )


@unittest.skipIf(np is None, "numpy is required for the simulator generator")
class SyntheticEventMetadataTest(unittest.TestCase):
    def setUp(self):
        self.context = SimulationContext(
            scenario_id=DEFAULT_SCENARIO_ID,
            simulation_run_id="run_test_001",
            generator_type=DEFAULT_GENERATOR_TYPE,
        )

    def test_default_run_id_uses_utc_timestamp(self):
        run_id = default_simulation_run_id(
            datetime(2026, 8, 31, 1, 2, 3, tzinfo=timezone.utc)
        )

        self.assertEqual("run_20260831T010203Z", run_id)

    def test_emitter_adds_required_runtime_metadata(self):
        events = []
        emitter = Emitter(
            events,
            "PC00001",
            datetime(2026, 8, 31, 1, 0, 0),
            np.random.default_rng(42),
            self.context,
        )

        emitter.emit("session_start")

        self.assertEqual(
            {
                "scenario_id": "normal_day",
                "simulation_run_id": "run_test_001",
                "generator_type": "python_batch",
            },
            {
                key: events[0]["properties"][key]
                for key in ("scenario_id", "simulation_run_id", "generator_type")
            },
        )
        self.assertFalse(events[0]["properties"].get("seeded", False))
        self.assertTrue(events[0]["session_id"].startswith("run_test_001:"))

    def test_seed_emitter_marks_every_event_and_scopes_session(self):
        events = []
        session_id = seed_session_id(self.context, "PC00001", "P00001")
        emitter = Emitter(
            events,
            "PC00001",
            datetime(2026, 8, 31, 1, 0, 0),
            np.random.default_rng(42),
            self.context,
            session_id=session_id,
            is_seed=True,
        )

        emitter.emit("add_to_cart", "P00001")

        self.assertEqual("seed:run_test_001:PC00001:P00001", events[0]["session_id"])
        self.assertTrue(events[0]["properties"]["seeded"])

    def test_emitter_omits_absent_optional_properties(self):
        events = []
        emitter = Emitter(
            events,
            "PC00001",
            datetime(2026, 8, 31, 1, 0, 0),
            np.random.default_rng(42),
            self.context,
        )

        emitter.emit(
            "section_view",
            "P00001",
            section_id="ingredients",
            content_kind=None,
            content_ref=None,
        )

        self.assertEqual("ingredients", events[0]["properties"]["section_id"])
        self.assertNotIn("content_kind", events[0]["properties"])
        self.assertNotIn("content_ref", events[0]["properties"])

    def test_how_to_use_section_carries_usage_guide_content_kind(self):
        """사용법 아코디언은 실제 화면이 content_kind=usage_guide 를 싣는다
        (frontend/src/pages/ProductDetailPage.tsx:153). 합성 로그가 None 이면 대시보드
        콘텐츠 화면의 '사용법' 행이 통째로 빈다 — 09-19 dw 에서 usage_guide 0건이었다 (Jira 364).
        같은 자리의 전성분 아코디언은 실제 화면도 안 실으므로 None 이 맞다."""
        events = []
        emitter = Emitter(events, "PC00001", datetime(2026, 8, 31, 1, 0, 0),
                          np.random.default_rng(1), self.context)
        product = {"variants": [], "cat": "Moisturizers", "price": 30.0}
        # depth 100 이어야 how_to_use 까지 내려간다 (n_sec = 섹션 수 x depth/100)
        visit_detail(emitter, "P2", product, [], np.random.default_rng(2), depth_target=100,
                     engaged=False, entry_source="in_app")

        by_section = {}
        for e in events:
            if e["event_name"] != "section_view":
                continue
            by_section.setdefault(e["properties"]["section_id"], set()).add(
                e["properties"].get("content_kind"))

        self.assertIn("how_to_use", by_section)
        self.assertEqual({"usage_guide"}, by_section["how_to_use"])
        self.assertEqual({None}, by_section["ingredients"])

    def test_product_view_carries_recommendation_ids_when_entered_from_card(self):
        """추천 카드로 들어간 상세의 product_view 는 recommendation_id / list_id / position 을
        싣는다 (Jira 210). 안 실리면 데이터가 세션 순서로 추정해야 한다."""
        events = []
        emitter = Emitter(events, "PC00001", datetime(2026, 8, 31, 1, 0, 0),
                          np.random.default_rng(1), self.context)
        product = {"variants": [], "cat": "Moisturizers", "price": 30.0}
        meta = {"recommendation_id": "rec-P1-0001", "list_id": "similar_products", "position": 2}
        visit_detail(emitter, "P2", product, [], np.random.default_rng(2), depth_target=25,
                     engaged=False, entry_source="in_app", rec_meta=meta)
        pv = [e for e in events if e["event_name"] == "product_view"]
        self.assertEqual(len(pv), 1)
        for k, v in meta.items():
            self.assertEqual(pv[0]["properties"][k], v)
        self.assertEqual(pv[0]["properties"]["navigation_source"], "in_app")
        # 직접 들어온 상세엔 식별자가 없어야 한다 (선택 필드는 없으면 키 자체를 안 보낸다)
        events2 = []
        emitter2 = Emitter(events2, "PC00001", datetime(2026, 8, 31, 1, 0, 0),
                           np.random.default_rng(1), self.context)
        visit_detail(emitter2, "P2", product, [], np.random.default_rng(2), depth_target=25,
                     engaged=False, entry_source="in_app")
        pv2 = [e for e in events2 if e["event_name"] == "product_view"][0]
        self.assertNotIn("recommendation_id", pv2["properties"])

    def test_banner_events_use_banner_slot_and_share_ids_with_impression(self):
        """배너 이벤트(Jira 212·239). property 이름은 DATA 계약대로 `banner_slot` — `slot` 은 거부된다.
        화면은 히어로 하나(slot 1, list_id hero_banner, policy_version 동봉). 폴백 히어로는 new_brand 이고,
        force 한 상품은 그 자리를 차지해야 클릭이 노출된 배너에서 나온다."""
        rng = np.random.default_rng(3)
        catalog = {f"P{i}": {"cat": "Moisturizers", "price": 10.0 * i, "concern": "Dryness",
                             "variants": [], "n": i} for i in range(1, 13)}
        popular = sorted(catalog, key=lambda g: -catalog[g]["n"])
        persona = {"persona_id": "PC00001", "skin_type": "oily"}
        banners = make_banners(persona, catalog, popular[:8], popular, rng, force="P3", exclude={"P12"})
        self.assertEqual([b["slot"] for b in banners], [1])
        self.assertEqual(banners[0]["product_id"], "P3")
        self.assertEqual(banners[0]["type"], "new_brand")
        self.assertIsNone(banners[0]["value"])
        free = make_banners(persona, catalog, popular[:8], popular, rng, exclude={"P12"})
        self.assertEqual([b["slot"] for b in free], [1])
        self.assertEqual(free[0]["product_id"], "P1")          # 리뷰가 가장 적은 상품 (P12 는 제외)
        self.assertEqual(free[0]["type"], "new_brand")
        events = []
        emitter = Emitter(events, "PC00001", datetime(2026, 8, 31, 1, 0, 0), rng, self.context)
        browse_list(emitter, popular[:2], popular[:5], catalog, rng, dwell_ms=3000, first=True,
                    banners=banners)
        imps = [e for e in events if e["event_name"] == "banner_impression"]
        self.assertEqual(len(imps), 1)
        for e in imps:
            pr = e["properties"]
            self.assertNotIn("slot", pr)
            self.assertEqual(pr["banner_slot"], 1)
            self.assertEqual(pr["position"], pr["banner_slot"])
            self.assertEqual(pr["list_id"], "hero_banner")
            self.assertEqual(pr["policy_version"], BANNER_POLICY_VERSION)
            self.assertIn("banner_value", pr)
            self.assertIn(pr["trait_source"], ("coldstart", "profile", "session", "explore"))
        self.assertEqual(len({e["properties"]["recommendation_id"] for e in imps}), 1)
        batch, shown, source, algo = emitter.last_banner
        self.assertEqual(batch, imps[0]["properties"]["recommendation_id"])
        # new_brand 칸은 banner_value 키를 **남기고 null** 로 보낸다 (DATA 계약 required, Jira 213)
        self.assertTrue(all("banner_value" in e["properties"] and e["properties"]["banner_value"] is None
                            for e in imps if e["properties"]["banner_type"] == "new_brand"))

    def test_selectable_variants_excludes_initial_frontend_selection(self):
        product = {
            "variants": [
                {"sku_id": "SKU-1", "label": "30ml"},
                {"sku_id": "SKU-2", "label": "50ml"},
                {"sku_id": "SKU-3", "label": "100ml"},
            ]
        }

        self.assertEqual(product["variants"][1:], selectable_variants(product))
        self.assertEqual([], selectable_variants({}))

    def test_property_contract_accepts_valid_event(self):
        events = [
            {
                "event_name": "quick_look_close",
                "properties": {
                    "close_reason": "escape",
                    "dwell_ms": 1200,
                    "variants_viewed": 1,
                    "added_to_cart": False,
                    "wishlisted": False,
                },
            }
        ]

        result = validate_property_contract(events)

        self.assertEqual(1, result["checked"])

    def test_property_contract_rejects_invalid_enum(self):
        events = [
            {
                "event_name": "quick_look_close",
                "properties": {
                    "close_reason": "esc",
                    "dwell_ms": 1200,
                    "variants_viewed": 1,
                    "added_to_cart": False,
                    "wishlisted": False,
                },
            }
        ]

        with self.assertRaisesRegex(ValueError, "Event Properties"):
            validate_property_contract(events)


@unittest.skipIf(np is None, "numpy is required for the simulator generator")
class CheckoutTest(unittest.TestCase):
    """Jira 312 — 담기 뒤 결제 이벤트. 계약(event-properties-schema §4·§3.9·§3.15·§3.16)을 통과해야 한다."""

    def setUp(self):
        self.context = SimulationContext(scenario_id=DEFAULT_SCENARIO_ID, simulation_run_id="run_test_312",
                                         generator_type=DEFAULT_GENERATOR_TYPE)
        self.catalog = {"P1": {"price": 24.0}, "P2": {"price": 10.5}}

    def _run(self, seed, **sc_over):
        events = []
        e = Emitter(events, "PC00001", datetime(2026, 8, 31, 1, 0, 0), np.random.default_rng(seed), self.context)
        e.new_page("product_detail")
        e.emit("add_to_cart", "P1", quantity=1, price_usd=24.0)
        sc = {**SCENARIO, **sc_over}
        oid = checkout(e, self.catalog, ["P1", "P2"], e.rng, sc, quantities={"P2": 2})
        return events, oid

    def test_seed_flag_follows_emitter_not_checkout(self):
        """Jira 327 — 재구매 쌍은 seeded 없는 Emitter 로 낸다. 결제 이벤트의 seeded 는 Emitter 가 정한다"""
        for is_seed in (True, False):
            events = []
            e = Emitter(events, "PC00001", datetime(2026, 8, 31, 1, 0, 0), np.random.default_rng(3), self.context,
                        session_id=("seed:" if is_seed else "hist:") + "run:PC00001:P1", is_seed=is_seed)
            e.new_page("product_detail")
            e.emit("add_to_cart", "P1", quantity=1, price_usd=24.0)
            checkout(e, self.catalog, ["P1"], e.rng, {**SCENARIO, "p_payment_failed": 0.0}, restock=not is_seed)
            pu = next(x for x in events if x["event_name"] == "purchase")
            self.assertEqual(pu["properties"].get("seeded") is True, is_seed)
            self.assertTrue(all((x["properties"].get("seeded") is True) == is_seed for x in events))
            if not is_seed:
                rs = next(x for x in events if x["event_name"] == "purchase_reason_select")
                self.assertEqual("restock", rs["properties"]["reasons"][0])   # 재구매 사유가 앞

    def test_purchase_path_has_required_properties_and_passes_contract(self):
        events, oid = self._run(1, p_payment_failed=0.0, p_reason_answer=1.0)
        names = [x["event_name"] for x in events]
        self.assertEqual(["add_to_cart", "page_view", "begin_checkout", "purchase", "purchase_reason_select"], names)
        bc, pu, rs = events[2], events[3], events[4]
        self.assertEqual("cart", pu["page_type"])
        self.assertIsNone(pu["product_id"])                       # 주문 단위 이벤트 — 상품은 items[] 에
        self.assertEqual(2, len(pu["properties"]["items"]))
        self.assertEqual({"product_id": "P2", "quantity": 2, "unit_price": 10.5}, pu["properties"]["items"][1])
        self.assertEqual(45.0, pu["properties"]["order_value"])   # 24 + 2×10.5
        self.assertIn(pu["properties"]["payment_method"], ("kakaopay", "card"))
        self.assertEqual("backend", pu["properties"]["order_channel"])
        self.assertEqual("USD", pu["properties"]["currency"])
        self.assertLessEqual(pu["properties"]["paid_value"], pu["properties"]["order_value"])
        self.assertEqual(bc["properties"]["cart_value"], pu["properties"]["order_value"])
        self.assertEqual(oid, pu["properties"]["order_id"]); self.assertEqual(oid, rs["properties"]["order_id"])
        self.assertFalse(rs["properties"]["skipped"])
        self.assertTrue(1 <= len(rs["properties"]["reasons"]) <= 2)
        self.assertEqual(rs["properties"]["reasons"][0], rs["properties"]["primary_reason"])
        for k in ("pg_provider", "payment_id", "paid_at"):
            self.assertNotIn(k, pu["properties"])                  # 키 생략 (계약 §4: null 을 싣지 않는다)
        validate_property_contract(events)

    def test_skipped_survey_has_empty_reasons_and_no_primary(self):
        events, _ = self._run(2, p_payment_failed=0.0, p_reason_answer=0.0)
        rs = events[-1]
        self.assertEqual("purchase_reason_select", rs["event_name"])
        self.assertTrue(rs["properties"]["skipped"]); self.assertEqual([], rs["properties"]["reasons"])
        self.assertNotIn("primary_reason", rs["properties"])
        validate_property_contract(events)

    def test_payment_failed_path_stops_before_purchase(self):
        events, oid = self._run(3, p_payment_failed=1.0)
        self.assertIsNone(oid)
        self.assertEqual(["add_to_cart", "page_view", "begin_checkout", "payment_failed"], [x["event_name"] for x in events])
        self.assertEqual("conversion", events[-1]["intent"])
        validate_property_contract(events)

    def test_restock_reason_comes_first(self):
        events = []
        e = Emitter(events, "PC00001", datetime(2026, 8, 31, 1, 0, 0), np.random.default_rng(4), self.context,
                    session_id=seed_session_id(self.context, "PC00001", "P1#restock1"), is_seed=True)
        e.new_page("product_detail")
        checkout(e, self.catalog, ["P1"], e.rng, {**SCENARIO, "p_payment_failed": 0.0, "p_reason_answer": 1.0}, restock=True)
        rs = events[-1]
        self.assertEqual("restock", rs["properties"]["reasons"][0])
        self.assertTrue(all(x["properties"].get("seeded") for x in events))   # 시드 세션이면 전부 seeded


if __name__ == "__main__":
    unittest.main()


@unittest.skipIf(np is None, "numpy is required for the simulator generator")
class ViewCartCurrencyTest(unittest.TestCase):
    """Jira 340 — view_cart 도 currency 를 싣는다 (계약 §3.2: 금액은 currency 와 함께 해석한다).

    계약 303 이 view_cart.currency 를 필수로 올렸는데 생성기만 빠져 있었다. begin_checkout·purchase 처럼
    `checkout()` 단위 함수가 아니라 페르소나 동선 안에서 나오는 이벤트라 CLI 를 그대로 돌려 확인한다
    (--limit 20 이면 1초 안, view_cart 18건).
    """

    def _run(self, currency):
        import json, os, subprocess, sys, tempfile
        here = os.path.dirname(os.path.abspath(__file__))
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "behavior_logs.jsonl")
            r = subprocess.run([sys.executable, os.path.join(here, "gen_behavior_logs.py"),
                                "--limit", "20", "--currency", currency, "--out", out],
                               capture_output=True, text=True, encoding="utf-8", errors="replace",
                               env={**os.environ, "PYTHONIOENCODING": "utf-8"})
            self.assertEqual(0, r.returncode, r.stderr[-2000:])
            with open(out, encoding="utf-8") as f:
                return [json.loads(ln) for ln in f if ln.strip()]

    def test_view_cart_carries_currency_in_both_modes(self):
        for currency, value_type in (("USD", float), ("KRW", int)):
            with self.subTest(currency=currency):
                events = self._run(currency)
                money_events = [x for x in events if x["event_name"] in ("view_cart", "begin_checkout", "purchase")]
                view_cart = [x for x in money_events if x["event_name"] == "view_cart"]
                self.assertGreater(len(view_cart), 0)
                for x in money_events:                       # 금액을 싣는 세 이벤트가 같은 통화를 쓴다
                    self.assertEqual(currency, x["properties"].get("currency"), x["event_name"])
                for x in view_cart:
                    self.assertIsInstance(x["properties"]["cart_value"], value_type)

    def test_every_add_to_cart_carries_price_props(self):
        """Jira 342 — 담기 6곳 전부 가격 속성. Quick Look 경로(:784)만 빠져 관측 담기의 38% 가 unit_price NULL 이었다"""
        for currency, keys in (("USD", {"price_usd"}), ("KRW", {"unit_price", "currency"})):
            with self.subTest(currency=currency):
                events = self._run(currency)
                adds = [x for x in events if x["event_name"] == "add_to_cart"]
                quick = [x for x in adds if x["properties"].get("entry_source") == "quick_look"]
                self.assertGreater(len(quick), 0)                # Quick Look 담기가 표본에 있어야 검사가 의미 있다
                missing = [x for x in adds if not keys <= set(x["properties"])]
                self.assertEqual([], missing, f"가격 속성 없는 add_to_cart {len(missing)}/{len(adds)}건 "
                                              f"(entry_source: {sorted({x['properties'].get('entry_source') for x in missing})})")

    def test_history_sessions_open_detail_before_cart_but_seed_sessions_do_not(self):
        """Jira 345·349 — hist:(재구매 쌍) 세션은 노출→조회→담기→구매 최소 퍼널을 갖고, seed: 긍정 시드는 계약대로 조회 없이 담기만"""
        events = self._run("KRW")
        by_sid = {}
        for x in events:
            by_sid.setdefault(x["session_id"], []).append(x)
        hist = {s: v for s, v in by_sid.items() if s.startswith("hist:")}
        seed_pos = {s: v for s, v in by_sid.items()
                    if s.startswith("seed:") and any(x["event_name"] == "add_to_cart" for x in v)}
        self.assertGreater(len(hist), 0); self.assertGreater(len(seed_pos), 0)
        for sid, v in hist.items():
            v = sorted(v, key=lambda x: x["sequence_no"])
            names = [x["event_name"] for x in v]
            with self.subTest(sid=sid):
                self.assertIn("product_view", names)
                self.assertLess(names.index("product_view"), names.index("add_to_cart"))
                # Jira 349 — 노출이 조회보다 앞서야 퍼널 단계가 노출→조회로 귀속된다
                self.assertIn("product_impression", names)
                self.assertLess(names.index("product_impression"), names.index("product_view"))
                imp = v[names.index("product_impression")]["properties"]
                for k in ("list_id", "position", "hold_ms", "visible_ratio"):
                    self.assertIn(k, imp)                     # 계약 필수 4종
                pv = v[names.index("product_view")]
                pages = [x for x in v if x["event_name"] == "page_view"]
                # 상세 진입 page_view = product_view 와 같은 page_view_id (결제 단계에도 page_view 가 있어 위치로 찾지 않는다)
                detail_pg = [x for x in pages if x["page_view_id"] == pv["page_view_id"]]
                self.assertEqual(1, len(detail_pg), "상세 진입 page_view 가 정확히 하나여야 한다")
                self.assertEqual("in_app", pv["properties"]["navigation_source"])
                self.assertEqual(pv["properties"]["navigation_source"],
                                 detail_pg[0]["properties"]["navigation_source"])   # 계약 §3.4
                self.assertEqual("session_start", pages[0]["properties"]["navigation_source"])
                # 노출은 상세가 아니라 목록 페이지에서 난다
                self.assertNotEqual(v[names.index("product_impression")]["page_view_id"], pv["page_view_id"])
        for sid, v in seed_pos.items():
            with self.subTest(sid=sid):
                seed_names = [x["event_name"] for x in v]
                self.assertNotIn("product_view", seed_names)
                self.assertNotIn("product_impression", seed_names)

    def test_history_back_revisit_exists_and_is_marked(self):
        """Jira 350 — 상세 → 목록 복귀 → 같은 상품 재조회가 navigation_source=history_back 으로 남는다.

        마트가 재조회를 건수 집계에서 빼는 로직을 검증하려면 로그에 이 모양이 있어야 한다 (데이터·프론트 요청)."""
        events = self._run("KRW")
        back = [x for x in events
                if x["event_name"] == "product_view"
                and x["properties"].get("navigation_source") == "history_back"]
        self.assertGreater(len(back), 0, "20명 표본에 뒤로가기 재조회가 한 건도 없다")

        by_sid = {}
        for x in events:
            by_sid.setdefault(x["session_id"], []).append(x)
        for ev in back[:5]:
            v = sorted(by_sid[ev["session_id"]], key=lambda x: x["sequence_no"])
            with self.subTest(sid=ev["session_id"], product=ev["product_id"]):
                views = [x for x in v
                         if x["event_name"] == "product_view" and x["product_id"] == ev["product_id"]]
                self.assertGreaterEqual(len(views), 2, "재조회면 같은 상품 조회가 둘 이상이어야 한다")
                self.assertNotEqual("history_back", views[0]["properties"]["navigation_source"])  # 첫 진입은 아니다
                # 계약 §3.4 — 같은 상세 진입의 page_view 와 값이 같아야 한다
                pg = [x for x in v if x["event_name"] == "page_view"
                      and x["page_view_id"] == ev["page_view_id"]]
                self.assertEqual(1, len(pg))
                self.assertEqual("history_back", pg[0]["properties"]["navigation_source"])
                # 목록 복귀도 history_back 으로 남는다
                self.assertTrue(any(x["event_name"] == "page_view"
                                    and x["properties"].get("navigation_source") == "history_back"
                                    and x["page_view_id"] != ev["page_view_id"] for x in v))



class ResolveNowTest(unittest.TestCase):
    """09-17 — 시연 로그는 기준 시각을 오늘로 옮길 수 있어야 한다.

    고정 시각(2026-08-28)으로 만들면 마트가 그 시점에 쌓이는데 대시보드 기본 조회창은
    '어제까지 14일' 이라 영영 안 걸린다. 평가용 재현성은 기본값으로 지킨다."""

    def setUp(self):
        self._saved = os.environ.get("GEN_NOW")

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("GEN_NOW", None)
        else:
            os.environ["GEN_NOW"] = self._saved

    def test_default_is_the_fixed_constant(self):
        """안 주면 고정값 — 평가 데이터셋이 같은 씨앗으로 같은 파일이어야 한다"""
        os.environ.pop("GEN_NOW", None)
        self.assertEqual(datetime(2026, 8, 28, 12, 0, 0), gen._resolve_now())
        os.environ["GEN_NOW"] = ""
        self.assertEqual(datetime(2026, 8, 28, 12, 0, 0), gen._resolve_now())

    def test_today_is_noon_kst_expressed_in_utc(self):
        """사람이 주는 값은 한국 시각, 안에서는 UTC.

        occurred_at 이 `...Z` 로 나가므로 UTC 여야 한다. 예전에는 한국 시각에 Z 만 붙여
        **9시간 미래**가 됐고, 정오 넘는 이벤트가 다음 날로 넘어갔다 (09-17)."""
        os.environ["GEN_NOW"] = "today"
        got = gen._resolve_now()
        now = datetime.now()
        self.assertEqual(datetime(now.year, now.month, now.day, 12, 0, 0),
                         got + gen.KST_OFFSET, "KST 로 되돌리면 오늘 정오여야 한다")

    def test_explicit_dates_are_read_as_kst(self):
        os.environ["GEN_NOW"] = "2026-09-17"
        self.assertEqual(datetime(2026, 9, 17, 12, 0, 0), gen._resolve_now() + gen.KST_OFFSET)
        os.environ["GEN_NOW"] = "2026-09-17T09:30:00"
        self.assertEqual(datetime(2026, 9, 17, 9, 30, 0), gen._resolve_now() + gen.KST_OFFSET)

    def test_generated_events_do_not_land_in_the_future(self):
        """GEN_NOW=today 로 만든 로그를 KST 로 되돌렸을 때 **내일**이 나오면 안 된다"""
        os.environ["GEN_NOW"] = "today"
        now = gen._resolve_now()
        last_kst = now + gen.KST_OFFSET
        today = datetime.now()
        self.assertLessEqual(last_kst.date(), today.date(),
                             "기준 시각이 오늘을 넘으면 모든 이벤트가 미래가 된다")

    def test_bad_value_stops_instead_of_guessing(self):
        os.environ["GEN_NOW"] = "어제"
        with self.assertRaises(SystemExit):
            gen._resolve_now()


@unittest.skipIf(np is None, "numpy is required for the simulator generator")
class SamplePersonasTest(unittest.TestCase):
    """--limit 층화 추출 (Jira 318). 파일이 stratum 순 정렬이라 앞에서 자르면 한 층만 남는다."""

    def _personas(self):
        strata = [("combination|light|3", 550), ("dry|light|3", 200), ("normal|fair|3", 150),
                  ("oily|medium|4", 90), ("normal|deep|7+", 10)]
        P, n = [], 0
        for st, cnt in strata:
            for _ in range(cnt):
                n += 1
                P.append({"persona_id": f"PC{n:05d}", "stratum": st, "skin_type": st.split("|")[0]})
        return P

    def test_head_keeps_old_behavior(self):
        P = self._personas()
        picked = sample_personas(P, 100, how="head")
        self.assertEqual(picked, P[:100])
        self.assertEqual({p["stratum"] for p in picked}, {"combination|light|3"})

    def test_stratified_is_proportional_and_reproducible(self):
        P = self._personas()
        picked = sample_personas(P, 100)
        self.assertEqual(len(picked), 100)
        by = {}
        for p in picked:
            by[p["stratum"]] = by.get(p["stratum"], 0) + 1
        self.assertEqual(by, {"combination|light|3": 55, "dry|light|3": 20, "normal|fair|3": 15,
                              "oily|medium|4": 9, "normal|deep|7+": 1})
        self.assertEqual(len({p["persona_id"] for p in picked}), 100)
        self.assertEqual([p["persona_id"] for p in picked],
                         [p["persona_id"] for p in sample_personas(P, 100)])
        self.assertEqual([p["persona_id"] for p in picked], sorted(p["persona_id"] for p in picked))

    def test_limit_at_or_above_population_returns_everyone(self):
        P = self._personas()
        self.assertEqual(len(sample_personas(P, 5000)), len(P))
        self.assertEqual(len(sample_personas(P, None)), len(P))
