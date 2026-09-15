# -*- coding: utf-8 -*-
"""쇼핑몰 백엔드 카탈로그 동기화(Jira 222)를 고정한다 — 가짜 백엔드(opener)로 돈다.

여기서 막고 싶은 것
  * 백엔드 요약(camelCase)이 등록 입력으로 잘못 매핑되는 것 (brandName 없으면 brandId, rating 은 안 넘김)
  * 바뀌지 않은 상품을 매번 다시 인코딩하는 것 (해시로 건너뛴다)
  * 목록에서 빠진 백엔드 상품이 남아 추천에 계속 나오는 것 / 시연 시드가 잘못 중단되는 것
  * 백엔드가 죽었을 때 500 이 나거나 추천이 멎는 것
  * 계약 위반 상품 하나가 전체 동기화를 멎게 하는 것
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
import urllib.error

BD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BD)
_TMP = tempfile.mkdtemp(prefix="sync222_")
os.environ["REGISTERED_PRODUCTS_PATH"] = shutil.copy(
    os.path.join(BD, "..", "ingest", "data", "serving", "registered_products.jsonl"), os.path.join(_TMP, "r.jsonl"))
os.environ.setdefault("SESSION_EVENTS_PATH", os.path.join(tempfile.mkdtemp(prefix="sess_"), "session_events.jsonl"))  # 세션 로그가 레포에 쌓이지 않게
os.environ["PRESCRIPTIONS_PATH"] = os.path.join(_TMP, "p.jsonl")
os.environ.pop("SHOP_BACKEND_URL", None)

import catalog_sync as cs                  # noqa: E402
import recommend_server as rs              # noqa: E402


def summary(pid, name="테스트 세럼", brand="Gamma Lab", sec="Treatments", ter="Face Serums",
            hl=("Dryness", "Vegan"), krw=30800, brand_name=True):
    return {"productId": pid, "brandId": "brand-gamma", "brandName": brand if brand_name else None,
            "categoryId": "skincare", "productName": name, "secondaryCategory": sec, "tertiaryCategory": ter,
            "priceKrw": krw, "priceBin": "20-35", "rating": 4.25, "lovesCount": 0,
            "primaryImageUrl": None, "highlights": list(hl)}


class FakeBackend:
    def __init__(self, products, ingredients=None, fail_list=False):
        self.products = products
        self.ingredients = ingredients or {}
        self.fail_list = fail_list
        self.calls = []

    def __call__(self, req, timeout=None):
        url = req.full_url
        self.calls.append(url)
        if self.fail_list:
            raise ConnectionRefusedError("down")
        path = url.split("://", 1)[1].split("/", 1)[1]

        class R:
            def __init__(s, body): s.body = body
            def __enter__(s): return s
            def __exit__(s, *a): return False
            def read(s): return json.dumps(s.body).encode("utf-8")
        if path == "api/products":
            return R(self.products)
        pid = path.rsplit("/", 1)[1]
        p = next((x for x in self.products if x["productId"] == pid), None)
        if p is None:
            raise urllib.error.HTTPError(url, 404, "nf", {}, None)
        return R({"product": p, "variants": [], "ingredients": self.ingredients.get(pid, "Water, Glycerin, Niacinamide"),
                  "description": None})


class TestMapping(unittest.TestCase):
    def test_to_registration(self):
        inp = cs.to_registration(summary("bk-1"), "Water, Kaolin")
        self.assertEqual(inp["product_id"], "bk-1")
        self.assertEqual(inp["brand_name"], "Gamma Lab")
        self.assertEqual(inp["price_krw"], 30800)
        self.assertEqual(inp["ingredients"], "Water, Kaolin")
        self.assertNotIn("rating", inp)                         # 우리 §4.2 로 다시 주입
        inp2 = cs.to_registration(summary("bk-2", brand_name=False), None)
        self.assertEqual(inp2["brand_name"], "brand-gamma")     # brandName 없으면 brandId
        self.assertEqual(inp2["ingredients"], "")


class TestSync(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e = rs.get_engine()

    def test_add_skip_unchanged_update_and_deactivate(self):
        e = self.e
        n0 = len(e.products)
        seed_id = e.products[0]["product_id"]                 # 세포라 원천 — 백엔드 목록에도 시드로 있다 (Jira 308)
        seed_before = dict(e.products[0])
        be = FakeBackend([summary("bk-1"), summary("bk-2", name="크림", sec="Moisturizers", ter="Moisturizers"),
                          summary(seed_id, name="백엔드가 부르는 이름")])
        r = cs.sync(e, "http://localhost:8090", opener=be, log=lambda m: None)
        self.assertIsNone(r["error"])
        self.assertEqual(sorted(r["added"]), ["bk-1", "bk-2"])
        self.assertEqual(r["seed_kept"], 1)
        self.assertEqual(r["replaced"], [])
        self.assertEqual(e.products[0], seed_before)               # 원천 행 불변 (product_source·rating·loves)
        self.assertFalse(e.new_flags()[0])
        self.assertFalse(any(seed_id in u for u in be.calls if "/api/products/" in u))   # 원천은 상세도 안 부른다
        self.assertEqual(len(e.products), n0 + 2)
        self.assertEqual(e.products[e.index["bk-1"]]["sync_source"], "shop_backend")
        self.assertTrue(e.rec.new_mask()[e.index["bk-1"]])      # 어휘집 밖 브랜드 → 전용 칸 후보
        self.assertEqual(sum(1 for u in be.calls if u.endswith("/api/products")), 1)
        self.assertEqual(sum(1 for u in be.calls if "/api/products/" in u), 2)   # 상세 2회
        # 두 번째 동기화 — 바뀐 게 없으면 상세도 안 부르고 인코딩도 안 한다
        be.calls.clear()
        r2 = cs.sync(e, "http://localhost:8090", opener=be, log=lambda m: None)
        self.assertEqual(r2["unchanged"], 2)
        self.assertEqual(r2["added"], [])
        self.assertEqual(sum(1 for u in be.calls if "/api/products/" in u), 0)
        # 요약이 바뀌면 그 상품만 갱신
        be.products[0]["priceKrw"] = 49000
        r3 = cs.sync(e, "http://localhost:8090", opener=be, log=lambda m: None)
        self.assertEqual(r3["replaced"], ["bk-1"])
        self.assertEqual(r3["unchanged"], 1)
        self.assertEqual(e.products[e.index["bk-1"]]["price_krw"], 49000.0)      # 원화 그대로 (Jira 302)
        # 목록에서 빠지면 판매 중단, 시연 시드(SSAFY)는 그대로
        be.products = [be.products[0]]
        r4 = cs.sync(e, "http://localhost:8090", opener=be, log=lambda m: None)
        self.assertEqual(r4["deactivated"], ["bk-2"])
        self.assertIn("bk-2", e.inactive)
        self.assertNotIn("SB000001", e.inactive)
        # 다시 나타나면 재활성
        be.products.append(summary("bk-2", name="크림", sec="Moisturizers", ter="Moisturizers"))
        r5 = cs.sync(e, "http://localhost:8090", opener=be, log=lambda m: None)
        self.assertIn("bk-2", r5["replaced"] + r5["added"])
        self.assertNotIn("bk-2", e.inactive)

    def test_backend_down_returns_error_without_raising(self):
        e = self.e
        n0 = len(e.products)
        r = cs.sync(e, "http://localhost:8090", opener=FakeBackend([], fail_list=True), log=lambda m: None)
        self.assertIsNotNone(r["error"])
        self.assertEqual(len(e.products), n0)

    def test_contract_violation_rejects_one_not_all(self):
        e = self.e
        be = FakeBackend([summary("bk-bad", sec="Nope", ter="Nope"), summary("bk-ok", name="ok")])
        r = cs.sync(e, "http://localhost:8090", opener=be, log=lambda m: None)
        self.assertIn("bk-bad", r["rejected"])
        self.assertTrue(any("secondary_category" in x for x in r["rejected"]["bk-bad"]))
        self.assertIn("bk-ok", r["added"] + r["replaced"])

    def test_endpoint_without_source_400_and_with_source(self):
        from fastapi.testclient import TestClient
        c = TestClient(rs.app)
        self.assertEqual(c.post("/api/catalog/sync").status_code, 400)
        # 없는 포트 — 200 에 error 를 채운다 (추천은 계속)
        r = c.post("/api/catalog/sync", params={"source": "http://127.0.0.1:1"})
        self.assertEqual(r.status_code, 200)
        self.assertIsNotNone(r.json()["error"])
        self.assertEqual(c.get("/api/recommend", params={"size": 5}).status_code, 200)


if __name__ == "__main__":
    unittest.main()


class IngredientsField(unittest.TestCase):
    """2026-09-14 백엔드 상세 모양 변화 — ingredientsText 로 옮겨도, 이름 목록이어도 전성분을 읽는다"""

    def test_text_field_first(self):
        from catalog_sync import _ingredients_of
        self.assertEqual(_ingredients_of({"ingredients": "", "ingredientsText": "Water, Glycerin"}), "Water, Glycerin")
        self.assertEqual(_ingredients_of({"ingredients": "Water, Kaolin"}), "Water, Kaolin")
        self.assertEqual(_ingredients_of({"ingredients": [{"name": "Water"}, {"name": "Glycerin"}]}), "Water, Glycerin")
        self.assertIsNone(_ingredients_of({"ingredients": "", "ingredientsText": None}))
