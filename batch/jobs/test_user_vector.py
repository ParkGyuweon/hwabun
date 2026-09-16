"""user_vector.observe — 주문 단위 이벤트 펼치기 (Jira 320).

깨지면 안 되는 것
  * purchase·begin_checkout 은 product_id 없이 items[] 로 오고, 항목마다 log.ts 가중치(8.0·5.0)가 붙는다
  * 구매 상품은 converted 에 들어가 추천에서 제외된다(규칙 5)
  * quantity 는 강도에 영향이 없고, 같은 상품이 items 에 두 번 있어도 한 번만 센다
  * product_id 가 이미 있으면 예전과 같고, items 없는 주문 이벤트는 아무 일도 안 한다
"""
import os
import sys
import unittest

BD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BD)

import user_vector as UV  # noqa: E402


def _order(name, items, **props):
    return {"event_name": name, "product_id": None,
            "properties": {"order_id": "o1", "items": items, **props}}


class TestOrderItemsExpand(unittest.TestCase):
    def setUp(self):
        self.W = UV.BW.load()["event"]

    def test_purchase_items_get_purchase_weight_and_convert(self):
        st = UV.UserVector()
        st.observe(_order("purchase", [{"product_id": "P1", "quantity": 3, "unit_price": 10.0},
                                       {"product_id": "P2", "quantity": 1, "unit_price": 20.0}],
                          payment_method="test", paid_value=50.0, order_channel="backend"))
        self.assertEqual(st.pos["P1"], self.W["purchase"])
        self.assertEqual(st.pos["P2"], self.W["purchase"])          # quantity 3 vs 1 — 같은 강도
        self.assertEqual(st.converted, {"P1", "P2"})
        self.assertGreaterEqual(self.W["purchase"], 2 * self.W["add_to_cart"])   # log.ts 규칙 2:1

    def test_begin_checkout_items_get_checkout_weight(self):
        st = UV.UserVector()
        st.observe(_order("begin_checkout", [{"product_id": "P1", "quantity": 1, "unit_price": 10.0}],
                          cart_value=10.0, currency="USD"))
        self.assertEqual(st.pos["P1"], self.W["begin_checkout"])
        self.assertNotIn("P1", st.converted)                          # 결제 시작만으론 전환이 아니다

    def test_duplicate_item_counts_once_and_missing_items_is_noop(self):
        st = UV.UserVector()
        st.observe(_order("purchase", [{"product_id": "P1"}, {"product_id": "P1"}, {"sku_id": "x"}, None]))
        self.assertEqual(st.pos["P1"], self.W["purchase"])
        st2 = UV.UserVector()
        st2.observe({"event_name": "purchase", "product_id": None, "properties": {"order_id": "o2"}})
        st2.observe({"event_name": "page_view", "product_id": None, "properties": {}})
        self.assertEqual((st2.pos, st2.converted), ({}, set()))

    def test_product_level_event_unchanged(self):
        st = UV.UserVector()
        st.observe({"event_name": "add_to_cart", "product_id": "P9", "properties": {}})
        st.observe({"event_name": "purchase", "product_id": "P9",
                    "properties": {"items": [{"product_id": "P1"}]}})   # product_id 가 있으면 items 는 안 본다
        self.assertEqual(st.pos["P9"], self.W["add_to_cart"] + self.W["purchase"])
        self.assertNotIn("P1", st.pos)


if __name__ == "__main__":
    unittest.main()
