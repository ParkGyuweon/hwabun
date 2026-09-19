# -*- coding: utf-8 -*-
"""
대시보드 화면·섹션별 "한 마디" (Jira 365).

처방(prescription.py)과 목적이 다르다.

    처방   "무엇을 어디로 옮기세요"  — 할 일 한 건. 판정이 난 콘텐츠에만 붙는다.
    한 마디 "지금 무슨 일이 일어나고 있나" — 읽는 보조. 숫자가 있는 자리마다 붙는다.

사장님은 표를 안 읽는다. 표 위에 한 줄이 있으면 그 줄만 읽고 넘어가도 화면을 이해할 수
있어야 한다. 그래서 여기서 나오는 문장은 **지시가 아니라 서술**이고, 끝이 "~합니다" 다.
"~하세요" 가 섞이면 거부한다 — 할 일은 처방 자리이고, 두 자리가 서로 다른 말을 하면
사장님이 어느 쪽을 따라야 할지 모른다.

입력은 프론트가 이미 화면에 그린 값 그대로다(`value_text`). 서버는 숫자를 계산하지 않는다.
계산을 여기서 다시 하면 화면과 문장이 어긋날 수 있고, 어긋나면 문장 쪽을 아무도 못 믿는다.

거부 규칙은 처방과 같은 집을 쓴다 (`prescription.ClaimTerms` · 숫자 대조 · 줄표 금지).
계약: contracts/headline-api-spec.md
"""
import hashlib
import json
import os
import re
import time
from typing import Optional

from pydantic import BaseModel, Field

import prescription as rx

PROMPT_VERSION = "0.1"
MODEL = os.environ.get("HEADLINE_MODEL", rx.MODEL)
STORE_PATH = os.environ.get("HEADLINES_PATH") or os.path.join(
    os.environ.get("SESSION_LOG_DIR") or os.path.join(rx.ROOT, "data", "serving"), "headlines.jsonl")

MAX_LINE_CHARS = 90          # 표 위 한 줄. 이보다 길면 줄바꿈이 생겨 "한 줄" 이 아니게 된다
MAX_SECTIONS = 8
MAX_FACTS = 8

# 지시문 어미. 한 마디는 서술이다 (§4-2)
IMPERATIVE = re.compile(r"(하세요|하십시오|해\s?보세요|바랍니다|권합니다|권장합니다|하시면\s?됩니다|올리세요|바꾸세요|넣으세요|빼세요)")
# 입력에 없으면 쓸 수 없는 비교·판단 (처방 §7-5 와 같은 규칙, 표현만 서술체로 넓힘)
#
# **배수는 한글 수사로 온다.** 09-19 실호출에서 입력이 "680건에서 1,436건으로 늘었습니다" 뿐인데
# 모델이 "두 배 이상 늘었습니다" 라고 썼다. 산술로는 맞지만 입력이 안 한 말이고, 숫자 대조는
# 아라비아 숫자만 보므로 "두" 를 못 잡는다. 배수·절반 같은 크기 주장을 여기에 같이 넣는다.
JUDGEMENT = re.compile(
    r"(평균보다\s?(높|낮)|보다\s?(높|낮)(다|고|은|아|습니다|습니다만)|가장\s?(높|낮)|충분(하|합니다)"
    r"|좋(다|습니다|고|은)|나쁘(다|고|습니다)|부족(하|합니다)|많(습니다|은 편)|적(습니다|은 편)"
    r"|올랐|떨어졌|늘었|줄었|개선|악화"
    r"|(한|두|세|네|다섯|여섯|일곱|여덟|아홉|열|몇)\s?배|곱절|절반|갑절"
    r"|배\s?(이상|가까이|넘게|가량))")


# ── 입력 (§3) ──────────────────────────────────────────────────────────────
class Fact(BaseModel):
    """화면에 이미 그려져 있는 값 하나. 숫자는 문자열로 받는다 — 표기까지 화면과 같아야 한다"""
    label_ko: str
    value_text: str


