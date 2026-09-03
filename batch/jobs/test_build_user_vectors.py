"""로그 -> 사용자 벡터 상태 변환의 규칙을 고정한다.

여기서 막고 싶은 사고
  * 이벤트 순서가 뒤섞여 들어와 담았다 뺀 것이 뒤집히는 것
  * 귀속할 사람이 없는 이벤트가 누군가에게 붙는 것
  * 정규화된 벡터를 저장해 증분 갱신이 불가능해지는 것 (누적합이어야 한다)
"""
import os
import sys
import unittest

try:
    import numpy as np
except ModuleNotFoundError:
    np = None

BD = os.path.dirname(os.path.abspath(__file__))
if np is not None:
    sys.path.insert(0, BD)
    from batch.jobs.build_user_vectors import build
    from batch.jobs.product_encoder import Encoder


def ev(persona, name, product, seq, t="2026-09-01T00:00:00Z", **props):
    return {"persona_id": persona, "event_name": name, "product_id": product,
            "sequence_no": seq, "event_time": t, "properties": props}


@unittest.skipIf(np is None, "numpy is required")
class BuildUserVectorsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        e = Encoder()
        cls.matrix = np.asarray(e.matrix(), np.float64)
        cls.index = {p["product_id"]: i for i, p in enumerate(e.products)}
        ids = [p["product_id"] for p in e.products]
        cls.A, cls.B = ids[0], ids[1]

    def run_build(self, events, **kw):
        rows, skipped = build(events, self.index, self.matrix, **kw)
        return {r["persona_id"]: r for r in rows}, skipped

    def test_conversion_and_view_sets(self):
        rows, _ = self.run_build([
            ev("PC1", "product_view", self.A, 1),
            ev("PC1", "add_to_cart", self.A, 2),
            ev("PC1", "product_view", self.B, 3),
        ])
        r = rows["PC1"]
        self.assertEqual([self.A], r["converted"])
        self.assertEqual([self.A, self.B], sorted(r["viewed"]))
        self.assertEqual(2, r["n_products"])          # 스케줄 판정은 viewed 기준
        self.assertGreater(r["positive_w_sum"], 0.0)

    def test_remove_from_cart_undoes_conversion(self):
        """담았다 빼면 전환은 취소된다. 다만 감점 상품이 되지는 않는다.

        담기까지 갔다는 것은 **관여도가 가장 높은 상태**다 (규칙 7 이 원래
        가장 약한 감점을 주던 자리). 2026-09-03 개정으로 이 자리는 감점이
        아니라 **약한 긍정**이 됐다.
        """
        rows, _ = self.run_build([
            ev("PC1", "add_to_cart", self.A, 1),
            ev("PC1", "remove_from_cart", self.A, 2),
        ])
        r = rows["PC1"]
        self.assertEqual([], r["converted"])
        self.assertIn(self.A, r["viewed"])            # 뺐어도 본 것은 사실이다
        self.assertGreater(r["positive_w_sum"], 0.0)
        self.assertEqual(0.0, r["negative_w_sum"])

    def test_engaged_non_converted_is_weak_positive(self):
        """오래 붙들고 있었던 미전환 상품은 약한 긍정이다 (규칙 5 개정).

        감점 축이 카탈로그 평균 방향이 되어 정답까지 밀어내던 것을 고친 것이다.
        valid 1,975명에서 순위 개선/악화가 38.5:54.2 -> 47.5:45.2 로 바뀐다.
        """
        from batch.jobs.user_vector import ENGAGED_MIN, ENGAGED_POS_W
        self.assertEqual(3.0, ENGAGED_MIN)
        self.assertEqual(0.6, ENGAGED_POS_W)

        rows, _ = self.run_build([
            ev("PC1", "product_view", self.A, 1),
            ev("PC1", "section_dwell", self.A, 2,
               section_id="ingredients", dwell_ms=30000),
            ev("PC1", "section_dwell", self.A, 3,
               section_id="reviews", dwell_ms=30000),
            ev("PC1", "scroll_depth", self.A, 4, depth_percent=100),
        ])
        r = rows["PC1"]
        self.assertEqual([], r["converted"])           # 담지는 않았다
        self.assertGreater(r["positive_w_sum"], 0.0)   # 그래도 긍정 쪽이다
        self.assertEqual(0.0, r["negative_w_sum"])

    def test_bounce_is_still_negative(self):
        """열자마자 나간 상품은 그대로 감점이다. 임계값 아래는 안 바뀐다"""
        rows, _ = self.run_build([
            ev("PC1", "product_view", self.A, 1),
            ev("PC1", "add_to_cart", self.B, 2),       # 긍정 신호 하나는 있어야 한다
        ])
        r = rows["PC1"]
        self.assertGreater(r["negative_w_sum"], 0.0)

    def test_order_is_restored_from_sequence(self):
        """도착 순서가 뒤바뀌어도 sequence_no 로 복원한다"""
        forward = [ev("PC1", "add_to_cart", self.A, 1),
                   ev("PC1", "remove_from_cart", self.A, 2)]
        shuffled = list(reversed(forward))
        a, _ = self.run_build(forward)
        b, _ = self.run_build(shuffled)
        self.assertEqual(a["PC1"]["converted"], b["PC1"]["converted"])
        self.assertEqual([], b["PC1"]["converted"])

    def test_events_without_persona_are_skipped(self):
        rows, skipped = self.run_build([
            ev(None, "product_view", self.A, 1),
            ev("PC1", "product_view", self.A, 1),
        ])
        self.assertEqual(1, skipped)
        self.assertEqual({"PC1"}, set(rows))

    def test_actor_type_filter(self):
        events = [dict(ev("PC1", "add_to_cart", self.A, 1), actor_type="synthetic"),
                  dict(ev("U1", "add_to_cart", self.A, 1), actor_type="user")]
        rows, _ = self.run_build(events, actor_type="synthetic")
        self.assertEqual({"PC1"}, set(rows))

    def test_stores_sums_not_normalized_vectors(self):
        """증분 갱신을 위해 정규화 전 누적합을 저장한다"""
        rows, _ = self.run_build([ev("PC1", "add_to_cart", self.A, 1)])
        r = rows["PC1"]
        self.assertEqual(self.matrix.shape[1], len(r["positive_u_sum"]))
        norm = float(np.linalg.norm(r["positive_u_sum"]))
        self.assertGreater(norm, 1.0)                 # L2=1 이면 합이 아니라 벡터다
        self.assertAlmostEqual(r["positive_w_sum"], norm, places=4)


if __name__ == "__main__":
    unittest.main()
