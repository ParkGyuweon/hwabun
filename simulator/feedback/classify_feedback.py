# -*- coding: utf-8 -*-
"""피드백을 축·카테고리로 분류한다 — **고정 목록에서 고르기**, 건당 호출 1회.

계약: `contracts/feedback-category-vocab.json` (축 5개, 카테고리 20종, 기타).
분류기는 그 목록에서만 고른다. 목록에 없는 답은 `기타` 로 떨어진다.

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


PROMPT = """고객 피드백 1건을 아래 목록에서 **딱 하나** 골라 분류한다.
전부 불만·개선 요청이므로 극성은 판단하지 마라.

{menu}

규칙
- 증상이 여러 개면 **가장 두드러진 하나**만 고른다
- 목록의 이름을 **글자 그대로** 쓴다. 새 이름을 만들지 마라
- 어디에도 안 맞으면 axis, category 둘 다 "기타"
- 반대 방향은 다른 항목이다 — "뚜껑이 자꾸 열림" 은 뚜껑 헐거움·누수,
  "뚜껑이 안 열림" 은 뚜껑 뻑뻑함

상품: {product}
피드백: {body}

JSON 만: {{"axis":"..","category":".."}}"""


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

    def _other(self):
        return {"axis_id": self.other["id"], "axis": self.other["label"],
                "category_id": self.other["id"], "category": self.other["label"]}

    def classify(self, body, product=""):
        try:
            g = self._ask(PROMPT.format(menu=self.menu, product=product or "(미상)", body=body))
        except ValueError as e:
            self.fallback.append((body[:40], f"파싱 실패 {e}"))
            return self._other()
        axis = (g.get("axis") or "").strip()
        cat = (g.get("category") or "").strip()
        ax = self.axes.get(axis)
        # 목록에 없는 답은 **그대로 받지 않는다.** 이름을 짓게 하던 시절에 프롬프트
        # 예시 문자열이 카테고리로 등록된 적이 있다. 둘 중 하나라도 어긋나면 기타.
        if ax is None or cat not in ax["cats"]:
            if not (axis == self.other["label"] and cat == self.other["label"]):
                self.fallback.append((body[:40], f"{axis!r}/{cat!r}"))
            return self._other()
        return {"axis_id": ax["id"], "axis": axis,
                "category_id": ax["cats"][cat], "category": cat}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", default=os.path.join(DATA, "feedback_demo.jsonl"))
    ap.add_argument("--out", default=os.path.join(DATA, "feedback_classified.jsonl"))
    ap.add_argument("--limit", type=int, default=None, help="앞에서 N건만 (크레딧 아끼기)")
    ap.add_argument("--model", default=MODEL)
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

    out, t0 = [], time.time()
    for i, r in enumerate(rows, 1):
        g = clf.classify(r["body"], r.get("product_name", ""))
        out.append(dict(r, **g, classifier=a.model,
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
    if clf.fallback:
        print(f"{NL}목록에 없는 답 {len(clf.fallback)}건 -> 기타")
        for b, why in clf.fallback[:10]:
            print(f"    {why} | {b}")

    byc = defaultdict(list)
    for r in out:
        byc[(r["axis"], r["category"])].append(r["body"])
    print(f"{NL}**칸 {len(byc)}개 사용** (목록 {n_cat}+1 중)")
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