class Section(BaseModel):
    id: str
    label_ko: str
    facts: list[Fact] = Field(default_factory=list)
    # 프론트가 만든 완성형 비교 문장. 여기에 있는 말만 비교·판단으로 쓸 수 있다
    comparisons: list[str] = Field(default_factory=list)
    # 표본이 얇아 결론을 내면 안 되는 자리. true 면 문장이 "아직 판단하기 이릅니다" 쪽으로 간다
    thin: bool = False


class Screen(BaseModel):
    id: str
    label_ko: str
    period_text: str


class HeadlineInput(BaseModel):
    brand: rx.Brand
    screen: Screen
    sections: list[Section]


# ── 프롬프트 ───────────────────────────────────────────────────────────────
SYSTEM = """당신은 화장품 브랜드 대시보드의 화면 설명 한 줄을 쓴다. 읽는 사람은 직원 다섯 명 이하 브랜드의 사장님이다. 웹 분석 용어를 모르고, 표를 끝까지 읽을 시간이 없다.

하는 일
- 화면 전체에 한 줄, 섹션마다 한 줄. 그 줄만 읽어도 지금 무슨 일이 일어나고 있는지 알 수 있게 쓴다.
- 숫자를 그대로 옮겨 적는 것이 아니라, 그 숫자가 사장님에게 무슨 뜻인지 사람 말로 옮긴다.

절대 쓰지 않는 것
- 지시: "~하세요", "~하시면 됩니다", "권합니다". 할 일은 다른 자리에서 따로 알려 준다. 여기는 설명만 한다.
- 웹 분석 용어: 전환율, 퍼널, 이탈률, 리텐션, CTA, UX, 인게이지먼트, 세션, 임프레션
- 효능 단정: 주름 개선, 미백, 여드름 치료, 아토피, 재생, 흡수 촉진, 세포 활성화, 최고, 1위, 유일
- 입력에 없는 숫자. 업계 평균, 경쟁사 수치, 벤치마크를 만들어 넣지 않는다.
- 입력에 없는 비교·변화 판단. "늘었다", "줄었다", "높다", "낮다", "좋다" 는 입력의 비교 문장에 그 말이 있을 때만 쓴다. 값 하나만 받았으면 그 값이 큰지 작은지 말하지 않는다.
- 두 숫자를 나눠 만든 크기 주장. "두 배", "절반", "배 이상" 같은 말은 입력 문장에 그대로 있을 때만 쓴다. 680 과 1,436 을 받았다고 "두 배" 라고 쓰지 않는다.
- 인과 단정. 같이 움직였다는 사실만 관찰됐다.

문장 규칙
- 한 줄은 한 문장이다. 두 문장으로 나누지 않는다.
- 한 줄은 90자 안이다.
- 끝은 "~입니다" 또는 "~습니다".
- 숫자는 입력 값 그대로. 소수점 자리도 바꾸지 않는다.
- 줄표 기호를 쓰지 않는다. 괄호 안 설명을 넣지 않는다.
- 섹션 줄에는 그 섹션의 이름이나 그 섹션 값의 이름 중 하나가 들어가야 한다.
- 표본이 얇다고 표시된 섹션은 값을 결론처럼 쓰지 말고 아직 판단하기 이르다는 뜻이 드러나게 쓴다.

출력은 아래 골격의 JSON 하나. 설명이나 인사말을 붙이지 않는다.
{"headline": "화면 전체 한 줄", "sections": [{"id": "입력에서 받은 id", "line": "한 줄"}]}"""


def schema(ids: list[str]) -> dict:
    """섹션 id 를 열거로 못박는다. 없는 id 나 빠뜨린 id 는 모델이 만들 수 없게 한다"""
    return {"type": "object", "additionalProperties": False, "required": ["headline", "sections"],
            "properties": {
                "headline": {"type": "string"},
                "sections": {"type": "array", "minItems": len(ids), "maxItems": len(ids),
                             "items": {"type": "object", "additionalProperties": False,
                                       "required": ["id", "line"],
                                       "properties": {"id": {"type": "string", "enum": ids},
                                                      "line": {"type": "string"}}}}}}


