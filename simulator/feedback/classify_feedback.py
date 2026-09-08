# -*- coding: utf-8 -*-
"""피드백을 축·카테고리로 분류한다 — **고정 목록에서 고르기**, 건당 호출 1회, **다중 라벨**.

계약: `contracts/feedback-category-vocab.json` (축 5개, 카테고리 20종, 기타) `0.2.0`.
분류기는 그 목록에서만 고른다. 목록에 없는 답은 버리고, 남는 게 없으면 `기타`.

축은 고객이 고른다 (0.2.0, 2026-09-08)
    화면이 왼쪽에 축 토글(용기·사용감·효능·…), 오른쪽에 그 축의 주관식 칸이다. 그래서
    **축은 입력**이고 분류기는 **그 축 안의 카테고리만** 고른다 (`classify_in_axis`).
    축 추론 오류가 구조적으로 사라진다. 다른 축 얘기가 섞여 보이면 `off_axis_hint` 에
    축 이름만 적고 재분류는 안 한다 — 고객이 고른 칸을 존중한다.

다중 라벨
    한 문장에 불만이 둘이면 둘 다 붙인다 (최대 3, 첫 번째가 primary). 사람 정답 50건
    채점에서 카테고리 불일치 15건 중 11건이 "용량 적은데 가격 비싸서" 였다 — 사용자는
    우리 축을 모르고 쓰므로 하나만 고르게 하면 불만이 버려진다. 집계는 **언급 수**다.
    "뚜껑도 이상하고 펌프도 이상하다" → 뚜껑 칸에도 펌프 칸에도 그 피드백이 뜬다.

왜 이름을 짓게 하지 않는가
    처음에는 모델이 라벨을 짓고, 그것을 기존 카테고리와 비교해 붙이거나 새로
    만들게 했다 (건당 호출 3회). 아홉 번 돌리면서 같은 문제가 계속 났다.

        파편    '기대효과 없음' 4 · '기대효과 미달' 4 · '기대효과 미흡' 1  <- 같은 문제
        과병합  '끈적임' 칸에 묽음 4건, '내용물 확인' 칸에 내구성 4건
        누출    비교 프롬프트의 **예시 문자열**이 그대로 카테고리로 등록됨
        방향    "뚜껑이 자꾸 열림" 과 "뚜껑이 안 열림" 이 한 칸

    비교 프롬프트에 한 줄을 넣으면 파편, 빼면 과병합으로 오갔다. 문구가 아니라
    구조의 문제다 — 이름을 매 건 새로 짓는 한 같은 이름이 나올 보장이 없다.

    목록을 못박으면 넷이 한 번에 사라진다. 이름을 안 지으니 파편·누출이 없고,
    '뚜껑 헐거움' 과 '뚜껑 뻑뻑함' 을 우리가 갈라 두니 방향 혼입도 없다.
    호출도 3회에서 1회로 줄어 크레딧이 1/3 이다.

잃는 것
    "새 카테고리 자동 생성". 대신 `기타` 에 쌓인 것을 가끔 훑어 목록에 항목을
    추가한다. 새 문제는 매 건마다가 아니라 어느 정도 쌓였을 때 보이는 것이
    맞고, 사장님 화면도 칸이 매일 바뀌면 오히려 불편하다.

⚠ 이 데이터로 분류 정확도를 재면 안 된다
    `intended_axis` 는 생성 때 지시한 축이다. 같은 모델이 축을 알고 쓴 문장을
    같은 모델이 분류한 값이라 **성능 근거가 아니라 바닥 점검용**이다.

실행
    set -a && . ./.env && set +a
    python simulator/feedback/classify_feedback.py --limit 30      # 먼저 30건만
    python simulator/feedback/classify_feedback.py --audit 4       # 칸 안 원문 확인
"""
import argparse
import json
import os
import sys
import time
from collections import Counter, defaultdict

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, BD)
from banned_terms import BannedTerms  # noqa: E402  금지어 대조 — LLM 없음

GMS_BASE = "https://gms.ssafy.io/gmsapi/api.openai.com/v1"
MODEL = "gpt-4.1-nano"      # 목록에서 고르는 일은 nano 로 충분하다
VOCAB = os.path.join(ROOT, "contracts", "feedback-category-vocab.json")
DATA = os.path.join(BD, "data")
NL = chr(10)


def load_vocab(path=VOCAB):
    v = json.load(open(path, encoding="utf-8"))
    axes = {}                       # label -> {"id", "desc", "cats": {label -> id}}
    for ax in v["axes"]:
        axes[ax["label"]] = {
            "id": ax["id"], "desc": ax["desc"],
            "cats": {c["label"]: c["id"] for c in ax["categories"]},
            "cat_desc": {c["label"]: c["desc"] for c in ax["categories"]},
        }
    return v, axes


