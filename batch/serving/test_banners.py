# -*- coding: utf-8 -*-
"""히어로·배너 응답을 고정한다 (Jira 218, 계약 §5-1 · 프론트 확정 2026-09-09).

여기서 막고 싶은 것
  * hero.banner_type 이 비는 것 — 프론트가 이 값으로 이미지 변형을 고른다
  * banners 와 items 의 product_id 가 겹치는 것, 배너 안 중복
  * banner_slots=6&reserved=2 인데 칸 5·6 이 new_brand 가 아니거나 banner_value 키가 빠지는 것
  * 성분 축 배너가 위치가중 < 0.3 성분에 붙는 것
  * reason 이 key 하나가 아니거나 우선순위를 어기는 것
  * banner_slots 가 있을 때 메인 items 에 전용 칸이 섞이는 것 (전용 칸은 배너로 갔다)
  * banner_slots=0 이면 hero·banners 키가 없어야 하고 reserved 는 메인 안 (예전 동작 보존)
"""
import os
import shutil
import sys
import tempfile
import unittest

BD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BD)
_TMP = tempfile.mkdtemp(prefix="banner218_")
_COPY = os.path.join(_TMP, "registered_products.jsonl")
shutil.copy(os.path.join(BD, "..", "ingest", "data", "serving", "registered_products.jsonl"), _COPY)
os.environ["REGISTERED_PRODUCTS_PATH"] = _COPY

from fastapi.testclient import TestClient  # noqa: E402

import banners as bn                       # noqa: E402
import recommend_server as rs              # noqa: E402

client = TestClient(rs.app)
PID = "PC00001"
Q = {"persona_id": PID, "size": 10, "banner_slots": 6, "reserved": 2, "seed": "review"}
PRIORITY = ("attribute", "content", "cf", "new_brand", "popular")