def user_prompt(inp: HeadlineInput) -> str:
    parts = []
    for s in inp.sections:
        facts = "\n".join(f"    - {f.label_ko}: {f.value_text}" for f in s.facts) or "    - (값 없음)"
        cmp_ = "\n".join(f"    · {c}" for c in s.comparisons)
        thin = "\n    (표본이 얇은 자리다. 결론을 내지 마라.)" if s.thin else ""
        parts.append(f"  [{s.id}] {s.label_ko}\n{facts}"
                     + (f"\n    비교 문장 (이 말 안에서만 비교·변화를 쓸 수 있다)\n{cmp_}" if cmp_ else "")
                     + thin)
    return f"""브랜드 {inp.brand.name} 의 대시보드 화면 하나다. 기간은 {inp.screen.period_text} 다.

화면: {inp.screen.label_ko}

섹션과 화면에 이미 그려진 값
{chr(10).join(parts)}

화면 전체 한 줄에는 이 화면에서 사장님이 가장 먼저 알아야 할 것 하나만 담아라.
섹션 줄은 위에서 받은 id 를 그대로 쓰고, 섹션마다 하나씩 빠짐없이 써라.

JSON 만 출력해라."""


# ── 입력 규칙 ──────────────────────────────────────────────────────────────
def input_problems(inp: HeadlineInput) -> list[str]:
    p = []
    if not inp.sections:
        p.append("no_section")
    if len(inp.sections) > MAX_SECTIONS:
        p.append(f"too_many_sections:{len(inp.sections)}")
    ids = [s.id for s in inp.sections]
    if len(set(ids)) != len(ids):
        p.append("duplicate_section_id")
    for s in inp.sections:
        if len(s.facts) > MAX_FACTS:
            p.append(f"too_many_facts:{s.id}")
        if not s.facts and not s.comparisons:
            p.append(f"empty_section:{s.id}")
    return p


# ── 자동 거부 ──────────────────────────────────────────────────────────────
def input_numbers(inp: HeadlineInput) -> set[float]:
    """처방과 같은 방식. 입력 어디엔가 있는 숫자만 문장에 쓸 수 있다"""
    nums: set[float] = set()

    def walk(x):
        if isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
        elif isinstance(x, bool):
            return
        elif isinstance(x, (int, float)):
            nums.add(float(x))
        elif isinstance(x, str):
            nums.update(float(n.replace(",", "")) for n in rx.NUM.findall(x.replace(",", "")))
    walk(inp.model_dump())
    for v in list(nums):
        if 0 < v < 1:
            nums.add(round(v * 100, 1)); nums.add(float(round(v * 100)))
    nums.update({1.0, 2.0, 3.0, 4.0, 5.0})
    return nums


def _numbers_in(text: str) -> list[float]:
    return [float(n.replace(",", "")) for n in rx.NUM.findall((text or "").replace(",", ""))]


# 한 글자 낱말은 아무 문장에나 걸린다 (곳·본·수·것). 주제 판정에서 뺀다
_STOP = {"가장", "평균", "전체", "지난", "최근", "이번", "그중", "합계"}


def topic_words(s: Section) -> set[str]:
    """그 섹션이 무슨 이야기인지 알아보는 낱말들 — 섹션 이름 + 값 이름 + 값 자체"""
    src = [s.label_ko] + [f.label_ko for f in s.facts] + [f.value_text for f in s.facts]
    out = set()
    for t in src:
        for w in re.split(r"[\s,·/()]+", t or ""):
            w = w.strip()
            if len(w) >= 2 and w not in _STOP:
                out.add(w)
    return out


