# -*- coding: utf-8 -*-
"""grain 단위 노출·클릭 가드 (Jira 358).

총량이 맞아도 특정 grain 에서 클릭 > 노출 이 날 수 있다. Q5 는 마트 grain
(event_date_kst, brand_id, product_id, 실행축) 으로 보므로 총량 점검은 이것을 못 잡는다.
09-18 리포트의 `banner_daily` ctr>1 1행이 `python_batch` 로 잡힌 것이 그 예다.

여기서 막고 싶은 것
  * 총량은 맞는데 grain 하나에서 어긋난 경우 — **총량 검사가 놓치는 바로 그 경우**
  * 상품·추천·배너 세 쌍 전부
  * 날짜·상품·실행축이 다르면 다른 grain 이다
  * strict 가 아니면 경고만 하고 통과
"""
import os
import sys
import unittest

BD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BD)

import gen_behavior_logs as G  # noqa: E402


def ev(name, product="P1", day="2026-09-18", brand="B1", run="run-1"):
    return {
        "event_name": name,
        "product_id": product,
        "occurred_at": f"{day}T01:02:03.000Z",
        "properties": {"brand_id": brand, "actor_type": "synthetic", "source": "simulator",
                       "generator_type": "python_batch", "scenario_id": "normal_day",
                       "simulation_run_id": run},
    }


class CatchesWhatTotalsMiss(unittest.TestCase):
    def test_총량은_맞는데_grain_하나가_어긋나면_잡는다(self):
        # 노출 2 · 클릭 2 — 총량으로는 통과한다
        events = [ev("product_impression", "P1"), ev("product_impression", "P1"),
                  ev("product_click", "P1"), ev("product_click", "P2")]
        totals_ok = (sum(1 for e in events if e["event_name"] == "product_impression")
                     >= sum(1 for e in events if e["event_name"] == "product_click"))
        self.assertTrue(totals_ok, "총량 검사는 통과해야 이 테스트가 의미를 가진다")
        bad = G.check_ctr_grains(events)
        self.assertEqual(1, len(bad))
        self.assertEqual(0, bad[0]["impressions"])
        self.assertEqual(1, bad[0]["clicks"])

    def test_노출이_충분하면_통과한다(self):
        events = [ev("product_impression"), ev("product_impression"), ev("product_click")]
        self.assertEqual([], G.check_ctr_grains(events))

    def test_노출과_클릭이_같아도_통과한다(self):
        events = [ev("product_impression"), ev("product_click")]
        self.assertEqual([], G.check_ctr_grains(events))


class AllThreePairs(unittest.TestCase):
    def test_추천도_본다(self):
        bad = G.check_ctr_grains([ev("recommendation_click")])
        self.assertEqual(1, len(bad))
        self.assertIn("recommendation", bad[0]["pair"])

    def test_배너도_본다(self):
        bad = G.check_ctr_grains([ev("banner_click")])
        self.assertEqual(1, len(bad))
        self.assertIn("banner", bad[0]["pair"])

    def test_세_쌍이_섞여도_각각_센다(self):
        bad = G.check_ctr_grains([ev("product_click"), ev("recommendation_click"),
                                  ev("banner_click")])
        self.assertEqual(3, len(bad))

    def test_다른_쌍의_노출로는_메워지지_않는다(self):
        # 추천 노출이 있어도 상품 클릭의 분모가 되지 않는다
        bad = G.check_ctr_grains([ev("recommendation_impression"), ev("product_click")])
        self.assertEqual(1, len(bad))
        self.assertIn("product_click", bad[0]["pair"])


class GrainBoundaries(unittest.TestCase):
    def test_날짜가_다르면_다른_grain_이다(self):
        events = [ev("product_impression", day="2026-09-17"),
                  ev("product_click", day="2026-09-18")]
        self.assertEqual(1, len(G.check_ctr_grains(events)))

    def test_상품이_다르면_다른_grain_이다(self):
        events = [ev("product_impression", "P1"), ev("product_click", "P2")]
        self.assertEqual(1, len(G.check_ctr_grains(events)))

    def test_실행축이_다르면_다른_grain_이다(self):
        events = [ev("product_impression", run="run-1"), ev("product_click", run="run-2")]
        self.assertEqual(1, len(G.check_ctr_grains(events)))

    def test_같은_grain_이면_합쳐서_센다(self):
        events = [ev("product_impression"), ev("product_impression"),
                  ev("product_click"), ev("product_click")]
        self.assertEqual([], G.check_ctr_grains(events))


class StrictMode(unittest.TestCase):
    def test_기본은_멈춘다(self):
        with self.assertRaises(ValueError) as cm:
            G.validate_ctr_grains([ev("product_click")], strict=True)
        self.assertIn("grain", str(cm.exception))

    def test_허용하면_경고만_하고_목록을_돌려준다(self):
        bad = G.validate_ctr_grains([ev("product_click")], strict=False)
        self.assertEqual(1, len(bad))

    def test_위반이_없으면_빈_목록이다(self):
        self.assertEqual([], G.validate_ctr_grains([ev("product_impression")], strict=True))


if __name__ == "__main__":
    unittest.main(verbosity=2)
