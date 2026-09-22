# -*- coding: utf-8 -*-
"""브랜드 대시보드 할 일 처방 문장 생성 — `POST /api/prescription` 참조 구현 (Jira 220 → v0.3 정합 Jira 225).

규격 정본: `docs/dashboard/action-prescription-prompt.md` **v0.3** (프론트, MR !171) — 판정(up/fix/keep)과
**옮길 위치(insert_after)** 는 프론트 코드가 정하고, LLM 은 how·basis·verify 문장만 쓴다.
자동 거부 11개(§7)는 여기서 걸어 `prescription: null + rejected_by[]` 로 내리고, 실증 필요 표현은
거부하지 않고 `needs_evidence[]` 꼬리표로 내린다.

v0.3 에서 v0.1 과 달라진 것 (같은 입력 20회 실측으로 고친 것)
    * 비율·배수는 입력에서 이미 문자열이다 (`view_rate_text` "34.0%", `cart_lift_text` "2.1배"). 원시 수치는 안 쓴다
    * `up` 이면 프론트가 계산한 `insert_after` 칸 이름을 how 첫 문장이 그대로 써야 한다 (거부 6 slot_mismatch)
    * from 허용 화면 **여섯 개**. 대상 콘텐츠 집계에도 화면 이름을 붙인다
    * 출력 JSON 골격을 프롬프트에 박고 response_format=json_schema strict 로 강제 (v0.1 은 basis 가 20/20 문자열)
    * 형식·개수는 근거가 있을 때만 — 억지 "1개" 금지
    * 비교 판단("평균보다 높다")은 입력 신호 문장에 있을 때만 (거부 5 unsupported_comparison)
    * 금지 표현은 `contracts/cosmetic-claim-banned-terms.json` (banned 거부 · needs_evidence 꼬리표 · functional_only 는 심사 없으면 거부)
    * 응답 봉투에 `input_hash`("sha256:…") · `needs_evidence[]`. 해시가 같으면 재생성하지 않고 저장본

모델 gpt-4.1-mini · temperature 0 (nano 는 칸 이름을 못 써 5/5 거부). GMS 키 없으면 503.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import unicodedata
from typing import List, Optional

from pydantic import BaseModel, Field

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))

PROMPT_VERSION = "0.3"
MODEL = os.environ.get("PRESCRIPTION_MODEL", "gpt-4.1-mini")
GMS_BASE = os.environ.get("GMS_BASE", "https://gms.ssafy.io/gmsapi/api.openai.com/v1")
STORE_PATH = os.environ.get("PRESCRIPTIONS_PATH") or os.path.join(
    ROOT, "batch", "ingest", "data", "serving", "prescriptions.jsonl")
CLAIM_TERMS_PATH = os.path.join(ROOT, "contracts", "cosmetic-claim-banned-terms.json")

SCREENS = ("무엇을 보고 사나", "누가 사나", "고객이 찾는 성분", "상품마다 어디서 멈추나", "고객이 고쳐 달라는 것", "막히는 곳")
# 모델에게 주는 **판정**이지 출력 문구가 아니다. 명령형으로 두면 그대로 베껴 쓴다.
VERB_KO = {"up": "위로 올린다", "fix": "손본다"}
MIN_SIGNALS, MAX_SIGNALS, MIN_SAMPLE = 2, 6, 200
TARGET_RANGE = (1.2, 1.6)        # verify 목표값 / 현재값 — 검사는 (1.0, 1.6] 로 본다 (§7-10)

# §5 웹 분석 용어·효능 단정 (금지어 계약 파일이 없을 때의 최소 그물)
WEB_TERMS = ["전환율", "퍼널", "이탈률", "리텐션", "CTA", "UX", "인게이지먼트", "세션", "임프레션"]
EFFICACY_FALLBACK = ["주름 개선", "미백", "여드름 치료", "아토피", "재생", "흡수 촉진", "세포 활성화", "최고", "1위", "유일"]
JUDGEMENT = re.compile(r"(평균보다 (높|낮)|보다 (높|낮)(다|고|은|아|습니다)|가장 (높|낮)|충분(하|합니다)|좋(다|습니다|고)|나쁘(다|고|습니다))")
# §7-7 "아래로" 는 "성분 목록 **바로 아래로** 옮기세요"(위치 지정, 정상)와 구분해야 한다 — "바로 " 뒤는 제외
# 권유형으로 바꾸면 "빼세요" 대신 "빼 주시면", "빼시는 게" 가 나온다. 어간으로 잡는다.
DIRECTION_DOWN = re.compile(
    r"(빼|삭제하|지우|없애)(세요|시|\s?주|는\s?게|시는)|(?<!바로 )아래로")
SPECIFIC = re.compile(r"(바로 위|바로 아래|위로|맨 앞|맨 위|첫|번째|칸|표로|표 |목록|카드|줄|열|항목)")
NUM = re.compile(r"\d+(?:\.\d+)?")


# ── 입력 (규격 §3) ─────────────────────────────────────────────────────────
class Block(BaseModel):
    label_ko: str
    content_kind: Optional[str] = None
    view_rate_text: Optional[str] = None
    cart_lift_text: Optional[str] = None
    view_rate: Optional[float] = None          # v0.1 호환 — _text 가 없을 때만 쓴다
    cart_lift: Optional[float] = None


class Target(BaseModel):
    content_kind: str
    label_ko: str
    verb: str                                  # up · fix · keep
    dwell_sec: Optional[float] = None
    view_rate_text: Optional[str] = None
    cart_lift_text: Optional[str] = None
    sample_size: int
    position_in_page: int
    total_blocks: int
    insert_after: Optional[str] = None         # up 이면 프론트가 계산한 칸 이름. null 이면 "맨 위"
    avg_dwell_ms: Optional[float] = None       # v0.1 호환
    view_rate: Optional[float] = None
    cart_lift: Optional[float] = None


class PageContext(BaseModel):
    blocks_in_order: List[Block]
    quick_exit_rate_text: Optional[str] = None
    brand_cart_rate_text: Optional[str] = None
    quick_exit_rate: Optional[float] = None
    brand_cart_rate: Optional[float] = None


class Signal(BaseModel):
    from_: str = Field(alias="from")
    signal: str
    text: str
    sample_size: int
    value: Optional[float] = None

    model_config = {"populate_by_name": True}


class Brand(BaseModel):
    name: str
    product_count: Optional[int] = None
    functional_certified: bool = False         # 기능성화장품 심사 기록 (있으면 functional_only 낱말 허용)


class PrescriptionInput(BaseModel):
    brand: Brand
    target: Target
    page_context: PageContext
    cross_screen_signals: List[Signal]


def _pct(x): return None if x is None else f"{x * 100:.1f}%"
def _lift(x): return None if x is None else f"{x}배"


def texts(inp: PrescriptionInput) -> dict:
    """템플릿에 넣을 문자열들 — _text 가 있으면 그것, 없으면 v0.1 수치에서 만든다"""
    t = inp.target
    return {
        "view_rate": t.view_rate_text or _pct(t.view_rate) or "?",
        "cart_lift": t.cart_lift_text or _lift(t.cart_lift) or "?",
        "dwell_sec": (int(t.dwell_sec) if t.dwell_sec is not None and float(t.dwell_sec).is_integer() else t.dwell_sec)
                     if t.dwell_sec is not None else (round(t.avg_dwell_ms / 1000) if t.avg_dwell_ms else "?"),
        "blocks": [(b.label_ko, b.view_rate_text or _pct(b.view_rate) or "?", b.cart_lift_text or _lift(b.cart_lift) or "?")
                   for b in inp.page_context.blocks_in_order],
    }


# ── 프롬프트 (v0.3 §5·§6 그대로) ───────────────────────────────────────────
SYSTEM = """당신은 화장품 브랜드 대시보드의 개선 지시문을 쓴다. 읽는 사람은 마케팅 담당자가 아니라 직원 다섯 명 이하 브랜드의 사장님이다. 웹 분석 용어를 모르고, 이번 주에 직접 상세페이지를 고칠 사람이다.

