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
        rows, _ = self.run_build([
            ev("PC1", "add_to_cart", self.A, 1),
            ev("PC1", "remove_from_cart", self.A, 2),
        ])
        r = rows["PC1"]
        self.assertEqual([], r["converted"])
        self.assertIn(self.A, r["viewed"])            # 뺐어도 본 것은 사실이다
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
