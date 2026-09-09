# -*- coding: utf-8 -*-
"""처방 문장 생성(Jira 220)을 고정한다. LLM 은 가짜 클라이언트로 대신한다 — 네트워크 없이 돈다.

여기서 막고 싶은 것
  * §6 자동 거부가 새는 것 — basis 문자열·from 없는 화면·없는 숫자·아래로 옮기기·화살표 없음·비교 판단
  * keep 판정이나 신호 1개짜리 입력에 LLM 을 부르는 것
  * 같은 입력을 다시 생성하는 것 (저장본을 줘야 한다)
  * 키가 없을 때 500 으로 죽는 것 (503 이어야 한다)
실제 GMS 호출은 RUN_LIVE=1 이고 GMS_KEY 가 있을 때만 1회 돈다.
"""
import copy
import json
import os
import shutil
import sys
import tempfile
import unittest

BD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BD)
_TMP = tempfile.mkdtemp(prefix="rx220_")
os.environ["PRESCRIPTIONS_PATH"] = os.path.join(_TMP, "prescriptions.jsonl")
os.environ["REGISTERED_PRODUCTS_PATH"] = shutil.copy(
    os.path.join(BD, "..", "ingest", "data", "serving", "registered_products.jsonl"), os.path.join(_TMP, "r.jsonl"))

import prescription as rx                  # noqa: E402

INPUT = {
    "brand": {"name": "SSAFY Beauty", "product_count": 24},
    "target": {"content_kind": "clinical_claim", "label_ko": "임상 결과", "verb": "up", "avg_dwell_ms": 22300,
               "view_rate": 0.34, "cart_lift": 2.1, "sample_size": 947, "position_in_page": 6, "total_blocks": 10},
    "page_context": {"blocks_in_order": [
        {"content_kind": "product_image", "label_ko": "상품 이미지", "view_rate": 0.94, "cart_lift": 1.0},
        {"content_kind": "what_it_is", "label_ko": "제품 소개", "view_rate": 0.88, "cart_lift": 1.0},
        {"content_kind": "ingredient_callout", "label_ko": "성분 특징", "view_rate": 0.71, "cart_lift": 1.6},
        {"content_kind": "ingredient_list", "label_ko": "성분 목록", "view_rate": 0.62, "cart_lift": 2.3},
        {"content_kind": "usage_guide", "label_ko": "사용법", "view_rate": 0.48, "cart_lift": 0.9},
        {"content_kind": "clinical_claim", "label_ko": "임상 결과", "view_rate": 0.34, "cart_lift": 2.1},
        {"content_kind": "user_review", "label_ko": "사용자 리뷰", "view_rate": 0.31, "cart_lift": 1.8},
        {"content_kind": "what_else", "label_ko": "추가 설명", "view_rate": 0.22, "cart_lift": 0.7},
        {"content_kind": "faq", "label_ko": "자주 묻는 질문", "view_rate": 0.18, "cart_lift": 1.1},
        {"content_kind": "shipping", "label_ko": "배송 안내", "view_rate": 0.15, "cart_lift": 1.0}],
        "quick_exit_rate": 0.29, "brand_cart_rate": 0.061},
    "cross_screen_signals": [
        {"from": "누가 사나", "signal": "segment_top_content",
         "text": "지성 고객이 가장 오래 보는 글이 임상 결과. 이 고객군 체류의 29.0%", "value": 0.29, "sample_size": 1240},
        {"from": "고객이 찾는 성분", "signal": "dragged_ingredients_top3",
         "text": "드래그 상위 3개: 콜라겐(198회)·아연(186회)·펩타이드(148회)", "value": None, "sample_size": 532},
        {"from": "막히는 곳", "signal": "scroll_backtrack_by_location",
         "text": "성분 목록 구간 되돌아 읽기 388건", "value": 388, "sample_size": 4904},
        {"from": "무엇을 보고 사나", "signal": "validation_behavior",
         "text": "전성분 펼쳐 본 방문 담기율 13.2% vs 안 펼친 방문 5.1%", "value": 0.132, "sample_size": 4904}],
}
GOOD = {
    "how": "임상 결과를 성분 목록 바로 아래로 옮기세요. 시험 인원·기간·측정 항목·결과를 4줄 표로 바꾸세요.",
    "basis": [
        {"from": "무엇을 보고 사나", "text": "이 글을 본 사람의 담기율은 브랜드 평균의 2.1배이고, 열람률은 34.0%입니다."},
        {"from": "누가 사나", "text": "지성 고객이 가장 오래 보는 글이 임상 결과이고, 이 고객군 체류의 29.0%를 여기서 씁니다."},
    ],
    "verify": "열람률 34.0% → 48.0%. 열람률만 오르고 담기율 배수가 1.5배 아래로 내려가면 원래 위치로 되돌리세요.",
}


