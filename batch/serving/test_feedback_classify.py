# -*- coding: utf-8 -*-
"""피드백 분류 서빙(Jira 353)을 고정한다. LLM 은 가짜 클라이언트 — 네트워크 없이 돈다.

여기서 막고 싶은 것

  * **축은 고객 입력이다** (계약 0.2.0 ``axis_is_input``). 모르는 axis_id 는 LLM 에 안 넘기고 FAILED
  * 목록 밖 카테고리를 모델이 지어내면 버린다. 하나도 못 고르면 그 축 안에서 ``other``
  * ``other`` 는 단독으로만
  * 금지어는 사전 대조라 LLM 과 무관하게 돌고 ``hidden_by_default`` 를 정한다
  * 한 건이 죽어도 배치의 나머지는 산다 (예외를 밖으로 안 던진다)
  * ``off_axis_hint`` 는 라벨이 아니라 **axis_id** 로 나간다 — 백엔드가 그걸 저장한다
  * **DB 를 건드리지 않는다.** 쓰기는 shop_backend 몫 (2026-09-18 합의)
"""
import json
import os
import sys
import unittest

BD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BD)

import feedback_classify as fc  # noqa: E402


class FakeMessage:
    def __init__(self, content):
        self.content = content


class FakeChoice:
    def __init__(self, content):
        self.message = FakeMessage(content)


class FakeUsage:
    prompt_tokens = 10
    completion_tokens = 5


class FakeResponse:
    def __init__(self, content):
        self.choices = [FakeChoice(content)]
        self.usage = FakeUsage()


class FakeCompletions:
    def __init__(self, replies):
        # replies: 문자열 또는 예외. 호출마다 하나씩 꺼낸다
        self.replies = list(replies)
        self.calls = 0

    def create(self, **kw):
        self.calls += 1
        r = self.replies.pop(0) if self.replies else "{}"
        if isinstance(r, Exception):
            raise r
        return FakeResponse(r)


class FakeClient:
    def __init__(self, *replies):
        self.chat = type("C", (), {"completions": FakeCompletions(replies)})()


def one(client, axis_id="texture", body="끈적여요", feedback_id="f1", product_id=None):
    items = [{"feedback_id": feedback_id, "product_id": product_id,
              "axis_id": axis_id, "body": body}]
    return fc.classify_items(items, client)[0]


class AxisIsInput(unittest.TestCase):
    def test_계약의_축_다섯이_전부_매핑된다(self):
        for axis_id in ("efficacy", "texture", "scent", "packaging", "value"):
            self.assertIsNotNone(fc.axis_label(axis_id), axis_id)

    def test_모르는_축은_LLM_을_부르지_않고_실패로_돌려준다(self):
        c = FakeClient('{"categories": ["끈적임"]}')
        got = one(c, axis_id="delivery")          # 배송은 계약이 뺀 축이다
        self.assertEqual(got["status"], "FAILED")
        self.assertIn("unknown axis_id", got["error"])
        self.assertEqual(c.chat.completions.calls, 0)

    def test_본문이_비면_LLM_을_부르지_않는다(self):
        c = FakeClient('{"categories": ["끈적임"]}')
        got = one(c, body="   ")
        self.assertEqual(got["status"], "FAILED")
        self.assertEqual(c.chat.completions.calls, 0)


class LabelsFollowContract(unittest.TestCase):
    def test_그_축_안의_카테고리를_여러_개_고른다(self):
        c = FakeClient('{"categories": ["끈적임", "흡수 느림"]}')
        got = one(c)
        self.assertEqual(got["status"], "COMPLETED")
        self.assertEqual([l["category_id"] for l in got["labels"]],
                         ["texture_sticky", "texture_slow"])
        self.assertTrue(all(l["axis_id"] == "texture" for l in got["labels"]))
        self.assertEqual(got["primary_category_id"], "texture_sticky")

    def test_목록에_없는_카테고리는_버린다(self):
        c = FakeClient('{"categories": ["끈적임", "향이 강함", "지어낸것"]}')
        got = one(c)                              # 향은 다른 축, 마지막은 없는 값
        self.assertEqual([l["category_id"] for l in got["labels"]], ["texture_sticky"])

    def test_하나도_못_고르면_그_축_안에서_기타다(self):
        c = FakeClient('{"categories": []}')
        got = one(c)
        self.assertEqual(got["status"], "COMPLETED")
        self.assertEqual(len(got["labels"]), 1)
        self.assertEqual(got["labels"][0]["axis_id"], "texture")   # 축은 고객이 고른 그대로
        self.assertEqual(got["primary_category_id"], "other")

    def test_기타는_단독으로만_붙는다(self):
        c = FakeClient('{"categories": ["끈적임", "기타"]}')
        got = one(c)
        ids = [l["category_id"] for l in got["labels"]]
        self.assertIn("texture_sticky", ids)
        self.assertNotIn("other", ids)

    def test_off_axis_는_라벨이_아니라_axis_id_로_나간다(self):
        c = FakeClient('{"categories": ["끈적임"], "off_axis": "향"}')
        got = one(c)
        self.assertEqual(got["off_axis_hint"], "scent")

    def test_같은_카테고리를_두_번_주면_한_번만_센다(self):
        c = FakeClient('{"categories": ["끈적임", "끈적임"]}')
        self.assertEqual(len(one(c)["labels"]), 1)


