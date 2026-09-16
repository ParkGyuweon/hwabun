import unittest
from datetime import datetime, timezone

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
