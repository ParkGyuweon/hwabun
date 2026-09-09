# -*- coding: utf-8 -*-
"""브랜드 대시보드 할 일 처방 문장 생성 — `POST /api/prescription` 참조 구현 (Jira 220).

규격: `docs/dashboard/action-prescription-prompt.md` (프론트, v0.1) + AI 답변서의 v0.3 수정 다섯 줄.
역할 분담은 규격 그대로 — **판정(up/fix/keep)은 프론트 코드가, 문장(how·basis·verify)은 LLM 이.**
자동 거부(§6)는 여기서 걸어 `prescription: null + rejected_by[]` 로 내린다.

v0.3 에서 v0.1 과 달라진 것 (같은 입력 5회 실측으로 고친 것, 2026-09-09)
    1. 출력 JSON 골격을 프롬프트에 그대로 보여주고 response_format=json_schema(strict) 로 강제
       — v0.1 은 20/20 이 basis 를 문자열로 냈다
    2. up 이면 지금 칸보다 **앞** 칸으로만. 위치는 필수, 형식·개수는 근거 있을 때만 (억지 "1개" 금지)
    3. verify 는 "현재값 → 목표값" 화살표 문자 그대로, 목표는 1.2~1.6배
    4. 비율은 템플릿에서 34.0% 로 미리 적어 준다 (0.34 를 주면 그대로 쓴다)
    5. from 허용 목록 명시 + 대상 콘텐츠 집계에도 화면 이름을 붙인다
    +  비교 판단("평균보다 높다") 은 입력 문장에 있는 것만 — 검사기도 이 표현을 본다

모델: gpt-4.1-mini · temperature 0. nano 는 칸 이름 없이 "위쪽으로" 만 써서 5/5 거부됐다.
호출은 GMS(OpenAI 호환) — 키는 환경변수 GMS_KEY (또는 OPENAI_API_KEY). 없으면 503.
저장: 같은 입력(해시)은 다시 생성하지 않고 저장본을 준다 (일 1회 생성 권고). `force=true` 로 재생성.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from typing import List, Optional

from pydantic import BaseModel, Field

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))

PROMPT_VERSION = "0.3"
MODEL = os.environ.get("PRESCRIPTION_MODEL", "gpt-4.1-mini")
GMS_BASE = os.environ.get("GMS_BASE", "https://gms.ssafy.io/gmsapi/api.openai.com/v1")
STORE_PATH = os.environ.get("PRESCRIPTIONS_PATH") or os.path.join(
    ROOT, "batch", "ingest", "data", "serving", "prescriptions.jsonl")

SCREENS = ("무엇을 보고 사나", "누가 사나", "고객이 찾는 성분", "막히는 곳")
VERB_KO = {"up": "위로 올리세요", "fix": "손보세요"}
MIN_SIGNALS, MAX_SIGNALS, MIN_SAMPLE = 2, 6, 200
TARGET_RANGE = (1.2, 1.6)        # verify 목표값 / 현재값

# §4 금지 용어 (웹 분석·효능 단정). 효능 목록은 ai-insight-rules §4-3 확정본이 나오면 교체
FORBIDDEN = ["전환율", "퍼널", "이탈률", "리텐션", "CTA", "UX", "인게이지먼트", "세션", "임프레션",
             "주름 개선", "미백", "여드름 치료", "아토피", "재생", "흡수 촉진", "세포 활성화", "최고", "1위", "유일"]
# 비교 판단 표현 — 입력 문장에 없으면 모델이 만든 해석이다
JUDGEMENT = re.compile(r"(평균보다 (높|낮)|보다 (높|낮)(다|고|은|아)|가장 (높|낮)|매우|크게|상당히)")
SPECIFIC = re.compile(r"(바로 위|바로 아래|위로|아래로|맨 앞|맨 위|첫|번째|칸|표로|표 |목록|카드|줄|열)")


# ── 입력 (규격 §2) ─────────────────────────────────────────────────────────
class Block(BaseModel):
    content_kind: str
    label_ko: str
    view_rate: float
    cart_lift: float


class Target(BaseModel):
    content_kind: str
    label_ko: str
    verb: str                      # up · fix · keep
    avg_dwell_ms: float
    view_rate: float
    cart_lift: float
    sample_size: int
    position_in_page: int
    total_blocks: int


class PageContext(BaseModel):
    blocks_in_order: List[Block]
    quick_exit_rate: Optional[float] = None
    brand_cart_rate: Optional[float] = None


class Signal(BaseModel):
    from_: str = Field(alias="from")
    signal: str
    text: str
    value: Optional[float] = None
    sample_size: int

    model_config = {"populate_by_name": True}


class Brand(BaseModel):
    name: str
    product_count: Optional[int] = None


class PrescriptionInput(BaseModel):
    brand: Brand
    target: Target
    page_context: PageContext
    cross_screen_signals: List[Signal]


# ── 프롬프트 (v0.3) ────────────────────────────────────────────────────────
SYSTEM = """당신은 화장품 브랜드 대시보드의 개선 지시문을 쓴다. 읽는 사람은 마케팅 담당자가 아니라 직원 다섯 명 이하 브랜드의 사장님이다. 웹 분석 용어를 모르고, 이번 주에 직접 상세페이지를 고칠 사람이다.