쓰는 것
- 상세페이지에서 무엇을 어디로 옮기고 어떤 형식으로 바꿀지. 옮길 위치는 입력으로 받은 칸 이름을 그대로 쓴다.
- 그 지시를 뒷받침하는 근거. 입력으로 받은 신호 문장만 쓴다.
- 다음 주에 무엇이 얼마나 바뀌면 성공인지, 그리고 어떤 경우 되돌려야 하는지.

절대 쓰지 않는 것
- 웹 분석 용어: 전환율, 퍼널, 이탈률, 리텐션, CTA, UX, 인게이지먼트, 세션, 임프레션
- 효능 단정: 주름 개선, 미백, 여드름 치료, 아토피, 재생, 흡수 촉진, 세포 활성화, 최고, 1위, 유일
- 인과 단정: "이 글을 올리면 매출이 오릅니다". 관찰된 것은 같이 움직였다는 사실뿐이다.
- 입력에 없는 숫자. 업계 평균, 경쟁사 수치, 벤치마크를 만들어 넣지 않는다.
- 입력에 없는 비교 판단. 숫자는 옮겨 쓰되 "평균보다 높다", "낮다", "좋다", "나쁘다" 같은 판단은 입력 문장에 그 말이 있을 때만 쓴다. 34.0% 를 받아 "평균보다 높고" 라고 쓰면 안 된다.
- 제품 문구 자체를 대신 써 주는 일. 형식과 항목만 지시하고 홍보 문장은 쓰지 않는다.

