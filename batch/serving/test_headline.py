# -*- coding: utf-8 -*-
"""화면·섹션별 한 마디(Jira 365)를 고정한다. LLM 은 가짜 클라이언트 — 네트워크 없이 돈다.

여기서 막고 싶은 것
  * 입력에 없는 숫자 · 입력에 없는 비교·변화 판단
  * 지시문("~하세요") — 할 일은 처방 자리다. 두 자리가 다른 말을 하면 안 된다
  * 섹션 빠짐·없는 섹션 id · 섹션 줄이 그 섹션 이야기가 아님
  * 한 줄이 두 문장 · 90자 초과 · 줄표
  * 금지 표현(웹 용어·효능 단정)은 처방과 같은 목록으로 거부
  * 얇은 표본 자리는 결론을 내지 않는다
  * 키가 없거나 거부돼도 규칙 문장으로 화면이 비지 않는다 (origin)
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
_TMP = tempfile.mkdtemp(prefix="hl365_")
os.environ["HEADLINES_PATH"] = os.path.join(_TMP, "headlines.jsonl")
os.environ["PRESCRIPTIONS_PATH"] = os.path.join(_TMP, "prescriptions.jsonl")
os.environ["REGISTERED_PRODUCTS_PATH"] = shutil.copy(
    os.path.join(BD, "..", "ingest", "data", "serving", "registered_products.jsonl"), os.path.join(_TMP, "r.jsonl"))
os.environ["SESSION_EVENTS_PATH"] = os.path.join(_TMP, "s.jsonl")
os.environ.pop("SHOP_BACKEND_URL", None)

import headline as hl                      # noqa: E402

INPUT = {
    "brand": {"name": "SSAFY Beauty", "product_count": 8},
    "screen": {"id": "overview", "label_ko": "한눈에 보기", "period_text": "최근 14일"},
    "sections": [
        {"id": "traffic", "label_ko": "찾아온 사람",
         "facts": [{"label_ko": "상세를 본 방문", "value_text": "1,360건"},
                   {"label_ko": "상세를 본 사람", "value_text": "412명"}],
         "comparisons": ["상세를 본 방문이 지난 2주 1,120건에서 1,360건으로 늘었습니다."]},
        {"id": "cart", "label_ko": "장바구니",
         "facts": [{"label_ko": "담은 방문", "value_text": "141건"},
                   {"label_ko": "담기까지 걸린 시간", "value_text": "92초"}]},
        {"id": "repeat", "label_ko": "다시 산 고객",
         "facts": [{"label_ko": "재구매한 고객", "value_text": "6명"}], "thin": True},
    ],
}

OK_OUT = {
    "headline": "최근 14일 동안 상세를 본 방문이 1,360건이고 그중 141건이 장바구니까지 갔습니다.",
    "sections": [
        {"id": "traffic", "line": "상세를 본 방문이 1,360건으로 지난 2주보다 늘었습니다."},
        {"id": "cart", "line": "담은 방문은 141건이고 담기까지 걸린 시간은 92초입니다."},
        {"id": "repeat", "line": "다시 산 고객은 아직 기록이 적어 판단하기 이릅니다."},
    ],
}


def inp(**over):
    d = copy.deepcopy(INPUT)
    d.update(over)
    return hl.HeadlineInput(**d)


class FakeLLM:
    """OpenAI 클라이언트 모양만 흉내낸다. 네트워크 없음"""

    def __init__(self, payload):
        self.payload = payload
        self.calls = 0
        outer = self

        class _Msg:
            def __init__(self, content): self.content = content

        class _Choice:
            def __init__(self, content): self.message = _Msg(content)

        class _Resp:
            def __init__(self, content): self.choices = [_Choice(content)]

        class _Completions:
            def create(self, **kw):
                outer.calls += 1
                outer.last_kw = kw
                p = outer.payload
                return _Resp(p if isinstance(p, str) else json.dumps(p, ensure_ascii=False))

        class _Chat:
            completions = _Completions()

        self.chat = _Chat()


_seq = [0]


def run(out, **over):
    """저장본 때문에 LLM 을 안 부르는 일이 없게, 호출마다 새 저장 파일을 쓴다"""
    _seq[0] += 1
    client = FakeLLM(out)
    return hl.headline(inp(**over), client, hl.Store(os.path.join(_TMP, f"s{_seq[0]}.jsonl"))), client


class CheckTest(unittest.TestCase):
    def test_good_output_passes(self):
        fails, needs = hl.check(OK_OUT, inp())
        self.assertEqual([], fails, fails)
        self.assertEqual([], needs)

    def test_number_not_in_input_is_rejected(self):
        bad = copy.deepcopy(OK_OUT)
        bad["sections"][1]["line"] = "담은 방문은 141건으로 업계 평균 320건에 못 미칩니다."
        fails, _ = hl.check(bad, inp())
        self.assertTrue(any(f.startswith("no_such_number") for f in fails), fails)

    def test_comparison_without_input_sentence_is_rejected(self):
        bad = copy.deepcopy(OK_OUT)
        # cart 섹션에는 비교 문장이 없다. 그런데 "늘었" 다고 썼다
        bad["sections"][1]["line"] = "담은 방문이 141건으로 늘었습니다."
        fails, _ = hl.check(bad, inp())
        self.assertTrue(any(f.startswith("unsupported_comparison") for f in fails), fails)

    def test_comparison_present_in_input_is_allowed(self):
        # traffic 섹션에는 "늘었습니다" 가 입력 비교 문장에 있다
        fails, _ = hl.check(OK_OUT, inp())
        self.assertEqual([], fails)

    def test_derived_magnitude_claim_is_rejected(self):
        """입력은 "1,120건에서 1,360건으로 늘었습니다" 뿐이다. 나눠서 만든 "두 배" 는
        아라비아 숫자가 없어 숫자 대조로는 안 잡힌다 (09-19 실호출에서 실제로 나왔다)."""
        bad = copy.deepcopy(OK_OUT)
        bad["headline"] = "최근 14일 상세를 본 방문이 1,360건으로 두 배 이상 늘었습니다."
        fails, _ = hl.check(bad, inp())
        self.assertTrue(any(f.startswith("unsupported_comparison") and "두 배" in f for f in fails), fails)

    def test_magnitude_adverb_is_rejected(self):
        """입력은 "1,120건에서 1,360건으로 늘었습니다" 뿐이다. "크게" 는 입력이 안 한 크기 판단이다.
        09-20 실호출에서 "680건에서 4,163건으로 크게 늘었습니다" 로 나왔다."""
        bad = copy.deepcopy(OK_OUT)
        bad["headline"] = "최근 14일 상세를 본 방문이 1,360건으로 크게 늘었습니다."
        fails, _ = hl.check(bad, inp())
        self.assertTrue(any(f.startswith("unsupported_comparison") and "크게" in f for f in fails), fails)

    def test_all_matches_are_checked_not_just_the_first(self):
        """앞의 정당한 말이 뒤의 지어낸 말을 가리면 안 된다"""
        bad = copy.deepcopy(OK_OUT)
        bad["sections"][0]["line"] = "상세를 본 방문이 1,360건으로 늘었고 절반이 사람입니다."
        fails, _ = hl.check(bad, inp())
        self.assertTrue(any("절반" in f for f in fails), fails)

    def test_imperative_is_rejected(self):
        bad = copy.deepcopy(OK_OUT)
        bad["sections"][1]["line"] = "담은 방문이 141건이니 장바구니 버튼을 위로 올리세요."
        fails, _ = hl.check(bad, inp())
        self.assertTrue(any(f.startswith("imperative") for f in fails), fails)

    def test_missing_section_is_rejected(self):
        bad = copy.deepcopy(OK_OUT)
        bad["sections"] = bad["sections"][:2]
        fails, _ = hl.check(bad, inp())
        self.assertTrue(any(f.startswith("section_mismatch") for f in fails), fails)

    def test_unknown_section_id_is_rejected(self):
        bad = copy.deepcopy(OK_OUT)
        bad["sections"][2]["id"] = "nope"
        fails, _ = hl.check(bad, inp())
        self.assertTrue(any(f.startswith("section_mismatch") for f in fails), fails)

    def test_off_topic_section_line_is_rejected(self):
        bad = copy.deepcopy(OK_OUT)
        bad["sections"][1]["line"] = "찾아온 사람이 412명입니다."
        fails, _ = hl.check(bad, inp())
        self.assertTrue(any(f.startswith("off_topic") for f in fails), fails)

    def test_two_sentences_is_rejected(self):
        bad = copy.deepcopy(OK_OUT)
        bad["sections"][1]["line"] = "담은 방문은 141건입니다. 담기까지 92초 걸립니다."
        fails, _ = hl.check(bad, inp())
        self.assertTrue(any(f.startswith("two_sentences") for f in fails), fails)

    def test_too_long_is_rejected(self):
        bad = copy.deepcopy(OK_OUT)
        bad["sections"][1]["line"] = "담은 방문은 141건이고 " + "그리고 장바구니 이야기가 이어집니다 " * 5
        fails, _ = hl.check(bad, inp())
        self.assertTrue(any(f.startswith("too_long") for f in fails), fails)

    def test_web_jargon_is_rejected(self):
        bad = copy.deepcopy(OK_OUT)
        bad["sections"][1]["line"] = "장바구니 전환율이 141건입니다."
        fails, _ = hl.check(bad, inp())
        self.assertTrue(any(f.startswith("banned_term") for f in fails), fails)

    def test_em_dash_is_rejected(self):
        bad = copy.deepcopy(OK_OUT)
        bad["headline"] = "최근 14일 — 상세를 본 방문이 1,360건입니다."
        fails, _ = hl.check(bad, inp())
        self.assertIn("em_dash:__screen__", fails)   # 어느 줄인지 같이 적는다

    def test_shape_mismatch_is_rejected(self):
        fails, _ = hl.check({"headline": "한 줄입니다."}, inp())
        self.assertEqual(["shape"], fails)


class InputRuleTest(unittest.TestCase):
    def test_empty_section_is_flagged(self):
        d = copy.deepcopy(INPUT)
        d["sections"][1]["facts"] = []
        p = hl.input_problems(hl.HeadlineInput(**d))
        self.assertTrue(any(x.startswith("empty_section") for x in p), p)

    def test_duplicate_id_is_flagged(self):
        d = copy.deepcopy(INPUT)
        d["sections"][1]["id"] = "traffic"
        self.assertIn("duplicate_section_id", hl.input_problems(hl.HeadlineInput(**d)))

    def test_no_section_is_flagged(self):
        d = copy.deepcopy(INPUT)
        d["sections"] = []
        self.assertIn("no_section", hl.input_problems(hl.HeadlineInput(**d)))


class FlowTest(unittest.TestCase):
    def test_accepted_output_is_llm_origin(self):
        env, client = run(OK_OUT)
        self.assertEqual("llm", env["origin"])
        self.assertEqual([], env["rejected_by"])
        self.assertEqual(3, len(env["sections"]))
        self.assertEqual(1, client.calls)
        self.assertTrue(env["input_hash"].startswith("sha256:"))

    def test_only_the_offending_line_falls_back(self):
        """한 줄의 낱말 하나 때문에 멀쩡한 나머지 줄을 버리지 않는다"""
        bad = copy.deepcopy(OK_OUT)
        bad["sections"][1]["line"] = "담은 방문은 141건으로 업계 평균 320건에 못 미칩니다."
        env, _ = run(bad)
        self.assertEqual("mixed", env["origin"])
        self.assertTrue(any(f.startswith("no_such_number:cart") for f in env["rejected_by"]), env["rejected_by"])
        by = {s["id"]: s for s in env["sections"]}
        self.assertEqual("rule", by["cart"]["origin"])
        self.assertEqual("llm", by["traffic"]["origin"])   # 멀쩡한 줄은 그대로
        self.assertEqual(OK_OUT["sections"][0]["line"], by["traffic"]["line"])
        self.assertEqual(3, len(env["sections"]))
        self.assertTrue(all(s["line"] for s in env["sections"]))

    def test_broken_shape_falls_back_whole(self):
        """모양이 깨졌으면 줄을 고를 수 없으니 통째로 규칙 문장"""
        env, _ = run({"headline": "한 줄입니다."})
        self.assertEqual("rule", env["origin"])
        self.assertEqual(["shape"], env["rejected_by"])
        self.assertEqual(3, len(env["sections"]))

    def test_no_client_falls_back_without_calling_llm(self):
        env = hl.headline(inp(), None, hl.Store(os.path.join(_TMP, "nc.jsonl")))
        self.assertEqual("rule", env["origin"])
        self.assertEqual(["llm_unavailable"], env["rejected_by"])
        self.assertTrue(env["headline"])

    def test_same_input_is_served_from_store(self):
        store = hl.Store(os.path.join(_TMP, "cache.jsonl"))
        c1 = FakeLLM(OK_OUT)
        first = hl.headline(inp(), c1, store)
        second = hl.headline(inp(), c1, store)
        self.assertFalse(first["cached"])
        self.assertTrue(second["cached"])
        self.assertEqual(1, c1.calls)

    def test_schema_pins_section_ids(self):
        _, client = run(OK_OUT)
        sch = client.last_kw["response_format"]["json_schema"]["schema"]
        self.assertEqual(["traffic", "cart", "repeat"], sch["properties"]["sections"]["items"]["properties"]["id"]["enum"])
        self.assertEqual(3, sch["properties"]["sections"]["minItems"])

    def test_rule_lines_pick_josa_by_batchim(self):
        out = hl.rule_lines(inp())
        lines = {s["id"]: s["line"] for s in out["sections"]}
        self.assertTrue(lines["traffic"].startswith("찾아온 사람은 "), lines["traffic"])   # 람 = 받침 있음 → 은
        self.assertTrue(lines["cart"].startswith("장바구니는 "), lines["cart"])            # 니 = 받침 없음 → 는
        self.assertIn("1,360건입니다", out["headline"])

    def test_thin_section_rule_line_says_too_early(self):
        lines = {s["id"]: s["line"] for s in hl.rule_lines(inp())["sections"]}
        self.assertIn("판단하기 이릅니다", lines["repeat"])

    def test_prompt_carries_thin_marker_and_comparisons(self):
        p = hl.user_prompt(inp())
        self.assertIn("표본이 얇은 자리다", p)
        self.assertIn("1,120건에서 1,360건으로 늘었습니다", p)
        self.assertIn("[cart]", p)


@unittest.skipUnless(os.environ.get("RUN_LIVE") == "1" and (os.environ.get("GMS_KEY") or os.environ.get("GMS_API_KEY")),
                     "RUN_LIVE=1 과 GMS_KEY 가 있을 때만 (과금)")
class LiveTest(unittest.TestCase):
    def test_real_call_passes_checks(self):
        env = hl.headline(inp(), hl.rx.make_client(), hl.Store(os.path.join(_TMP, "live.jsonl")), force=True)
        self.assertEqual("llm", env["origin"], env.get("rejected_by"))
        print("\nheadline:", env["headline"])
        for s in env["sections"]:
            print(" ", s["id"], s["line"])


if __name__ == "__main__":
    unittest.main()