class FakeClient:
    """chat.completions.create 만 흉내낸다. 다음 응답을 큐에 넣는다."""

    def __init__(self, *outputs):
        self.outputs = [o if isinstance(o, str) else json.dumps(o, ensure_ascii=False) for o in outputs]
        self.calls = 0

        class _C:
            def __init__(s2, outer): s2.outer = outer

            def create(s2, **kw):
                s2.outer.calls += 1
                s2.outer.last_kwargs = kw
                raw = s2.outer.outputs.pop(0)
                msg = type("M", (), {"content": raw})()
                return type("R", (), {"choices": [type("Ch", (), {"message": msg})()]})()
        self.chat = type("Chat", (), {"completions": _C(self)})()


def inp(**over):
    d = copy.deepcopy(INPUT)
    for k, v in over.items():
        cur = d
        *path, last = k.split(".")
        for p in path:
            cur = cur[p]
        cur[last] = v
    return rx.PrescriptionInput.model_validate(d)


class TestPrompt(unittest.TestCase):
    def test_user_prompt_v03_rules(self):
        p = rx.user_prompt(inp())
        self.assertIn("34.0%", p)                      # 비율은 미리 퍼센트로
        self.assertNotIn("0.34", p)
        self.assertIn("6번째보다 **앞** 칸", p)         # up 이면 앞 칸으로만
        self.assertIn("무엇을 보고 사나 / 누가 사나 / 고객이 찾는 성분 / 막히는 곳", p)
        self.assertIn("현재값 → 목표값", p)
        self.assertIn('"basis": [{"from"', rx.SYSTEM)  # 출력 골격
        f = rx.user_prompt(inp(**{"target.verb": "fix"}))
        self.assertIn("위치는 그대로 두고", f)


class TestCheck(unittest.TestCase):
    def test_good_passes(self):
        self.assertEqual(rx.check(GOOD, inp()), [])

    def test_shape(self):
        bad = dict(GOOD, basis="문자열 근거")
        self.assertEqual(rx.check(bad, inp()), ["shape"])
        self.assertEqual(rx.check({"how": "x"}, inp()), ["shape"])

    def test_moves_down_rejected(self):
        bad = dict(GOOD, how="임상 결과를 사용자 리뷰 아래로 옮기세요.")
        self.assertIn("how_moves_down", rx.check(bad, inp()))

    def test_contradicts_verb(self):
        bad = dict(GOOD, how="임상 결과 칸을 빼세요.")
        self.assertIn("how_contradicts_verb", rx.check(bad, inp()))

    def test_vague_how(self):
        bad = dict(GOOD, how="임상 결과를 개선하세요.")
        self.assertIn("how_vague", rx.check(bad, inp()))

    def test_basis_from_and_diversity(self):
        bad = dict(GOOD, basis=[dict(GOOD["basis"][0]), dict(GOOD["basis"][0])])
        self.assertIn("basis_same_from", rx.check(bad, inp()))
        bad = dict(GOOD, basis=[dict(GOOD["basis"][0]), {"from": "상세페이지 집계", "text": "열람률 34.0%"}])
        self.assertIn("basis_from", rx.check(bad, inp()))
        ok = dict(GOOD, basis=[{"from": "[무엇을 보고 사나]", "text": "열람률은 34.0%입니다."}, dict(GOOD["basis"][1])])
        self.assertEqual(rx.check(ok, inp()), [])      # 대괄호는 벗겨서 본다

    def test_invented_number_rejected(self):
        bad = dict(GOOD, basis=[{"from": "무엇을 보고 사나", "text": "업계 평균 열람률은 52.0%입니다."}, dict(GOOD["basis"][1])])
        self.assertTrue(any(f.startswith("basis_numbers") for f in rx.check(bad, inp())))

    def test_judgement_not_in_input_rejected(self):
        bad = dict(GOOD, basis=[{"from": "무엇을 보고 사나", "text": "열람률 34.0%로 평균보다 높고 담기율은 2.1배입니다."},
                                dict(GOOD["basis"][1])])
        self.assertTrue(any(f.startswith("basis_judgement") for f in rx.check(bad, inp())))

    def test_verify_arrow_and_range(self):
        self.assertIn("verify_no_arrow", rx.check(dict(GOOD, verify="열람률을 34.0%에서 48%로 올리세요."), inp()))
        self.assertTrue(any(f.startswith("verify_range") for f in rx.check(dict(GOOD, verify="열람률 34.0% → 80.0%. 떨어지면 되돌리세요."), inp())))
        self.assertTrue(any(f.startswith("verify_range") for f in rx.check(dict(GOOD, verify="열람률 34.0% → 30.0%. 떨어지면 되돌리세요."), inp())))

    def test_forbidden_terms_and_dash(self):
        self.assertTrue(any(f.startswith("forbidden_terms") for f in rx.check(dict(GOOD, how="임상 결과를 성분 목록 바로 아래로 옮겨 전환율을 올리세요."), inp())))
        self.assertIn("dash", rx.check(dict(GOOD, how=GOOD["how"] + " — 꼭 하세요."), inp()))