쓰는 것
- 상세페이지에서 무엇을 어디로 옮기고 어떤 형식으로 바꿀지. 위치와 개수와 형식을 지정한다.
- 그 지시를 뒷받침하는 근거. 입력으로 받은 신호만 쓴다.
- 다음 주에 무엇이 얼마나 바뀌면 성공인지, 그리고 어떤 경우 되돌려야 하는지.

절대 쓰지 않는 것
- 웹 분석 용어: 전환율, 퍼널, 이탈률, 리텐션, CTA, UX, 인게이지먼트, 세션, 임프레션
- 효능 단정: 주름 개선, 미백, 여드름 치료, 아토피, 재생, 흡수 촉진, 세포 활성화, 최고, 1위, 유일
- 인과 단정: "이 글을 올리면 매출이 오릅니다". 관찰된 것은 같이 움직였다는 사실뿐이다.
- 입력에 없는 숫자. 업계 평균, 경쟁사 수치, 벤치마크를 만들어 넣지 않는다.
- 입력에 없는 비교 판단. "평균보다 높다", "낮다", "좋다" 는 입력 문장에 그 말이 있을 때만 쓴다. 숫자는 옮기고 판단은 붙이지 않는다.
- 제품 문구 자체를 대신 써 주는 일. 형식과 항목만 지시하고 홍보 문장은 쓰지 않는다.

문장 규칙
- 사장님에게 하는 지시는 "~하세요" 로 끝낸다.
- 숫자는 입력 값 그대로. 소수점 자리도 바꾸지 않는다.
- 한 문장에 한 가지 일. 접속사로 두 지시를 잇지 않는다.
- 줄표(—)를 쓰지 않는다. 괄호 안 설명을 넣지 않는다.
- 표기는 contracts/product-feature-vocab.json 과 contracts/product-form-labels-ko.json 의 한국어 라벨을 따른다.

출력은 아래 모양의 JSON 하나. 키 이름과 구조를 바꾸지 않는다. 설명이나 인사말을 붙이지 않는다.
{"how": "지시 1~3문장", "basis": [{"from": "화면 이름", "text": "근거 한 문장"}, {"from": "...", "text": "..."}], "verify": "지표 현재값 → 목표값. 되돌릴 조건 한 문장."}"""

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["how", "basis", "verify"],
          "properties": {"how": {"type": "string"},
                         "basis": {"type": "array", "minItems": 2, "maxItems": 3,
                                   "items": {"type": "object", "additionalProperties": False,
                                             "required": ["from", "text"],
                                             "properties": {"from": {"type": "string"}, "text": {"type": "string"}}}},
                         "verify": {"type": "string"}}}


def pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def user_prompt(inp: PrescriptionInput) -> str:
    t = inp.target
    blocks = "\n".join(f"  {i + 1}. {b.label_ko}  열람 {pct(b.view_rate)} · 담기율 배수 {b.cart_lift}"
                       for i, b in enumerate(inp.page_context.blocks_in_order))
    sig = "\n".join(f"  - [{s.from_}] {s.text} (표본 {s.sample_size}건)" for s in inp.cross_screen_signals)
    first = inp.page_context.blocks_in_order[0].label_ko if inp.page_context.blocks_in_order else "첫 칸"
    if t.verb == "up":
        direction = (f"옮길 위치는 위 순서 표에서 지금 {t.position_in_page}번째보다 **앞** 칸 이름으로만 "
                     f"지정해라 (예: '{first} 바로 아래').")
    else:
        direction = "위치는 그대로 두고 형식·항목을 고쳐라."
    return f"""아래는 브랜드 한 곳의 상세페이지 콘텐츠 하나에 대한 집계와, 다른 화면에서 모은 신호다.
판정은 이미 정해져 있다. 판정을 바꾸지 말고, 그 판정을 실행하는 지시문만 써라.

판정: {VERB_KO[t.verb]}
대상 콘텐츠: {t.label_ko}
상세페이지 안 순서: {t.total_blocks}칸 중 {t.position_in_page}번째