class BannedTermsAreDictionaryOnly(unittest.TestCase):
    def test_금지어가_있으면_기본_숨김이다(self):
        hits, hidden = fc.check_banned("이 씨발 제품 끈적여요")
        self.assertTrue(hits)
        self.assertTrue(hidden)

    def test_평범한_문장은_숨기지_않는다(self):
        hits, hidden = fc.check_banned("끈적이고 흡수가 느려요")
        self.assertEqual(hits, [])
        self.assertFalse(hidden)

    def test_분류가_실패해도_금지어_판정은_나온다(self):
        c = FakeClient(RuntimeError("gms down"))
        got = one(c, body="이 씨발 제품 끈적여요")
        self.assertEqual(got["status"], "FAILED")
        self.assertTrue(got["hidden_by_default"])


class OneFailureDoesNotKillTheBatch(unittest.TestCase):
    def test_예외가_나도_그_건만_실패한다(self):
        c = FakeClient(RuntimeError("gms down"), '{"categories": ["끈적임"]}')
        items = [{"feedback_id": "f1", "axis_id": "texture", "body": "끈적여요"},
                 {"feedback_id": "f2", "axis_id": "texture", "body": "흡수 느려요"}]
        got = fc.classify_items(items, c)
        self.assertEqual([g["status"] for g in got], ["FAILED", "COMPLETED"])
        self.assertEqual(got[0]["feedback_id"], "f1")

    def test_JSON_이_아니어도_기타로_떨어지고_죽지_않는다(self):
        c = FakeClient("응답이 JSON 이 아님", "응답이 JSON 이 아님", "응답이 JSON 이 아님")
        got = one(c)
        self.assertEqual(got["status"], "COMPLETED")      # Classifier 가 기타로 받아 준다
        self.assertEqual(got["primary_category_id"], "other")


class ResponseShape(unittest.TestCase):
    def test_백엔드가_저장할_칸이_모두_있다(self):
        c = FakeClient('{"categories": ["끈적임"]}')
        got = one(c)
        for k in ("feedback_id", "status", "labels", "primary_category_id",
                  "off_axis_hint", "banned_terms", "hidden_by_default",
                  "classifier", "vocab_version"):
            self.assertIn(k, got, k)
        self.assertEqual(got["vocab_version"], "0.2.0-draft")

    def test_라벨은_axis_id_와_category_id_만_준다(self):
        c = FakeClient('{"categories": ["끈적임"]}')
        got = one(c)
        self.assertEqual(set(got["labels"][0]), {"axis_id", "category_id"})

    def test_json_직렬화가_된다(self):
        c = FakeClient('{"categories": ["끈적임"]}')
        json.dumps(one(c), ensure_ascii=False)


class Route(unittest.TestCase):
    """엔드포인트 계약. 엔진을 띄우므로 이 클래스만 무겁다."""

    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        import recommend_server as rs
        cls.rs, cls.client = rs, TestClient(rs.app)

    def tearDown(self):
        self.rs._fc_enabled = fc.ENABLED_DEFAULT
        self.rs._fc_client, self.rs._fc_client_tried = None, False

    def test_빈_목록은_LLM_없이_빈_결과다(self):
        r = self.client.post("/api/feedback/classify", json={"items": []})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"results": []})

    def test_스위치가_꺼져_있으면_503(self):
        self.rs._fc_enabled = False
        r = self.client.post("/api/feedback/classify", json={
            "items": [{"feedback_id": "f1", "axis_id": "texture", "body": "끈적여요"}]})
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["detail"]["code"], "LLM_UNAVAILABLE")

    def test_키가_없으면_503(self):
        self.rs._fc_enabled = True
        self.rs._fc_client, self.rs._fc_client_tried = None, True   # make_client 가 None 을 준 상태
        r = self.client.post("/api/feedback/classify", json={
            "items": [{"feedback_id": "f1", "axis_id": "texture", "body": "끈적여요"}]})
        self.assertEqual(r.status_code, 503)

    def test_분류가_되면_백엔드가_저장할_모양으로_돌려준다(self):
        self.rs._fc_enabled = True
        self.rs._fc_client = FakeClient('{"categories": ["끈적임"]}')
        self.rs._fc_client_tried = True
        r = self.client.post("/api/feedback/classify", json={
            "items": [{"feedback_id": "f1", "product_id": "P421996",
                       "axis_id": "texture", "body": "끈적여요"}]})
        self.assertEqual(r.status_code, 200)
        got = r.json()["results"][0]
        self.assertEqual(got["status"], "COMPLETED")
        self.assertEqual(got["labels"], [{"axis_id": "texture", "category_id": "texture_sticky"}])

    def test_스위치_라우트로_켜고_끌_수_있다(self):
        self.assertFalse(self.client.post("/api/feedback/classify/llm",
                                          json={"enabled": False}).json()["enabled"])
        self.assertTrue(self.client.get("/api/feedback/classify/llm").json()["enabled"] is False)
        self.assertTrue(self.client.post("/api/feedback/classify/llm",
                                         json={"enabled": True}).json()["enabled"])

    def test_health_에_분류_상태가_실린다(self):
        h = self.client.get("/health").json()
        self.assertIn("feedback_classify", h)
        self.assertIn("enabled", h["feedback_classify"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