class TestInputRules(unittest.TestCase):
    def test_keep_and_few_signals(self):
        self.assertIn("verb_keep", rx.input_problems(inp(**{"target.verb": "keep"})))
        one = inp(cross_screen_signals=INPUT["cross_screen_signals"][:1])
        self.assertIn("signals_lt_2", rx.input_problems(one))
        small = copy.deepcopy(INPUT["cross_screen_signals"])
        for s in small:
            s["sample_size"] = 50
        self.assertIn("signals_lt_2", rx.input_problems(inp(cross_screen_signals=small)))
        self.assertEqual(rx.input_problems(inp()), [])


class TestPrescribe(unittest.TestCase):
    def setUp(self):
        self.store = rx.Store(os.path.join(tempfile.mkdtemp(), "p.jsonl"))

    def test_generate_store_and_cache(self):
        c = FakeClient(GOOD)
        r = rx.prescribe(inp(), c, self.store)
        self.assertEqual(r["prescription"], GOOD)
        self.assertEqual(r["rejected_by"], [])
        self.assertFalse(r["cached"])
        self.assertEqual(r["prompt_version"], rx.PROMPT_VERSION)
        # 스키마 강제로 불렀나
        self.assertEqual(c.last_kwargs["response_format"]["type"], "json_schema")
        self.assertEqual(c.last_kwargs["temperature"], 0.0)
        # 같은 입력은 저장본 — LLM 을 다시 부르지 않는다
        r2 = rx.prescribe(inp(), c, self.store)
        self.assertTrue(r2["cached"])
        self.assertEqual(c.calls, 1)
        # 다른 저장 객체로 다시 읽어도 남아 있다
        again = rx.Store(self.store.path)
        self.assertIsNotNone(again.get(r["key"]))

    def test_rejected_returns_null_with_reasons(self):
        bad = dict(GOOD, how="임상 결과를 사용자 리뷰 아래로 옮기세요.")
        r = rx.prescribe(inp(), FakeClient(bad), self.store)
        self.assertIsNone(r["prescription"])
        self.assertIn("how_moves_down", r["rejected_by"])
        self.assertIsNotNone(r["raw"])

    def test_keep_never_calls_llm(self):
        c = FakeClient(GOOD)
        r = rx.prescribe(inp(**{"target.verb": "keep"}), c, self.store)
        self.assertIsNone(r["prescription"])
        self.assertEqual(r["rejected_by"], ["verb_keep"])
        self.assertEqual(c.calls, 0)


class TestEndpoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        import recommend_server as rs
        cls.rs = rs
        cls.client = TestClient(rs.app)

    def test_503_without_key_and_400ish_paths(self):
        rs = self.rs
        rs._rx_client, rs._rx_client_tried = None, True
        r = self.client.post("/api/prescription", json=INPUT)
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["detail"]["code"], "LLM_UNAVAILABLE")
        # keep 은 키 없이도 답한다
        keep = copy.deepcopy(INPUT); keep["target"]["verb"] = "keep"
        r = self.client.post("/api/prescription", json=keep)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["rejected_by"], ["verb_keep"])

    def test_endpoint_with_fake_client(self):
        rs = self.rs
        rs._rx_client, rs._rx_client_tried = FakeClient(GOOD), True
        rs._rx_store = rx.Store(os.path.join(tempfile.mkdtemp(), "p.jsonl"))
        r = self.client.post("/api/prescription", json=INPUT)
        self.assertEqual(r.status_code, 200, r.text)
        b = r.json()
        self.assertEqual(b["prescription"]["how"], GOOD["how"])
        self.assertEqual(b["content_kind"], "clinical_claim")
        r2 = self.client.post("/api/prescription", json=INPUT)
        self.assertTrue(r2.json()["cached"])

    @unittest.skipUnless(os.environ.get("RUN_LIVE") == "1" and (os.environ.get("GMS_KEY") or os.environ.get("OPENAI_API_KEY")),
                         "RUN_LIVE=1 + GMS_KEY 일 때만 실제 호출")
    def test_live_once(self):
        store = rx.Store(os.path.join(tempfile.mkdtemp(), "p.jsonl"))
        r = rx.prescribe(inp(), rx.make_client(), store)
        print("\n[live]", json.dumps(r, ensure_ascii=False)[:600])
        self.assertEqual(r["rejected_by"], [], r)


if __name__ == "__main__":
    unittest.main()
