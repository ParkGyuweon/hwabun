# -*- coding: utf-8 -*-
"""처방 문장 생성(Jira 220 → v0.3 정합 Jira 225)을 고정한다. LLM 은 가짜 클라이언트 — 네트워크 없이 돈다.

여기서 막고 싶은 것 (규격 §7 자동 거부 11개 + 입력 규칙)
  * basis 문자열 · from 여섯 화면 밖 · 같은 화면만 · 없는 숫자 · 없는 비교 판단
  * up 인데 insert_after 칸 이름이 없거나 다른 칸 · "빼세요/아래로"
  * 금지 표현(banned) 거부, functional_only 는 심사 없으면 거부, needs_evidence 는 꼬리표만
  * verify 화살표 없음 · 목표값 범위 밖 · 줄표
  * keep·신호 부족·insert_after 가 순서 표에 없음 → LLM 안 부름
  * 같은 입력 재생성 안 함 (input_hash 봉투) · 키 없으면 503
실제 GMS 호출은 RUN_LIVE=1 이고 GMS_KEY 가 있을 때만 1회.
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
_TMP = tempfile.mkdtemp(prefix="rx225_")
os.environ["PRESCRIPTIONS_PATH"] = os.path.join(_TMP, "prescriptions.jsonl")
os.environ["REGISTERED_PRODUCTS_PATH"] = shutil.copy(
    os.path.join(BD, "..", "ingest", "data", "serving", "registered_products.jsonl"), os.path.join(_TMP, "r.jsonl"))
os.environ["SESSION_EVENTS_PATH"] = os.path.join(_TMP, "s.jsonl")
os.environ.pop("SHOP_BACKEND_URL", None)

import prescription as rx                  # noqa: E402

INPUT = {   # 규격 §3 v0.3 예시 그대로
    "brand": {"name": "SSAFY Beauty", "product_count": 24},
    "target": {"content_kind": "clinical_claim", "label_ko": "임상 결과", "verb": "up", "dwell_sec": 22,
               "view_rate_text": "34.0%", "cart_lift_text": "2.1배", "sample_size": 947,
               "position_in_page": 6, "total_blocks": 10, "insert_after": "성분 목록"},
    "page_context": {"blocks_in_order": [
        {"label_ko": "상품 이미지", "view_rate_text": "94.0%", "cart_lift_text": "1.0배"},
        {"label_ko": "제품 소개", "view_rate_text": "88.0%", "cart_lift_text": "1.0배"},
        {"label_ko": "성분 특징", "view_rate_text": "71.0%", "cart_lift_text": "1.6배"},
        {"label_ko": "성분 목록", "view_rate_text": "62.0%", "cart_lift_text": "2.3배"},
        {"label_ko": "사용법", "view_rate_text": "48.0%", "cart_lift_text": "0.9배"},
        {"label_ko": "임상 결과", "view_rate_text": "34.0%", "cart_lift_text": "2.1배"},
        {"label_ko": "사용자 리뷰", "view_rate_text": "31.0%", "cart_lift_text": "1.8배"},
        {"label_ko": "추가 설명", "view_rate_text": "22.0%", "cart_lift_text": "0.7배"},
        {"label_ko": "자주 묻는 질문", "view_rate_text": "18.0%", "cart_lift_text": "1.1배"},
        {"label_ko": "배송 안내", "view_rate_text": "15.0%", "cart_lift_text": "1.0배"}],
        "quick_exit_rate_text": "29.0%", "brand_cart_rate_text": "6.1%"},
    "cross_screen_signals": [
        {"from": "누가 사나", "signal": "segment_top_content",
         "text": "지성 고객이 가장 오래 보는 글이 임상 결과입니다. 이 고객군 체류의 29.0%입니다.", "sample_size": 1240},
        {"from": "고객이 찾는 성분", "signal": "dragged_ingredients_top3",
         "text": "드래그 상위 3개는 콜라겐 198회, 아연 186회, 펩타이드 148회입니다.", "sample_size": 532},
        {"from": "막히는 곳", "signal": "scroll_backtrack_by_location",
         "text": "성분 목록 구간에서 위로 다시 올려 읽은 기록이 388건입니다.", "sample_size": 4904},
        {"from": "무엇을 보고 사나", "signal": "validation_behavior",
         "text": "전성분을 펼쳐 본 방문의 담기율은 13.2%, 안 펼친 방문은 5.1%입니다.", "sample_size": 4904}],
}
GOOD = {
    "how": "임상 결과를 성분 목록 바로 아래로 옮기세요. 시험 인원과 기간과 결과를 표로 정리하세요.",
    "basis": [
        {"from": "무엇을 보고 사나", "text": "이 글을 본 사람의 담기율은 브랜드 평균의 2.1배이고, 열람률은 34.0%입니다."},
        {"from": "누가 사나", "text": "지성 고객이 가장 오래 보는 글이 임상 결과이고, 이 고객군 체류의 29.0%를 여기서 씁니다."},
    ],
    "verify": "열람률 34.0% → 48.0%. 열람률만 오르고 담기율 배수가 1.5배 아래로 내려가면 원래 위치로 되돌리세요.",
}


class FakeClient:
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


def bad(**over):
    return dict(GOOD, **over)


class TestPrompt(unittest.TestCase):
    def test_user_prompt_v03(self):
        p = rx.user_prompt(inp())
        self.assertIn("옮길 위치: 성분 목록 바로 아래", p)
        self.assertIn("34.0%", p); self.assertIn("2.1배", p); self.assertNotIn("0.34", p)
        self.assertIn("22초", p)
        self.assertIn(" / ".join(rx.SCREENS), p)
        self.assertIn("(화면 이름: 무엇을 보고 사나)", p)
        self.assertIn('"basis": [{"from"', rx.SYSTEM)
        self.assertIn("옮길 위치: 위치 그대로", rx.user_prompt(inp(**{"target.verb": "fix", "target.insert_after": None})))
        self.assertIn("옮길 위치: 맨 위", rx.user_prompt(inp(**{"target.insert_after": None})))

    def test_v01_numeric_input_still_renders(self):
        d = copy.deepcopy(INPUT)
        t = d["target"]; t.pop("view_rate_text"); t.pop("cart_lift_text"); t.pop("dwell_sec")
        t.update(view_rate=0.34, cart_lift=2.1, avg_dwell_ms=22300)
        p = rx.user_prompt(rx.PrescriptionInput.model_validate(d))
        self.assertIn("34.0%", p); self.assertIn("2.1배", p); self.assertIn("22초", p)


class TestCheck(unittest.TestCase):
    def test_good_passes(self):
        fails, needs = rx.check(GOOD, inp())
        self.assertEqual((fails, needs), ([], []))

    def test_shape(self):
        self.assertEqual(rx.check(dict(GOOD, basis="문자열"), inp())[0], ["shape"])

    def test_slot_mismatch_and_direction(self):
        f, _ = rx.check(bad(how="임상 결과를 사용자 리뷰 바로 아래로 옮기세요."), inp())
        self.assertTrue(any(x.startswith("slot_mismatch") for x in f))
        f, _ = rx.check(bad(how="임상 결과를 위로 올리세요. 성분 목록 근처가 좋습니다."), inp())   # 첫 문장에 칸 이름 없음
        self.assertTrue(any(x.startswith("slot_mismatch") for x in f))
        f, _ = rx.check(bad(how="임상 결과를 성분 목록 바로 아래로 옮기고 추가 설명은 빼세요."), inp())
        self.assertTrue(any(x.startswith("direction_mismatch") for x in f))
        # insert_after 가 null 이면 "맨 위"
        f, _ = rx.check(bad(how="임상 결과를 맨 위로 옮기세요."), inp(**{"target.insert_after": None}))
        self.assertFalse(any(x.startswith("slot_mismatch") for x in f))

    def test_fix_needs_specific_how_but_no_slot(self):
        f, _ = rx.check(bad(how="사용법을 아침과 저녁 2열 표로 바꾸세요."), inp(**{"target.verb": "fix", "target.insert_after": None}))
        self.assertFalse(any(x.startswith("slot_mismatch") for x in f))
        f, _ = rx.check(bad(how="사용법을 개선하세요."), inp(**{"target.verb": "fix", "target.insert_after": None}))
        self.assertIn("how_vague", f)

    def test_basis_from_six_screens_and_diversity(self):
        ok = bad(basis=[{"from": "상품마다 어디서 멈추나", "text": "성분 목록 구간에서 위로 다시 올려 읽은 기록이 388건입니다."},
                        {"from": "[누가 사나]", "text": "지성 고객이 가장 오래 보는 글이 임상 결과입니다."}])
        self.assertEqual(rx.check(ok, inp())[0], [])                      # 여섯 화면 + 대괄호 벗김
        f, _ = rx.check(bad(basis=[{"from": "상세페이지 집계", "text": "열람률 34.0%"}, dict(GOOD["basis"][1])]), inp())
        self.assertIn("basis_from", f)
        f, _ = rx.check(bad(basis=[dict(GOOD["basis"][0]), dict(GOOD["basis"][0])]), inp())
        self.assertIn("basis_diversity", f)

    def test_no_such_number_and_unsupported_comparison(self):
        f, _ = rx.check(bad(basis=[{"from": "무엇을 보고 사나", "text": "업계 평균 열람률은 52.0%입니다."}, dict(GOOD["basis"][1])]), inp())
        self.assertTrue(any(x.startswith("no_such_number") for x in f))
        f, _ = rx.check(bad(basis=[{"from": "무엇을 보고 사나", "text": "열람률 34.0%로 평균보다 높고 담기율은 2.1배입니다."},
                                  dict(GOOD["basis"][1])]), inp())
        self.assertTrue(any(x.startswith("unsupported_comparison") for x in f))
        # 신호 문장에 있는 표현은 허용 ("가장 오래" 는 판단 목록에 없음)
        self.assertEqual(rx.check(GOOD, inp())[0], [])

    def test_verify_range_and_em_dash(self):
        f, _ = rx.check(bad(verify="열람률을 34.0%에서 48%로 올리세요."), inp())
        self.assertIn("verify_range:no_arrow", f)
        self.assertTrue(any(x.startswith("verify_range") for x in rx.check(bad(verify="열람률 34.0% → 80.0%. 떨어지면 되돌리세요."), inp())[0]))
        self.assertTrue(any(x.startswith("verify_range") for x in rx.check(bad(verify="열람률 34.0% → 34.0%. 떨어지면 되돌리세요."), inp())[0]))
        self.assertIn("em_dash", rx.check(bad(how=GOOD["how"] + " — 꼭 하세요."), inp())[0])

    def test_claim_terms_banned_functional_needs_evidence(self):
        self.assertTrue(rx.claim_terms().loaded, "contracts/cosmetic-claim-banned-terms.json 이 있어야 한다")
        f, _ = rx.check(bad(how="임상 결과를 성분 목록 바로 아래로 옮기고 아토피 완화를 강조하세요."), inp())
        self.assertTrue(any(x.startswith("banned_term") for x in f))
        f, _ = rx.check(bad(how="임상 결과를 성분 목록 바로 아래로 옮기고 전환율을 올리세요."), inp())
        self.assertTrue(any(x.startswith("banned_term") for x in f))                       # 웹 분석 용어
        f, _ = rx.check(bad(how="임상 결과를 성분 목록 바로 아래로 옮기고 미백 결과를 앞에 두세요."), inp())
        self.assertTrue(any(x.startswith("functional_only") for x in f))
        f, _ = rx.check(bad(how="임상 결과를 성분 목록 바로 아래로 옮기고 미백 결과를 앞에 두세요."),
                        inp(**{"brand.functional_certified": True}))
        self.assertFalse(any(x.startswith("functional_only") for x in f))                 # 심사 기록 있으면 허용
        f, needs = rx.check(bad(how="임상 결과를 성분 목록 바로 아래로 옮기고 다크서클 완화 문구를 표 위에 두세요."), inp())
        self.assertEqual(f, [])                                                          # 거부 아님
        self.assertEqual(needs, ["다크서클 완화"])                                          # 꼬리표


class TestInputRules(unittest.TestCase):
    def test_rules(self):
        self.assertIn("verb_keep", rx.input_problems(inp(**{"target.verb": "keep"})))
        self.assertIn("signals_lt_2", rx.input_problems(inp(cross_screen_signals=INPUT["cross_screen_signals"][:1])))
        self.assertIn("insert_after_not_in_blocks", rx.input_problems(inp(**{"target.insert_after": "없는 칸"})))
        self.assertIn("signal_from_unknown", rx.input_problems(inp(cross_screen_signals=[
            dict(INPUT["cross_screen_signals"][0], **{"from": "대시보드"}), INPUT["cross_screen_signals"][1]])))
        self.assertEqual(rx.input_problems(inp()), [])


class TestPrescribe(unittest.TestCase):
    def setUp(self):
        self.store = rx.Store(os.path.join(tempfile.mkdtemp(), "p.jsonl"))

    def test_envelope_generate_and_cache(self):
        c = FakeClient(GOOD)
        r = rx.prescribe(inp(), c, self.store)
        for k in ("content_kind", "verb", "prescription", "rejected_by", "needs_evidence", "model",
                  "prompt_version", "input_hash", "generated_at"):
            self.assertIn(k, r, k)
        self.assertEqual(r["prescription"], GOOD)
        self.assertEqual(r["rejected_by"], [])
        self.assertTrue(r["input_hash"].startswith("sha256:"))
        self.assertEqual(c.last_kwargs["response_format"]["type"], "json_schema")
        self.assertEqual(c.last_kwargs["temperature"], 0.0)
        r2 = rx.prescribe(inp(), c, self.store)
        self.assertTrue(r2["cached"]); self.assertEqual(c.calls, 1)
        # 입력이 바뀌면 해시가 바뀌어 다시 생성
        c2 = FakeClient(GOOD)
        r3 = rx.prescribe(inp(**{"target.view_rate_text": "35.0%"}), c2, self.store)
        self.assertNotEqual(r3["input_hash"], r["input_hash"]); self.assertEqual(c2.calls, 1)

    def test_rejected_and_needs_evidence_in_envelope(self):
        r = rx.prescribe(inp(), FakeClient(bad(how="임상 결과를 사용자 리뷰 바로 아래로 옮기세요.")), self.store)
        self.assertIsNone(r["prescription"]); self.assertTrue(any(x.startswith("slot_mismatch") for x in r["rejected_by"]))
        r = rx.prescribe(inp(**{"target.sample_size": 948}), FakeClient(bad(how="임상 결과를 성분 목록 바로 아래로 옮기고 다크서클 완화 문구를 두세요.")), self.store)
        self.assertIsNotNone(r["prescription"]); self.assertEqual(r["needs_evidence"], ["다크서클 완화"])

    def test_keep_never_calls_llm(self):
        c = FakeClient(GOOD)
        r = rx.prescribe(inp(**{"target.verb": "keep"}), c, self.store)
        self.assertIsNone(r["prescription"]); self.assertEqual(r["rejected_by"], ["verb_keep"]); self.assertEqual(c.calls, 0)


class TestEndpoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        import recommend_server as rs
        cls.rs = rs
        cls.client = TestClient(rs.app)

    def test_503_without_key_and_keep(self):
        rs = self.rs
        rs._rx_client, rs._rx_client_tried = None, True
        r = self.client.post("/api/prescription", json=INPUT)
        self.assertEqual(r.status_code, 503)
        keep = copy.deepcopy(INPUT); keep["target"]["verb"] = "keep"
        r = self.client.post("/api/prescription", json=keep)
        self.assertEqual(r.status_code, 200); self.assertEqual(r.json()["rejected_by"], ["verb_keep"])

    def test_endpoint_with_fake_client(self):
        rs = self.rs
        rs._rx_client, rs._rx_client_tried = FakeClient(GOOD), True
        rs._rx_store = rx.Store(os.path.join(tempfile.mkdtemp(), "p.jsonl"))
        r = self.client.post("/api/prescription", json=INPUT)
        self.assertEqual(r.status_code, 200, r.text)
        b = r.json()
        self.assertEqual(b["prescription"]["how"], GOOD["how"]); self.assertIn("input_hash", b); self.assertEqual(b["needs_evidence"], [])
        self.assertTrue(self.client.post("/api/prescription", json=INPUT).json()["cached"])

    @unittest.skipUnless(os.environ.get("RUN_LIVE") == "1" and (os.environ.get("GMS_KEY") or os.environ.get("OPENAI_API_KEY")),
                         "RUN_LIVE=1 + GMS_KEY 일 때만 실제 호출")
    def test_live_once(self):
        store = rx.Store(os.path.join(tempfile.mkdtemp(), "p.jsonl"))
        r = rx.prescribe(inp(), rx.make_client(), store)
        print("\n[live]", json.dumps(r, ensure_ascii=False)[:700])
        self.assertEqual(r["rejected_by"], [], r)
        self.assertIn("성분 목록", r["prescription"]["how"])


if __name__ == "__main__":
    unittest.main()
