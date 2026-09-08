# -*- coding: utf-8 -*-
"""금지어 대조 — `contracts/feedback-banned-terms.json`. LLM 없음.

입력을 막지 않는다. 걸린 단어를 `banned_terms` 에 적고 `hidden_by_default` 를
켠다. 사장님 화면은 그 행을 접어 두고, 눌러야 본문을 보여준다. 분류는 그대로
한다 — 욕이 섞여도 "펌프 막힘" 은 사장님이 봐야 할 내용이다.

정규화
    본문과 단어를 **같은 함수**로 정규화한 뒤 부분 일치를 본다. 공백·기호를
    지우므로 "시 발" · "시.발" 이 잡히고, 숫자는 남기므로 "18년" 도 잡힌다.
    allow 에 있는 낱말은 대조 전에 본문에서 지운다 — 목록의 짧은 단어가 평범한
    낱말 안에 들어 있을 때의 오탐 방지용이다.

실행 (단독 점검)
    python simulator/feedback/banned_terms.py "문장"
    python simulator/feedback/banned_terms.py --scan simulator/feedback/data/feedback_demo.jsonl
"""
import json
import os
import re
import sys
import unicodedata

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
CONTRACT = os.path.join(ROOT, "contracts", "feedback-banned-terms.json")

_KEEP = re.compile(r"[^가-힣ㄱ-ㅎㅏ-ㅣa-z0-9]+")


def normalize(s):
    # NFC 여야 한다. NFKC 는 호환 자모(ㅅ U+3145)를 조합 자모(U+1109)로 바꿔 버려서
    # 아래 정규식이 지운다 — 'ㅅㅂ' 같은 초성 항목 4개가 목록에서 통째로 사라졌다.
    s = unicodedata.normalize("NFC", s or "").lower()
    return _KEEP.sub("", s)


class BannedTerms:
    def __init__(self, path=CONTRACT):
        doc = json.load(open(path, encoding="utf-8"))
        self.version = doc["schema_version"]
        raw = list(doc.get("terms", [])) + list(doc.get("added", []))
        # disabled: 출처 목록에는 있지만 우리 맥락에서 오탐이 큰 것 ("18년" = 기간).
        # 출처 파일은 손대지 않고 여기서 끈다.
        off = {normalize(t) for t in doc.get("disabled", [])}
        # (원문, 정규화) — 긴 것부터 보면 "개새끼" 가 "개" 보다 먼저 잡혀 보고가 읽기 좋다
        seen, pairs = set(), []
        for t in raw:
            n = normalize(t)
            if n and n not in seen and n not in off:
                seen.add(n)
                pairs.append((t, n))
        self.terms = sorted(pairs, key=lambda p: -len(p[1]))
        self.allow = [normalize(a) for a in doc.get("allow", []) if normalize(a)]

    def find(self, text):
        n = normalize(text)
        for a in self.allow:
            n = n.replace(a, "")
        return [t for t, tn in self.terms if tn in n]


def main():
    bt = BannedTerms()
    args = sys.argv[1:]
    if args[:1] == ["--scan"]:
        rows = [json.loads(l) for l in open(args[1], encoding="utf-8")]
        hit = [(r.get("feedback_id", "?"), bt.find(r["body"]), r["body"]) for r in rows]
        hit = [h for h in hit if h[1]]
        print(f"{len(rows)}건 중 금지어 걸린 것 {len(hit)}건 · 목록 {len(bt.terms)}개 · {bt.version}")
        for fid, terms, body in hit:
            print(f"  {fid} {terms} | {body[:60]}")
        return
    for s in args:
        print(f"{bt.find(s)} <- {s}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