def check(out: dict, inp: HeadlineInput) -> tuple[list[str], list[str]]:
    """(rejected_by, needs_evidence). rejected_by 가 비어 있으면 통과."""
    if not isinstance(out, dict) or set(out) != {"headline", "sections"}:
        return ["shape"], []
    head, secs = out["headline"], out["sections"]
    if not isinstance(head, str) or not isinstance(secs, list) \
            or not all(isinstance(s, dict) and isinstance(s.get("id"), str) and isinstance(s.get("line"), str)
                       for s in secs):
        return ["shape"], []

    want = [s.id for s in inp.sections]
    got = [s["id"] for s in secs]
    if sorted(got) != sorted(want):
        return ["section_mismatch:" + ",".join(sorted(set(want) ^ set(got))[:3])], []

    fails: list[str] = []
    lines = {s["id"]: s["line"] for s in secs}
    joined = " ".join([head] + list(lines.values()))

    # 1·2·3 금지 표현 · 기능성 · 실증 필요 (처방과 같은 목록)
    hit_b, hit_f, hit_e = rx.claim_terms().scan(joined, inp.brand.functional_certified)
    if hit_b:
        fails.append("banned_term:" + ",".join(hit_b[:3]))
    if hit_f:
        fails.append("functional_only:" + ",".join(hit_f[:3]))
    needs_evidence = hit_e

    # 4 없는 숫자
    allowed = input_numbers(inp)
    bad = [n for n in _numbers_in(joined) if n not in allowed]
    if bad:
        fails.append("no_such_number:" + ",".join(f"{n:g}" for n in bad[:3]))

    # 5 없는 비교·변화 판단 — **그 섹션의** 비교 문장에 그 말이 있어야 한다.
    # 섹션을 안 가르고 전체에서 찾으면, 옆 섹션이 "늘었습니다" 를 가졌다는 이유로
    # 비교 문장이 없는 섹션까지 "늘었습니다" 를 쓸 수 있게 된다.
    all_said = " ".join(c for s in inp.sections for c in s.comparisons)
    scoped = [(s.id, lines[s.id], " ".join(s.comparisons)) for s in inp.sections]
    scoped.append(("__screen__", head, all_said))
    # 한 줄에 걸린 말이 여럿일 수 있다. 첫 것만 보면 "…에서 늘었고 두 배 이상입니다" 처럼
    # 앞의 정당한 말이 뒤의 지어낸 말을 가려 준다. 전부 본다.
    for sid, line, said in scoped:
        bad = [m.group(0) for m in JUDGEMENT.finditer(line) if m.group(0) not in said]
        if bad:
            fails.append(f"unsupported_comparison:{sid}:{bad[0]}")
            break

    # 6 지시문 금지 — 할 일은 처방 자리다
    m = IMPERATIVE.search(joined)
    if m:
        fails.append("imperative:" + m.group(0))

    # 7 한 줄 길이·문장 수 — 마침표는 끝에 하나뿐이어야 한 문장이다
    for sid, line in list(lines.items()) + [("__screen__", head)]:
        t = line.strip()
        if len(t) > MAX_LINE_CHARS:
            fails.append(f"too_long:{sid}:{len(t)}")
            break
        if len(re.split(r"(?<=[.!?])\s+", t)) > 1:
            fails.append(f"two_sentences:{sid}")
            break

    # 8 섹션 줄은 그 섹션 이야기를 해야 한다.
    # 이름을 통째로 넣으라고 하면 "상세페이지에서 오래 보는 곳은" 같은 표 제목을 그대로 베끼게 된다.
    # 사람 말로 옮기라고 해 놓고 베끼기를 강요하는 꼴이라, 낱말 하나만 겹치면 통과시킨다.
    for s in inp.sections:
        if not any(w in lines[s.id] for w in topic_words(s)):
            fails.append("off_topic:" + s.id)
            break

    # 9 줄표
    if "—" in joined or "–" in joined:
        fails.append("em_dash")
    return fails, needs_evidence


# ── 규칙 폴백 ──────────────────────────────────────────────────────────────
def _josa(word: str, with_batchim: str, without: str) -> str:
    """받침을 보고 조사를 고른다. 규칙 문장이 "찾아온 사람 는" 처럼 나가면 화면에서 바로 티가 난다.
    끝 글자가 한글이 아니면(숫자·영문) 읽는 소리를 모르므로 받침 있는 쪽으로 붙인다 — '141건은' 처럼."""
    ch = (word or "").strip()[-1:] or ""
    if "가" <= ch <= "힣":
        return with_batchim if (ord(ch) - 0xAC00) % 28 else without
    return with_batchim


