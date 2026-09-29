# -*- coding: utf-8 -*-
"""공개 LLM 엔드포인트(/api/prescription · /api/headline) 과금 방어.

nginx 가 두 자리를 인증 없이 열어 둔다. 여기서 막고 싶은 것
  * 요청의 ?model= 로 비싼 모델을 골라 부르는 것 — 모델은 서버 설정만 따른다
  * 아무나 ?force=true 로 저장본을 건너뛰어 매번 과금 호출을 만드는 것 — 운영 토큰이 맞을 때만
  * LLM 이 느리거나 죽었을 때 500 이 나는 것 — 처방은 503(프론트 규칙표), 한 마디는 규칙 문장

LLM 은 가짜 클라이언트다. 네트워크 없음.
"""
import copy
import os
import shutil
import sys
import tempfile
import unittest

BD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BD)
_TMP = tempfile.mkdtemp(prefix="llmguard_")
os.environ["HEADLINES_PATH"] = os.path.join(_TMP, "headlines.jsonl")
os.environ["PRESCRIPTIONS_PATH"] = os.path.join(_TMP, "prescriptions.jsonl")
os.environ["REGISTERED_PRODUCTS_PATH"] = shutil.copy(
    os.path.join(BD, "..", "ingest", "data", "serving", "registered_products.jsonl"), os.path.join(_TMP, "r.jsonl"))
os.environ["SESSION_EVENTS_PATH"] = os.path.join(_TMP, "s.jsonl")
os.environ.pop("SHOP_BACKEND_URL", None)
os.environ.pop("SERVING_ADMIN_TOKEN", None)

from fastapi.testclient import TestClient  # noqa: E402

import headline as hl                      # noqa: E402
import prescription as rx                  # noqa: E402
import recommend_server as rs              # noqa: E402
from test_headline import INPUT as HL_INPUT, OK_OUT as HL_OK, FakeLLM  # noqa: E402
import test_prescription as tp             # noqa: E402

client = TestClient(rs.app)


class _Boom:
    """chat.completions.create 가 늘 예외 — 시간 초과 흉내"""

    def __init__(self):
        self.calls = 0
        outer = self

        class _C:
            def create(self, **kw):
                outer.calls += 1
                raise TimeoutError("Request timed out.")

        class _Chat:
            completions = _C()

        self.chat = _Chat()


_seq = [0]


def _fresh(llm):
    """저장본·클라이언트를 새로 끼운다. 테스트끼리 저장본이 섞이지 않게 파일을 매번 바꾼다"""
    _seq[0] += 1
    rs._rx_store = rx.Store(os.path.join(_TMP, f"rx{_seq[0]}.jsonl"))
    rs._hl_store = rx.Store(os.path.join(_TMP, f"hl{_seq[0]}.jsonl"))
    rs._rx_client, rs._rx_client_tried = llm, True
    rs._rx_enabled = True


def _hl_body():
    return copy.deepcopy(HL_INPUT)


class HeadlineGuardTest(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("SERVING_ADMIN_TOKEN", None)

    def test_model_query_is_ignored(self):
        llm = FakeLLM(HL_OK)
        _fresh(llm)
        r = client.post("/api/headline", params={"model": "gpt-4o-expensive"}, json=_hl_body())
        self.assertEqual(200, r.status_code, r.text)
        self.assertEqual(hl.MODEL, llm.last_kw["model"])
        self.assertEqual(hl.MODEL, r.json()["model"])

    def test_force_without_token_serves_store(self):
        llm = FakeLLM(HL_OK)
        _fresh(llm)
        client.post("/api/headline", json=_hl_body())
        r = client.post("/api/headline", params={"force": "true"}, json=_hl_body())
        self.assertTrue(r.json()["cached"])
        self.assertEqual(1, llm.calls)

    def test_force_with_wrong_token_serves_store(self):
        os.environ["SERVING_ADMIN_TOKEN"] = "s3cret"
        llm = FakeLLM(HL_OK)
        _fresh(llm)
        client.post("/api/headline", json=_hl_body())
        r = client.post("/api/headline", params={"force": "true"}, headers={"X-Admin-Token": "nope"},
                        json=_hl_body())
        self.assertTrue(r.json()["cached"])
        self.assertEqual(1, llm.calls)

    def test_force_with_admin_token_regenerates(self):
        os.environ["SERVING_ADMIN_TOKEN"] = "s3cret"
        llm = FakeLLM(HL_OK)
        _fresh(llm)
        client.post("/api/headline", json=_hl_body())
        r = client.post("/api/headline", params={"force": "true"}, headers={"X-Admin-Token": "s3cret"},
                        json=_hl_body())
        self.assertFalse(r.json()["cached"])
        self.assertEqual(2, llm.calls)

    def test_empty_env_token_never_allows_force(self):
        os.environ["SERVING_ADMIN_TOKEN"] = ""
        self.assertFalse(rs._force_allowed(True, ""))
        self.assertFalse(rs._force_allowed(True, None))
        self.assertFalse(rs._force_allowed(False, "x"))


class PrescriptionGuardTest(unittest.TestCase):
    def test_model_query_is_ignored_and_force_needs_token(self):
        llm = tp.FakeClient(tp.GOOD, tp.GOOD)
        _fresh(llm)
        body = copy.deepcopy(tp.INPUT)
        r = client.post("/api/prescription", params={"model": "gpt-4o-expensive"}, json=body)
        self.assertEqual(200, r.status_code, r.text)
        self.assertEqual(rx.MODEL, llm.last_kwargs["model"])
        self.assertEqual(rx.MODEL, r.json()["model"])
        r2 = client.post("/api/prescription", params={"force": "true"}, json=body)
        self.assertTrue(r2.json()["cached"])
        self.assertEqual(1, llm.calls)


class TimeoutFallbackTest(unittest.TestCase):
    """LLM 이 시간 초과로 죽어도 500 이 아니다 — 처방은 503(프론트 규칙표), 한 마디는 규칙 문장"""

    def test_client_has_short_timeout(self):
        old = os.environ.get("GMS_KEY")
        os.environ["GMS_KEY"] = "test-not-a-key"
        try:
            c = rx.make_client()
        finally:
            if old is None:
                os.environ.pop("GMS_KEY", None)
            else:
                os.environ["GMS_KEY"] = old
        self.assertEqual(rx.LLM_TIMEOUT_S, c.timeout)
        self.assertLessEqual(c.timeout, 30)
        self.assertLessEqual(c.max_retries, 1)

    def test_headline_timeout_falls_back_to_rule(self):
        boom = _Boom()
        _fresh(boom)
        r = client.post("/api/headline", json=_hl_body())
        self.assertEqual(200, r.status_code, r.text)
        self.assertEqual("rule", r.json()["origin"])
        self.assertEqual(1, boom.calls)
        # 실패는 저장하지 않는다 — 다음 요청은 다시 LLM 을 시도한다
        client.post("/api/headline", json=_hl_body())
        self.assertEqual(2, boom.calls)

    def test_prescription_timeout_is_503(self):
        boom = _Boom()
        _fresh(boom)
        r = client.post("/api/prescription", json=copy.deepcopy(tp.INPUT))
        self.assertEqual(503, r.status_code, r.text)
        self.assertEqual("LLM_UNAVAILABLE", r.json()["detail"]["code"])


if __name__ == "__main__":
    unittest.main()