PROMPT = """고객 피드백 1건에 **적혀 있는 불만을 전부** 아래 목록에서 골라 분류한다.
전부 불만·개선 요청이므로 극성은 판단하지 마라.

{menu}

규칙
- 문장에 **실제로 적힌** 불만만 고른다. 짐작해서 붙이지 마라. 최대 3개
- 가장 두드러진 것을 **첫 번째**에 둔다
- "용량이 적은데 가격이 비싸서" 는 둘이다 (용량 부족 + 가격 비쌈).
  "끈적이고 흡수도 느려서" 도 둘이다. 하나만 고르지 마라
- 목록의 이름을 **글자 그대로** 쓴다. 새 이름을 만들지 마라
- 어디에도 안 맞으면 {{"axis":"기타","category":"기타"}} 하나만
- 반대 방향은 다른 항목이다 — "뚜껑이 자꾸 열림" 은 뚜껑 헐거움·누수,
  "뚜껑이 안 열림" 은 뚜껑 뻑뻑함
- "피부가 당기고 건조하다" 는 [효능] 건조·당김이다

상품: {product}
피드백: {body}

JSON 만: {{"labels":[{{"axis":"..","category":".."}}, ...]}}"""


PROMPT_AXIS = """고객이 **[{axis}]** 칸에 쓴 피드백이다 (축은 고객이 골랐다 — 다시 판단하지 마라).
이 축의 카테고리 중 **문장에 적혀 있는 불만을 전부** 고른다. 전부 불만·개선 요청이므로 극성은 판단하지 마라.

[{axis}] {axis_desc}
{menu}
    - 기타: 위 어디에도 안 맞음 (이 축 얘기지만 목록에 없는 불만)

규칙
- 문장에 **실제로 적힌** 불만만 고른다. 짐작해서 붙이지 마라. 최대 3개
- 가장 두드러진 것을 **첫 번째**에 둔다
- "뚜껑도 이상하고 펌프도 이상하다" 는 둘이다. 하나만 고르지 마라
- 목록의 이름을 **글자 그대로** 쓴다. 새 이름을 만들지 마라
- 이 축의 카테고리 어디에도 안 맞으면 ["기타"] 하나만
- 반대 방향은 다른 항목이다 — "뚜껑이 자꾸 열림" 은 뚜껑 헐거움·누수, "뚜껑이 안 열림" 은 뚜껑 뻑뻑함
- 문장이 **다른 축** 얘기(예: 용기 칸에 향 얘기)로 보이면 off_axis 에 그 축 이름을 적는다.
  그래도 분류는 이 축 안에서만 한다. 다른 축 얘기가 아니면 off_axis 는 null

상품: {product}
피드백: {body}

JSON 만: {{"categories":["..", ".."], "off_axis": null}}"""


def build_menu(axes, other_label):
    lines = []
    for lab, ax in axes.items():
        lines.append(f"[{lab}] {ax['desc']}")
        for c, d in ax["cat_desc"].items():
            lines.append(f"    - {c}: {d}")
    lines.append(f"[{other_label}] 위 어디에도 안 맞음")
    return NL.join(lines)