def rule_lines(inp: HeadlineInput) -> dict:
    """LLM 이 없거나 거부됐을 때. 값을 이어 붙이기만 한다 — 새 사실을 만들지 않는다.

    요약이 아니라 나열이라 직관적이지는 않다. 그래도 화면이 비는 것보다는 낫고,
    여기서 지어낸 판단이 없다는 점이 중요하다."""
    secs = []
    for s in inp.sections:
        lab = s.label_ko
        if s.thin:
            line = f"{lab}{_josa(lab, '은', '는')} 아직 쌓인 기록이 적어 판단하기 이릅니다."
        elif s.facts:
            body = ", ".join(f"{f.label_ko} {f.value_text}" for f in s.facts[:3])
            line = f"{lab}{_josa(lab, '은', '는')} {body}입니다."
        elif s.comparisons:
            line = s.comparisons[0]
        else:
            line = f"{lab}{_josa(lab, '은', '는')} 아직 값이 없습니다."
        secs.append({"id": s.id, "line": line})
    first = next((s for s in inp.sections if s.facts and not s.thin), None)
    if first:
        f0 = first.facts[0]
        head = (f"{inp.screen.period_text} {inp.screen.label_ko} 화면에서 {first.label_ko}의 "
                f"{f0.label_ko}{_josa(f0.label_ko, '은', '는')} {f0.value_text}입니다.")
    else:
        head = f"{inp.screen.period_text} {inp.screen.label_ko} 화면에는 아직 쌓인 기록이 적습니다."
    return {"headline": head, "sections": secs}


# ── 생성 ───────────────────────────────────────────────────────────────────
def input_hash(inp: HeadlineInput) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(inp.model_dump(exclude_none=True), sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def store_key(inp: HeadlineInput, model=MODEL) -> str:
    return f"{input_hash(inp)}-h{PROMPT_VERSION}-{model}"


def envelope(inp: HeadlineInput, model, **extra) -> dict:
    return dict({"screen": inp.screen.id, "brand": inp.brand.name,
                 "headline": None, "sections": [], "origin": "none",
                 "rejected_by": [], "needs_evidence": [],
                 "model": model, "prompt_version": PROMPT_VERSION, "input_hash": input_hash(inp),
                 "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "cached": False}, **extra)


def generate(inp: HeadlineInput, client, model=MODEL, temperature=0.0):
    ids = [s.id for s in inp.sections]
    r = client.chat.completions.create(
        model=model, temperature=temperature,
        response_format={"type": "json_schema",
                         "json_schema": {"name": "headline", "strict": True, "schema": schema(ids)}},
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": user_prompt(inp)}])
    raw = r.choices[0].message.content or ""
    try:
        out = json.loads(raw)
    except Exception:
        return None, ["shape"], [], raw
    fails, needs = check(out, inp)
    return (out if not fails else None), fails, needs, raw


def headline(inp: HeadlineInput, client, store: Optional[rx.Store], force=False, model=MODEL,
             fallback=True) -> dict:
    """엔드포인트 본체. 입력 규칙 → 저장본 → 생성 → 거부 → 저장.

    거부되거나 클라이언트가 없으면 `fallback` 이 참일 때 규칙 문장을 준다 (`origin="rule"`).
    프론트는 origin 을 보고 출처 배지를 바꾼다."""
    problems = input_problems(inp)
    if problems:
        return envelope(inp, model, rejected_by=problems,
                        **(dict(rule_lines(inp), origin="rule") if fallback and not _fatal(problems) else {}))
    key = store_key(inp, model)
    if store is not None and not force:
        hit = store.get(key)
        if hit:
            return dict(hit, cached=True)
    if client is None:
        return envelope(inp, model, rejected_by=["llm_unavailable"],
                        **(dict(rule_lines(inp), origin="rule") if fallback else {}))
    out, fails, needs, raw = generate(inp, client, model=model)
    if out is not None:
        rec = envelope(inp, model, key=key, origin="llm", headline=out["headline"], sections=out["sections"],
                       rejected_by=[], needs_evidence=needs)
    else:
        rec = envelope(inp, model, key=key, rejected_by=fails, needs_evidence=needs, raw=raw,
                       **(dict(rule_lines(inp), origin="rule") if fallback else {}))
    if store is not None:
        store.put(rec)
    return rec


def _fatal(problems: list[str]) -> bool:
    """섹션이 아예 없으면 규칙 문장도 못 만든다"""
    return any(p == "no_section" for p in problems)


class Store(rx.Store):
    def __init__(self, path=STORE_PATH):
        super().__init__(path)