이 콘텐츠의 집계 (화면: 무엇을 보고 사나)
- 본 사람의 담기율: 브랜드 평균의 {t.cart_lift}배
- 상세페이지를 연 사람 중 여기까지 본 비율(열람률): {pct(t.view_rate)}
- 평균 읽는 시간: {round(t.avg_dwell_ms / 1000)}초
- 표본: {t.sample_size}건

상세페이지 현재 순서 (위에서 아래)
{blocks}

다른 화면에서 모은 신호
{sig}

지시문을 쓸 때 지켜라.
1. how: {direction} 형식(표·목록·카드)이나 항목 수는 근거가 있을 때만 적고, 억지로 숫자를 만들지 마라.
2. basis: 위 신호에서 2~3개를 골라 사장님 말로 옮겨라. 서로 다른 화면(from)에서 최소 두 개. from 은 다음 네 화면 이름 중 하나를 대괄호 없이 그대로 쓴다: {' / '.join(SCREENS)}. 대상 콘텍츠의 집계는 '무엇을 보고 사나' 화면이다. 없는 숫자를 만들지 마라. 숫자는 위에 적힌 표기 그대로 쓴다.
3. verify: 위 집계값 하나를 골라 "현재값 → 목표값" 을 이 화살표 문자 그대로 쓰고(목표는 현재의 {TARGET_RANGE[0]}~{TARGET_RANGE[1]}배), 어떤 경우 되돌려야 하는지 한 문장 붙여라.