문장 규칙
- 사장님에게 하는 지시는 "~해 보시면 좋겠습니다" 또는 "~하시는 게 좋겠습니다" 로 끝낸다.
  읽는 사람이 그 브랜드의 주인이다. 시키는 말투로 쓰지 않는다.
- 숫자는 입력 값 그대로. 소수점 자리도 바꾸지 않는다. 입력이 34.0% 면 34.0% 라고 쓴다.
- 한 문장에 한 가지 일. 접속사로 두 지시를 잇지 않는다.
- 줄표 기호를 쓰지 않는다. 괄호 안 설명을 넣지 않는다.
- 표기는 contracts/product-feature-vocab.json 과 contracts/product-form-labels-ko.json 의 한국어 라벨을 따른다.

출력은 아래 골격의 JSON 하나. 설명이나 인사말을 붙이지 않는다.
{"how": "지시 1~3문장", "basis": [{"from": "화면 이름", "text": "근거 한 문장"}], "verify": "지표 현재값 → 목표값. 되돌릴 조건 한 문장."}"""

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["how", "basis", "verify"],
          "properties": {"how": {"type": "string"},
                         "basis": {"type": "array", "minItems": 2, "maxItems": 3,
                                   "items": {"type": "object", "additionalProperties": False,
                                             "required": ["from", "text"],
                                             "properties": {"from": {"type": "string"}, "text": {"type": "string"}}}},
                         "verify": {"type": "string"}}}


def user_prompt(inp: PrescriptionInput) -> str:
    t = inp.target
    tx = texts(inp)
    blocks = "\n".join(f"  {i + 1}. {lab}  열람 {vr} · 담기율 배수 {cl}" for i, (lab, vr, cl) in enumerate(tx["blocks"]))
    sig = "\n".join(f"  - [{s.from_}] {s.text} (표본 {s.sample_size}건)" for s in inp.cross_screen_signals)
    if t.verb == "up":
        where = f"옮길 위치: {t.insert_after} 바로 아래" if t.insert_after else "옮길 위치: 맨 위"
    else:
        where = "옮길 위치: 위치 그대로"
    return f"""아래는 브랜드 한 곳의 상세페이지 콘텐츠 하나에 대한 집계와, 다른 화면에서 모은 신호다.
판정과 옮길 위치는 이미 정해져 있다. 그것을 바꾸지 말고, 실행하는 지시문만 써라.

판정: {VERB_KO[t.verb]}
대상 콘텐츠: {t.label_ko}
상세페이지 안 순서: {t.total_blocks}칸 중 {t.position_in_page}번째
{where}

이 콘텐츠의 집계 (화면 이름: 무엇을 보고 사나)
- 본 사람의 담기율: 브랜드 평균의 {tx['cart_lift']}
- 상세페이지를 연 사람 중 여기까지 본 비율: {tx['view_rate']}
- 평균 읽는 시간: {tx['dwell_sec']}초
- 표본: {t.sample_size}건

상세페이지 현재 순서
{blocks}

다른 화면에서 모은 신호
{sig}

basis 의 from 에 쓸 수 있는 화면 이름은 이 여섯 개뿐이다. 대괄호나 따옴표 없이 그대로 써라.
{' / '.join(SCREENS)}

지시문을 쓸 때 지켜라.
1. 판정이 위로 올리기면, how 의 첫 문장에 "옮길 위치" 로 받은 칸 이름을 그대로 써서 어디로 옮길지 못박아라. 그 칸 이름 말고 다른 위치를 쓰지 마라. 판정이 손보기면 위치를 건드리지 말고 형식이나 항목을 고치라고 써라.
2. 형식이나 개수를 지시하려면 위 신호 중 그것을 지지하는 근거가 있어야 한다. 근거가 없으면 형식·개수를 쓰지 말고 위치나 항목 지시만 남겨라. 숫자를 채우기 위해 없는 개수를 만들지 마라.
3. basis 는 위 신호에서 2~3개를 골라 사장님 말로 옮겨라. 서로 다른 화면에서 최소 두 개를 골라라. 신호 문장에 없는 숫자나 비교 판단을 더하지 마라.
4. verify 에는 위 집계값 하나를 골라 "현재값 → 목표값" 을 이 화살표 문자 그대로 써라. 목표는 현재값의 {TARGET_RANGE[0]}~{TARGET_RANGE[1]}배 안이다. 그리고 어떤 경우 되돌려야 하는지 한 문장 붙여라.

