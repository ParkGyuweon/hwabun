"""
번역된 리뷰(상품별 JSON) 를 contracts/localization/reviews-ko.json 에 합치고 검수한다 (2026-09-10).

입력
    --en    reviews_en_100_all.json           영문 100건×200 (build_reviews_100.py 산출)
    --ko    번역 결과 폴더. {product_id}.json, 각 항목 {review_id, review_title, review_text}
    기존    contracts/localization/reviews-ko.json  (있는 review_id 는 그대로 재사용)
출력
    contracts/localization/reviews-ko.json     20,000건으로 교체 (--write 를 줘야 쓴다)
    <ko 폴더>/merge_qa_report.md               검수 결과, 걸린 review_id 목록

검수 규칙 (걸리면 해당 건은 넣지 않고 리포트에 남긴다)
    A 누락      영문에 있는데 번역이 없다
    B 여분      영문에 없는 review_id (무시, 개수만 보고)
    C 빈 본문   영문 본문이 있는데 번역 본문이 비었다
    D 제목 불일치  영문 제목 null 인데 번역 제목이 있거나, 반대
    E 미번역    한글 비율 < 0.30 (영문 그대로 남은 것). 짧은 감탄사·브랜드명은 예외 처리 못 하므로 리포트로 사람이 본다
    F 길이 이상  KO 글자수 / EN 글자수 가 0.15 미만 또는 1.5 초과 (요약·부풀림 의심)
    G 잔여 영문 문장  30자 넘는 영문 구간 중 소문자 시작 단어 4개 이상 (대문자 연속인 브랜드·제품명은 통과)
"""
import argparse
import glob
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
KO_PATH = os.path.join(ROOT, "contracts", "localization", "reviews-ko.json")
HANGUL = re.compile(r"[가-힣]")
LATIN_RUN = re.compile(r"[A-Za-z][A-Za-z ,.'!?-]{29,}")

ap = argparse.ArgumentParser()
ap.add_argument("--en", required=True)
ap.add_argument("--ko", required=True)
ap.add_argument("--write", action="store_true", help="검수 통과분을 reviews-ko.json 에 실제로 쓴다")
ap.add_argument("--allow", default="", help="사람이 원문과 대조해 통과시키는 review_id (쉼표). E·F 휴리스틱 걸림을 넘긴다")
A = ap.parse_args()

en = {x["review_id"]: x for x in json.load(open(A.en, encoding="utf-8"))}
old = json.load(open(KO_PATH, encoding="utf-8"))
meta = old.pop("_meta")
new = {}
for f in glob.glob(os.path.join(A.ko, "P*.json")):      # 상품 파일만 — 검수 리포트 JSON 은 건너뛴다
    for x in json.load(open(f, encoding="utf-8")):
        new[x["review_id"]] = x

def hangul_ratio(s):
    letters = [c for c in s if c.isalpha()]
    return (sum(1 for c in letters if HANGUL.match(c)) / len(letters)) if letters else 1.0

flags = {k: [] for k in "ABCDEFG"}
ALLOW = {x.strip() for x in A.allow.split(",") if x.strip()}   # 사람이 본 것
out = {}
for rid, e in en.items():
    src = old.get(rid) or new.get(rid)
    if src is None:
        flags["A"].append(rid)
        continue
    title, text = src.get("review_title"), (src.get("review_text") or "").strip()
    if rid in ALLOW:                       # 사람이 원문과 대조해 통과시킨 것 — 휴리스틱을 건너뛴다
        out[rid] = {"product_id": e["product_id"], "review_title": (None if title is None else str(title)), "review_text": text}
        continue
    bad = False
    if (e["review_text"] or "").strip() and not text:
        flags["C"].append(rid); bad = True
    if (e["review_title"] is None) != (title is None or str(title).strip() == ""):
        flags["D"].append(rid); bad = True
    if text and hangul_ratio(text) < 0.30:
        flags["E"].append(rid); bad = True
    en_len = len(e["review_text"] or "")
    if text and en_len >= 40 and not (0.15 <= len(text) / en_len <= 1.5):
        flags["F"].append(rid); bad = True
    # 브랜드·제품명은 대문자로 시작하는 단어가 이어진다. 소문자 시작 단어가 4개 이상인 구간만 문장으로 본다
    if text and any(sum(1 for w in m.group(0).split() if w[:1].islower()) >= 4 for m in LATIN_RUN.finditer(text)):
        flags["G"].append(rid); bad = True
    if not bad:
        out[rid] = {"product_id": e["product_id"], "review_title": (None if title is None else str(title)), "review_text": text}
extra = sorted(set(new) - set(en))
flags["B"] = extra

lines = [f"# reviews-ko 병합 검수 ({len(en):,}건 대상)", "",
         f"- 기존 재사용 {sum(1 for r in out if r in old):,} · 신규 번역 채택 {sum(1 for r in out if r not in old):,} · **통과 {len(out):,} / {len(en):,}**",
         f"- A 누락 {len(flags['A']):,} · B 여분(무시) {len(flags['B']):,} · C 빈 본문 {len(flags['C'])} · D 제목 불일치 {len(flags['D'])} "
         f"· E 미번역 {len(flags['E'])} · F 길이 이상 {len(flags['F'])} · G 잔여 영문 {len(flags['G'])}", ""]
for k, name in zip("ACDEFG", ["누락", "빈 본문", "제목 불일치", "미번역(한글<30%)", "길이 이상", "잔여 영문 30자+"]):
    if flags[k]:
        lines += [f"## {k} {name} ({len(flags[k])})", ""] + [f"- {r}" for r in flags[k][:300]] + (["- …"] if len(flags[k]) > 300 else []) + [""]
rep = os.path.join(A.ko, "merge_qa_report.md")
open(rep, "w", encoding="utf-8").write("\n".join(lines) + "\n")
print("\n".join(lines[:4]))
print("리포트:", rep)

if A.write:
    meta = dict(meta, reviews_source="build_reviews_100.py 상품당 100건 층화 추출 (2026-09-10)",
                reviews_translation="기존 2,000건: GMS gpt-4.1-mini 초안+검수(09-09) · 추가 18,025건: 사용자 GPT 번역(09-10), merge_reviews_ko.py 검수")
    json.dump({"_meta": meta, **out}, open(KO_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"→ {KO_PATH} {len(out):,}건 기록")
else:
    print("(--write 없음: 파일은 건드리지 않았다)")