class Classifier:
    def __init__(self, client, axes, other, model=MODEL):
        self.c, self.model = client, model
        self.axes, self.other = axes, other
        self.menu = build_menu(axes, other["label"])
        self.tok_in = self.tok_out = self.calls = self.retries = 0
        self.fallback = []              # 목록에 없는 답을 낸 것 -> 기타

    def _ask(self, prompt, tries=3):
        last = None
        for _ in range(tries):
            r = self.c.chat.completions.create(
                model=self.model, temperature=0,
                messages=[{"role": "user", "content": prompt}])
            self.tok_in += r.usage.prompt_tokens
            self.tok_out += r.usage.completion_tokens
            self.calls += 1
            o = r.choices[0].message.content.strip()
            i = o.find("{")
            if i >= 0:
                try:
                    return json.JSONDecoder().raw_decode(o, i)[0]
                except ValueError as e:
                    last = e
            else:
                last = ValueError(f"객체 없음: {o[:80]!r}")
            self.retries += 1
        raise ValueError(f"{tries}회 모두 JSON 파싱 실패: {last}")

    MAX_LABELS = 3

    def _other(self):
        return {"axis_id": self.other["id"], "axis": self.other["label"],
                "category_id": self.other["id"], "category": self.other["label"]}

    def _one(self, axis, cat):
        """목록에 있는 (축, 카테고리) 면 dict, 아니면 None. 지어낸 이름은 받지 않는다."""
        ax = self.axes.get(axis)
        if ax is not None and cat in ax["cats"]:
            return {"axis_id": ax["id"], "axis": axis,
                    "category_id": ax["cats"][cat], "category": cat}
        if axis == self.other["label"] and cat == self.other["label"]:
            return self._other()
        return None

    def classify_in_axis(self, body, axis, product=""):
        """(계약 0.2.0 정본 경로) **축은 고객이 골랐다.** 그 축 안의 카테고리만, 최대 3개.

        화면이 왼쪽에 축 토글, 오른쪽에 그 축의 주관식 칸이다. 그래서 축은 입력이고
        분류기는 카테고리만 고른다 — 축 추론 오류가 구조적으로 사라진다.
        다른 축 얘기로 보이면 off_axis_hint 에 그 축 이름만 적고 재분류는 안 한다.
        """
        ax = self.axes.get(axis)
        if ax is None:
            raise KeyError(f"모르는 축: {axis!r}")
        menu = NL.join(f"    - {c}: {d}" for c, d in ax["cat_desc"].items())
        try:
            g = self._ask(PROMPT_AXIS.format(axis=axis, axis_desc=ax["desc"], menu=menu,
                                             product=product or "(미상)", body=body))
        except ValueError as e:
            self.fallback.append((body[:40], f"파싱 실패 {e}"))
            return self._pack([self._other_in(axis)], off_axis=None)
        raw = g.get("categories")
        if not isinstance(raw, list):
            raw = [g.get("category")] if g.get("category") else []
        out, seen = [], set()
        for cat in raw[: self.MAX_LABELS * 2]:
            cat = (str(cat) if cat is not None else "").strip()
            if cat == self.other["label"]:
                continue
            if cat not in ax["cats"]:
                self.fallback.append((body[:40], f"[{axis}] {cat!r}"))
                continue
            if cat in seen:
                continue
            seen.add(cat)
            out.append({"axis_id": ax["id"], "axis": axis,
                        "category_id": ax["cats"][cat], "category": cat})
            if len(out) >= self.MAX_LABELS:
                break
        hint = g.get("off_axis")
        hint = hint.strip() if isinstance(hint, str) and hint.strip() in self.axes and hint.strip() != axis else None
        return self._pack(out or [self._other_in(axis)], off_axis=hint)

    def _other_in(self, axis):
        """그 축 안에서 못 고른 것 — 축은 그대로, 카테고리만 other"""
        ax = self.axes[axis]
        return {"axis_id": ax["id"], "axis": axis,
                "category_id": self.other["id"], "category": self.other["label"]}

    def classify(self, body, product=""):
        """(축을 모를 때의 보조 경로) 축 + 카테고리를 함께 추론. 최대 3개. 첫 번째가 primary.

        0.1.0 은 하나만 고르게 했다. 사람 정답 50건에서 카테고리 불일치 15건 중 11건이
        "용량 적은데 가격 비싸서" 처럼 한 문장에 두 불만이 함께 적힌 것이었다 —
        사용자는 우리 축을 모르고 쓴다. 하나만 고르게 하면 불만이 버려진다.
        """
        try:
            g = self._ask(PROMPT.format(menu=self.menu, product=product or "(미상)", body=body))
        except ValueError as e:
            self.fallback.append((body[:40], f"파싱 실패 {e}"))
            return self._pack([self._other()])
        raw = g.get("labels")
        if not isinstance(raw, list):                      # 옛 형식 {"axis","category"} 도 받는다
            raw = [g] if g.get("axis") else []
        out, seen = [], set()
        for item in raw[: self.MAX_LABELS * 2]:
            if not isinstance(item, dict):
                continue
            axis = (item.get("axis") or "").strip()
            cat = (item.get("category") or "").strip()
            lab = self._one(axis, cat)
            if lab is None:
                self.fallback.append((body[:40], f"{axis!r}/{cat!r}"))
                continue
            key = (lab["axis_id"], lab["category_id"])
            if key in seen:
                continue
            seen.add(key); out.append(lab)
            if len(out) >= self.MAX_LABELS:
                break
        # 기타는 단독으로만 — 다른 라벨이 있으면 기타를 뺀다
        real = [l for l in out if l["axis_id"] != self.other["id"]]
        return self._pack(real or [self._other()])

    def _pack(self, labels, off_axis=None):
        p = labels[0]
        return {"labels": labels, "primary": p, "off_axis_hint": off_axis,
                "axis_id": p["axis_id"], "axis": p["axis"],
                "category_id": p["category_id"], "category": p["category"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", default=os.path.join(DATA, "feedback_demo.jsonl"))
    ap.add_argument("--out", default=os.path.join(DATA, "feedback_classified.jsonl"))
    ap.add_argument("--limit", type=int, default=None, help="앞에서 N건만 (크레딧 아끼기)")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--axis-field", default="axis",
                    help="입력 행에서 고객이 고른 축을 읽는 필드. 시연 데이터는 intended_axis 가 그것이다. "
                         "없는 행은 축까지 추론하는 보조 경로로 간다")
    ap.add_argument("--audit", type=int, nargs="?", const=4, default=0, metavar="N",
                    help="N건 이상인 칸의 원문을 전부 찍는다 (오병합 확인)")
    a = ap.parse_args()

    vocab, axes = load_vocab()
    rows = [json.loads(l) for l in open(a.src, encoding="utf-8")]
    if a.limit:
        rows = rows[:a.limit]

    from openai import OpenAI
    key = (os.environ.get("GMS_KEY") or os.environ.get("GMS_API_KEY")
           or os.environ.get("OPENAI_API_KEY"))
    if not key:
        raise SystemExit("GMS 키를 못 찾았습니다. `set -a && . ./.env && set +a` 먼저.")

    clf = Classifier(OpenAI(api_key=key, base_url=GMS_BASE), axes, vocab["other"], a.model)
    n_cat = sum(len(ax["cats"]) for ax in axes.values())
    print(f"피드백 {len(rows)}건 · 고정 목록 {len(axes)}축 {n_cat}종 + 기타"
          f" · 어휘 {vocab['schema_version']} · {a.model} · 건당 호출 1회{NL}")

    banned = BannedTerms()
    out, t0 = [], time.time()
    for i, r in enumerate(rows, 1):
        # 축은 고객이 고른 것 (계약 §3 axis_id). 시연 데이터는 생성 때 지시한 축이 그것이다.
        axis_in = r.get(a.axis_field) or r.get("intended_axis")
        if axis_in in axes:
            g = clf.classify_in_axis(r["body"], axis_in, r.get("product_name", ""))
        else:
            g = clf.classify(r["body"], r.get("product_name", ""))
        # 금지어는 분류를 바꾸지 않는다. 걸리면 표시만 하고 화면에서 접는다.
        hits = banned.find(r["body"])
        out.append(dict(r, **g, banned_terms=hits, hidden_by_default=bool(hits),
                        classifier=a.model,
                        vocab_version=vocab["schema_version"],
                        classified_at=time.strftime("%Y-%m-%dT%H:%M:%S")))
        if i % 20 == 0:
            print(f"  {i:>4}/{len(rows)}건", flush=True)

    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"{NL}{len(out)}건 -> {a.out}")
    print(f"호출 {clf.calls}회(재시도 {clf.retries}) · 토큰 in {clf.tok_in:,}"
          f" / out {clf.tok_out:,} · {time.time() - t0:.0f}초")
    n_hidden = sum(1 for r in out if r["hidden_by_default"])
    print(f"금지어 걸린 것 {n_hidden}건 (hidden_by_default) · 목록 {len(banned.terms)}개")
    if clf.fallback:
        print(f"{NL}목록에 없는 답 {len(clf.fallback)}건 -> 기타")
        for b, why in clf.fallback[:10]:
            print(f"    {why} | {b}")

    # 집계는 **언급 수**다 — 라벨이 둘이면 두 칸에 각 1. 합이 건수를 넘을 수 있다 (계약 §4)
    byc = defaultdict(list)
    for r in out:
        for lab in r["labels"]:
            byc[(lab["axis"], lab["category"])].append(r["body"])
    n_lab = sum(len(r["labels"]) for r in out)
    multi = sum(1 for r in out if len(r["labels"]) > 1)
    off = sum(1 for r in out if r.get("off_axis_hint"))
    print(f"{NL}**칸 {len(byc)}개 사용** (목록 {n_cat}+1 중) · 언급 {n_lab}개 / 피드백 {len(out)}건"
          f" · 라벨 2개 이상 {multi}건 · 다른 축 얘기로 보임(off_axis_hint) {off}건")
    for lab in list(axes) + [vocab["other"]["label"]]:
        c = sorted([(k[1], len(v)) for k, v in byc.items() if k[0] == lab], key=lambda kv: -kv[1])
        if c:
            print(f"{NL}  [{lab}] " + " · ".join(f"{k} {n}건" for k, n in c))

    if a.audit:
        print(NL + "=" * 60 + NL + "감사 — 칸 안에 다른 문제가 섞였는지 눈으로 본다")
        for (ax, cat), bs in sorted(byc.items(), key=lambda kv: -len(kv[1])):
            if len(bs) < a.audit:
                continue
            print(f"{NL}### [{ax}] {cat} — {len(bs)}건")
            for b in bs:
                print("   ", b[:70])

    have = [r for r in out if r.get("intended_axis")]
    if have:
        ok = sum(1 for r in have if r["intended_axis"] == r["axis"])
        print(f"{NL}바닥 점검(생성 지시 축 복원): {ok}/{len(have)} = {ok / len(have) * 100:.0f}%")
        print("  ⚠ 같은 모델이 쓰고 같은 모델이 분류한 값이라 성능 근거가 아니다")


if __name__ == "__main__":
    main()