JSON 만 출력해라."""


# ── 입력 규칙 (§3) ─────────────────────────────────────────────────────────
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
    if inp.target.verb == "up" and inp.target.insert_after:
        labels = {b.label_ko for b in inp.page_context.blocks_in_order}
        if inp.target.insert_after not in labels:
            p.append("insert_after_not_in_blocks")
    return p


# ── 금지 표현 계약 (contracts/cosmetic-claim-banned-terms.json) ───────────────
def _norm(s: str) -> str:
    s = unicodedata.normalize("NFC", s or "")
    return "".join(ch for ch in s if ch.isalnum())


class ClaimTerms:
    """banned → 거부 · needs_evidence → 꼬리표 · functional_only → 심사 없으면 거부. allow 는 대조 전에 지운다"""

    def __init__(self, path=CLAIM_TERMS_PATH):
        self.loaded = os.path.exists(path)
        if self.loaded:
            d = json.load(open(path, encoding="utf-8"))
            self.banned = [w for grp in d.get("banned", {}).values() for w in grp]
            self.needs = list(d.get("needs_evidence", []))
            self.functional = list((d.get("functional_only") or {}).get("terms", []))
            self.allow = list((d.get("allow") or {}).get("terms", []))
        else:
            self.banned, self.needs, self.functional, self.allow = list(EFFICACY_FALLBACK), [], [], []
        self.banned = list(dict.fromkeys(self.banned + WEB_TERMS))

    def scan(self, text: str, functional_certified=False):
        raw = text or ""
        for a in self.allow:
            raw = raw.replace(a, " ")
        n = _norm(raw)
        hit_b = [w for w in self.banned if _norm(w) and _norm(w) in n]
        hit_f = [] if functional_certified else [w for w in self.functional if _norm(w) in n]
        hit_e = [w for w in self.needs if _norm(w) in n]
        return hit_b, hit_f, hit_e


_terms: Optional[ClaimTerms] = None


def claim_terms() -> ClaimTerms:
    global _terms
    if _terms is None:
        _terms = ClaimTerms()
    return _terms


# ── 자동 거부 (§7, 11개) ────────────────────────────────────────────────────
def input_numbers(inp: PrescriptionInput) -> set[float]:
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
            nums.update(float(n) for n in NUM.findall(x))
    walk(inp.model_dump(by_alias=True))
    for v in list(nums):
        if 0 < v < 1:
            nums.add(round(v * 100, 1)); nums.add(float(round(v * 100)))
    nums.update({1.0, 2.0, 3.0, 4.0, 5.0})       # 표 줄 수·항목 수 같은 작은 정수
    return nums


def check(out: dict, inp: PrescriptionInput) -> tuple[list[str], list[str]]:
    """§7 자동 거부. (rejected_by, needs_evidence) — rejected_by 가 비어 있으면 통과."""
    if not isinstance(out, dict) or set(out) != {"how", "basis", "verify"}:
        return ["shape"], []
    how, basis, verify = out["how"], out["basis"], out["verify"]
    if not isinstance(how, str) or not isinstance(verify, str) or not isinstance(basis, list) \
            or not all(isinstance(b, dict) and isinstance(b.get("from"), str) and isinstance(b.get("text"), str)
                       for b in basis):
        return ["shape"], []
    fails: list[str] = []
    joined = " ".join([how] + [b["text"] for b in basis] + [verify])

    # 1·2·3 금지 표현 · 기능성 · 실증 필요
    hit_b, hit_f, hit_e = claim_terms().scan(joined, inp.brand.functional_certified)
    if hit_b:
        fails.append("banned_term:" + ",".join(hit_b[:3]))
    if hit_f:
        fails.append("functional_only:" + ",".join(hit_f[:3]))
    needs_evidence = hit_e

    # 4 없는 숫자 (basis 기준 — how 의 표 줄 수 같은 작은 정수는 허용 집합에 있다)
    allowed = input_numbers(inp)
    bad = [n for n in (float(x) for x in NUM.findall(" ".join(b["text"] for b in basis) + " " + how)) if n not in allowed]
    if bad:
        fails.append("no_such_number:" + ",".join(f"{n:g}" for n in bad[:3]))

    # 5 없는 비교 판단
    input_text = " ".join(s.text for s in inp.cross_screen_signals)
    for b in basis:
        m = JUDGEMENT.search(b["text"])
        if m and m.group(0) not in input_text:
            fails.append("unsupported_comparison:" + m.group(0))
            break

    # 6 위치 일치 · 7 방향 일치 (up 만)
    if inp.target.verb == "up":
        labels = [b.label_ko for b in inp.page_context.blocks_in_order]
        ia = inp.target.insert_after
        first = re.split(r"(?<=[.。!?])\s+", how.strip())[0]
        if ia:
            others = [l for l in labels if l != ia and l != inp.target.label_ko and l in how]
            if ia not in first or others:
                fails.append("slot_mismatch:" + (ia if ia not in first else ",".join(others[:2])))
        else:
            if "맨 위" not in how:
                fails.append("slot_mismatch:맨 위")
        if DIRECTION_DOWN.search(how):
            fails.append("direction_mismatch:" + DIRECTION_DOWN.search(how).group(0))
    else:
        if not SPECIFIC.search(how):
            fails.append("how_vague")

    # 8·9 근거 출처 · 다양성
    froms = [b["from"].strip("[]\"' ") for b in basis]
    if not (2 <= len(froms) <= 3) or any(f not in SCREENS for f in froms):
        fails.append("basis_from")
    if len(set(froms)) < 2:
        fails.append("basis_diversity")

    # 10 목표값 범위
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:%|배|초|건)?\s*(?:→|->)\s*(\d+(?:\.\d+)?)", verify)
    if not m:
        fails.append("verify_range:no_arrow")
    else:
        cur, tgt = float(m.group(1)), float(m.group(2))
        if cur <= 0 or not (1.0 < tgt / cur <= TARGET_RANGE[1] + 1e-9):
            fails.append(f"verify_range:{cur:g}->{tgt:g}")

    # 11 줄표
    if "—" in joined or "–" in joined:
        fails.append("em_dash")
    return fails, needs_evidence


# ── 생성 ───────────────────────────────────────────────────────────────────
def make_client():
    key = os.environ.get("GMS_KEY") or os.environ.get("GMS_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not key:
        return None
    from openai import OpenAI
    return OpenAI(api_key=key, base_url=GMS_BASE)


def input_hash(inp: PrescriptionInput) -> str:
    """§8 — 입력 JSON 의 sha256. 같으면 재생성하지 않는다"""
    return "sha256:" + hashlib.sha256(json.dumps(inp.model_dump(by_alias=True, exclude_none=True), sort_keys=True,
                                                 ensure_ascii=False).encode("utf-8")).hexdigest()


class Store:
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


def generate(inp: PrescriptionInput, client, model=MODEL, temperature=0.0):
    """LLM 호출 1회 → (출력 dict 또는 None, rejected_by, needs_evidence, raw)"""
    r = client.chat.completions.create(
        model=model, temperature=temperature,
        response_format={"type": "json_schema",
                         "json_schema": {"name": "prescription", "strict": True, "schema": SCHEMA}},
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": user_prompt(inp)}])
    raw = r.choices[0].message.content or ""
    try:
        out = json.loads(raw)
    except Exception:
        return None, ["shape"], [], raw
    fails, needs = check(out, inp)
    return (out if not fails else None), fails, needs, raw


def envelope(inp: PrescriptionInput, model, **extra) -> dict:
    return dict({"content_kind": inp.target.content_kind, "verb": inp.target.verb, "brand": inp.brand.name,
                 "prescription": None, "rejected_by": [], "needs_evidence": [],
                 "model": model, "prompt_version": PROMPT_VERSION, "input_hash": input_hash(inp),
                 "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "cached": False}, **extra)


def store_key(inp: PrescriptionInput, model=MODEL) -> str:
    return f"{input_hash(inp)}-{PROMPT_VERSION}-{model}"


def prescribe(inp: PrescriptionInput, client, store: Store, force=False, model=MODEL) -> dict:
    """엔드포인트 본체. 입력 규칙 → 저장본 → 생성 → §7 → 저장. 봉투는 규격 §8 (PrescriptionEnvelope)."""
    problems = input_problems(inp)
    if problems:
        return envelope(inp, model, rejected_by=problems)
    key = store_key(inp, model)
    if not force:
        hit = store.get(key)
        if hit:
            return dict(hit, cached=True)
    out, fails, needs, raw = generate(inp, client, model=model)
    rec = envelope(inp, model, key=key, prescription=out, rejected_by=fails, needs_evidence=needs,
                   raw=raw if out is None else None)
    store.put(rec)
    return rec