class TestHeroBanners(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b = client.get("/api/recommend", params=Q).json()

    def test_shape(self):
        b = self.b
        self.assertEqual(b["banner_slots"], 6)
        self.assertEqual(b["banner_list_id"], "banner_row")
        self.assertEqual(b["axes"], ["concern", "segment"])
        self.assertEqual(len(b["banners"]), 6)
        self.assertEqual([x["banner_slot"] for x in b["banners"]], [1, 2, 3, 4, 5, 6])
        for x in b["banners"]:
            for k in ("banner_slot", "banner_type", "banner_value", "product_id", "product_name",
                      "brand_name", "score", "reserved", "trait_source", "reason", "product_source"):
                self.assertIn(k, x, k)
            self.assertIn(x["banner_type"], bn.AXES + ("new_brand",))
            self.assertIn(x["trait_source"], ("session", "profile", "coldstart", "explore"))

    def test_hero_always_has_banner_type(self):
        h = self.b["hero"]
        self.assertIsNotNone(h)
        self.assertEqual(h["product_id"], self.b["items"][0]["product_id"])
        self.assertIn(h["banner_type"], bn.AXES)
        self.assertIsNotNone(h["banner_value"])
        # 익명(시드 없음)도 hero 는 있어야 한다
        a = client.get("/api/recommend", params={"size": 10, "banner_slots": 6, "reserved": 2}).json()
        self.assertIn(a["hero"]["banner_type"], bn.AXES)
        self.assertEqual(a["state_source"], "cold_start")

    def test_no_overlap_and_no_dup(self):
        ids = {x["product_id"] for x in self.b["items"]}
        bs = [x["product_id"] for x in self.b["banners"]]
        self.assertEqual(ids & set(bs), set())
        self.assertEqual(len(bs), len(set(bs)))

    def test_reserved_goes_to_banner_slots_5_6(self):
        b = self.b
        res = [x for x in b["banners"] if x["reserved"]]
        self.assertEqual([x["banner_slot"] for x in res], [5, 6])
        for x in res:
            self.assertEqual(x["banner_type"], "new_brand")
            self.assertIn("banner_value", x)          # 키는 남기고
            self.assertIsNone(x["banner_value"])      # 값은 null (DATA 계약)
            self.assertEqual(x["product_source"], "brand_registered")
        self.assertEqual(b["reserved_filled"], 2)
        # 메인 items 에는 전용 칸이 없다 — 순수 순위
        self.assertFalse(any(x["reserved"] for x in b["items"]))
        self.assertFalse(any(x["product_id"].startswith("SB") for x in b["items"]))

    def test_axis_slots_cycle_axes(self):
        types = [x["banner_type"] for x in self.b["banners"][:4]]
        self.assertEqual(types, ["concern", "segment", "concern", "segment"])
        for x in self.b["banners"][:4]:
            self.assertIsNotNone(x["banner_value"])
            self.assertFalse(x["reserved"])
        # 같은 축 두 칸은 값이 같고 상품이 다르다
        self.assertEqual(self.b["banners"][0]["banner_value"], self.b["banners"][2]["banner_value"])

    def test_banner_value_is_vocab_string_and_product_has_it(self):
        e = rs.get_engine()
        for x in self.b["banners"]:
            if x["banner_type"] in ("concern", "clean", "ingredient", "category", "price_bin"):
                ax = e.planner.attrs_of[e.index[x["product_id"]]]
                self.assertIn(x["banner_value"], ax[x["banner_type"]], x)
            elif x["banner_type"] == "segment":
                self.assertIn(x["product_id"], e.planner.members["segment"][x["banner_value"]])

    def test_ingredient_axis_respects_position_weight(self):
        b = client.get("/api/recommend", params={**Q, "axes": "ingredient"}).json()
        e = rs.get_engine()
        ing = [x for x in b["banners"] if x["banner_type"] == "ingredient"]
        self.assertTrue(ing, "성분 축 배너가 하나도 없다")
        for x in ing:
            p = e.products[e.index[x["product_id"]]]
            w = e.enc.ingredient_values(p).get(x["banner_value"], 0.0)
            self.assertGreaterEqual(w, bn.INGREDIENT_MIN_POSITION, x)

    def test_reason_single_key_with_priority(self):
        for x in self.b["items"] + self.b["banners"]:
            self.assertEqual(len(x["reason"]), 1, x["reason"])
            self.assertIn(next(iter(x["reason"])), PRIORITY)
        self.assertEqual(bn.pick_reason({"new_brand": "n", "attribute": "a", "popular": "p"}), {"attribute": "a"})
        self.assertEqual(bn.pick_reason({"popular": "p", "cf": "c"}), {"cf": "c"})
        self.assertEqual(bn.pick_reason({}), {"popular": "많은 사용자가 선택한 상품"})

    def test_banner_slots_zero_keeps_old_behaviour(self):
        b = client.get("/api/recommend", params={"persona_id": PID, "size": 10, "reserved": 2,
                                                 "seed": "review"}).json()
        self.assertNotIn("hero", b)
        self.assertNotIn("banners", b)
        self.assertEqual(b["reserved_filled"], 2)           # 전용 칸은 메인 안 (예전 동작)
        self.assertEqual([x["position"] for x in b["items"] if x["reserved"]], [9, 10])

    def test_main_items_equal_reserved_zero_ranking(self):
        # banner_slots 가 있으면 items 는 reserved=0 순위와 같다 (전용 칸이 배너로 갔으니)
        a = client.get("/api/recommend", params={"persona_id": PID, "size": 10, "reserved": 0,
                                                 "seed": "review"}).json()
        self.assertEqual([x["product_id"] for x in a["items"]], [x["product_id"] for x in self.b["items"]])

    def test_invalid_axes_422(self):
        r = client.get("/api/recommend", params={**Q, "axes": "concern,nope"})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json()["detail"]["code"], "INVALID_AXES")

    def test_more_reserved_than_new_products_fills_without_flag(self):
        b = client.get("/api/recommend", params={**Q, "banner_slots": 12, "reserved": 10}).json()
        self.assertEqual(len(b["banners"]), 12)
        res = [x for x in b["banners"] if x["reserved"]]
        self.assertLessEqual(len(res), 10)
        self.assertEqual(b["reserved_filled"], len(res))
        for x in b["banners"]:
            self.assertIn(x["banner_type"], bn.AXES + ("new_brand",))
            if x["banner_type"] != "new_brand":
                self.assertIsNotNone(x["banner_value"])


if __name__ == "__main__":
    unittest.main()