JSON 만 출력해라.""".replace("콘텍츠", "콘텐츠")


# ── 입력 규칙 (§2) ─────────────────────────────────────────────────────────
def input_problems(inp: PrescriptionInput) -> list[str]:
    p = []
    if inp.target.verb not in VERB_KO:
        p.append("verb_keep" if inp.target.verb == "keep" else f"verb_unknown:{inp.target.verb}")
    sig = [s for s in inp.cross_screen_signals if s.sample_size >= MIN_SAMPLE]
    if len(sig) < MIN_SIGNALS:
        p.append(f"signals_lt_{MIN_SIGNALS}")
    if len(sig) > MAX_SIGNALS:
        p.append(f"signals_gt_{MAX_SIGNALS}")
    if any(s.from_ not in SCREENS for s in sig):
        p.append("signal_from_unknown")
    if not inp.page_context.blocks_in_order:
        p.append("no_blocks")
    return p


# ── 자동 거부 (§6) ─────────────────────────────────────────────────────────
_banned = None


def _banned_terms():
    global _banned
    if _banned is None:
        try:
            import sys
            sys.path.insert(0, os.path.join(ROOT, "simulator", "feedback"))
            from banned_terms import BannedTerms
            _banned = BannedTerms()
        except Exception:                      # 파일이 없어도 나머지 검사는 돈다
            _banned = False
    return _banned or None


def _numbers(text: str) -> list[float]:
    return [float(n) for n in re.findall(r"\d+(?:\.\d+)?", text)]


def input_numbers(inp: PrescriptionInput) -> set[float]:
    nums: set[float] = set()
    d = inp.model_dump(by_alias=True)

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
            nums.update(_numbers(x))
    walk(d)
    for v in list(nums):
        if 0 < v < 1:                            # 0.34 → 34.0 / 34
            nums.add(round(v * 100, 1)); nums.add(float(round(v * 100)))
        if v >= 1000:                            # 22300ms → 22초 / 22.3
            nums.add(float(round(v / 1000))); nums.add(round(v / 1000, 1))
    nums.update({1.0, 2.0, 3.0, 4.0, 5.0})       # 표 줄 수·항목 수 같은 작은 정수는 how 에서 허용
    return nums


def check(out: dict, inp: PrescriptionInput) -> list[str]:
    """§6 자동 거부. 걸린 검사 코드를 돌려준다 — 비어 있으면 통과."""
    fails: list[str] = []
    if not isinstance(out, dict) or set(out) != {"how", "basis", "verify"}:
        return ["shape"]
    how, basis, verify = out["how"], out["basis"], out["verify"]
    if not isinstance(how, str) or not isinstance(verify, str) or not isinstance(basis, list) \
            or not all(isinstance(b, dict) and isinstance(b.get("from"), str) and isinstance(b.get("text"), str)
                       for b in basis):
        return ["shape"]
    texts = [how] + [b["text"] for b in basis] + [verify]
    joined = " ".join(texts)

    if "—" in joined:
        fails.append("dash")
    hit = [w for w in FORBIDDEN if w in joined]
    if hit:
        fails.append("forbidden_terms:" + ",".join(hit))
    bt = _banned_terms()
    if bt is not None and bt.find(joined):
        fails.append("banned_terms")
    if not SPECIFIC.search(how):
        fails.append("how_vague")
    # up 인데 지금보다 뒤 칸을 지정 / 빼라고 함
    if inp.target.verb == "up":
        blocks = [b.label_ko for b in inp.page_context.blocks_in_order]
        cur = inp.target.position_in_page
        later = [b for i, b in enumerate(blocks, 1) if i > cur and b != inp.target.label_ko and b in how]
        earlier = [b for i, b in enumerate(blocks, 1) if i < cur and b in how]
        if later and not earlier:
            fails.append("how_moves_down")
        if re.search(r"(빼세요|삭제하세요|지우세요|없애세요)", how):
            fails.append("how_contradicts_verb")
    froms = [b["from"].strip("[] ") for b in basis]
    if not (2 <= len(froms) <= 3):
        fails.append("basis_n")
    if any(f not in SCREENS for f in froms):
        fails.append("basis_from")
    if len(set(froms)) < 2:
        fails.append("basis_same_from")
    allowed = input_numbers(inp)
    bad = [n for n in _numbers(" ".join(b["text"] for b in basis)) if n not in allowed]
    if bad:
        fails.append("basis_numbers:" + ",".join(str(n) for n in bad[:3]))
    input_text = " ".join(s.text for s in inp.cross_screen_signals)
    for b in basis:
        m = JUDGEMENT.search(b["text"])
        if m and m.group(0) not in input_text:
            fails.append("basis_judgement:" + m.group(0))
            break
    m = re.search(r"(\d+(?:\.\d+)?)\s*%?\s*(?:→|->)\s*(\d+(?:\.\d+)?)", verify)
    if not m:
        fails.append("verify_no_arrow")
    else:
        cur_v, tgt = float(m.group(1)), float(m.group(2))
        if cur_v <= 0 or not (1.0 <= tgt / cur_v <= TARGET_RANGE[1]):
            fails.append(f"verify_range:{cur_v}->{tgt}")
    return fails


# ── 생성 ───────────────────────────────────────────────────────────────────
def make_client():
    key = os.environ.get("GMS_KEY") or os.environ.get("GMS_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not key:
        return None
    from openai import OpenAI
    return OpenAI(api_key=key, base_url=GMS_BASE)


def input_hash(inp: PrescriptionInput) -> str:
    return hashlib.sha256(json.dumps(inp.model_dump(by_alias=True), sort_keys=True,
                                     ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


class Store:
    """생성 결과 영속 — 같은 입력은 다시 생성하지 않는다 (일 1회 생성 권고)"""

    def __init__(self, path=STORE_PATH):
        self.path = path
        self._by_key: dict[str, dict] = {}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        r = json.loads(line)
                        self._by_key[r["key"]] = r

    def get(self, key):
        return self._by_key.get(key)

    def put(self, rec):
        self._by_key[rec["key"]] = rec
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def generate(inp: PrescriptionInput, client, model=MODEL, temperature=0.0) -> tuple[Optional[dict], list[str], str]:
    """LLM 호출 1회 → (출력 dict 또는 None, rejected_by, raw)"""
    r = client.chat.completions.create(
        model=model, temperature=temperature,
        response_format={"type": "json_schema",
                         "json_schema": {"name": "prescription", "strict": True, "schema": SCHEMA}},
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": user_prompt(inp)}])
    raw = r.choices[0].message.content or ""
    try:
        out = json.loads(raw)
    except Exception:
        return None, ["shape"], raw
    fails = check(out, inp)
    return (out if not fails else None), fails, raw


def prescribe(inp: PrescriptionInput, client, store: Store, force=False, model=MODEL) -> dict:
    """엔드포인트 본체. 입력 규칙 → 저장본 → 생성 → §6 → 저장."""
    problems = input_problems(inp)
    base = {"content_kind": inp.target.content_kind, "verb": inp.target.verb,
            "brand": inp.brand.name, "prompt_version": PROMPT_VERSION, "model": model}
    if problems:
        return dict(base, prescription=None, rejected_by=problems, cached=False,
                    generated_at=time.strftime("%Y-%m-%dT%H:%M:%S"))
    key = f"{input_hash(inp)}-{PROMPT_VERSION}-{model}"
    if not force:
        hit = store.get(key)
        if hit:
            return dict(hit, cached=True)
    out, fails, raw = generate(inp, client, model=model)
    rec = dict(base, key=key, prescription=out, rejected_by=fails,
               generated_at=time.strftime("%Y-%m-%dT%H:%M:%S"), raw=raw if out is None else None)
    store.put(rec)
    return dict(rec, cached=False)
