"""쇼핑몰 상품 문구에 화장품 표시·광고 금지 표현이 남아 있지 않은지 본다.

기준: contracts/cosmetic-claim-banned-terms.json 의 banned (product_copy.skip_groups 제외)
      + product_copy.extra_banned. allow·product_copy.allow 는 대조 전에 지운다.
정규화는 batch/serving/prescription.py 와 같다 (NFC · 한글/영문/숫자만 남김 · 부분 일치).

대상: 고객에게 보이는 한국어 상품명·설명
    contracts/localization/products-ko.json   (세포라 200개 번역본)
    frontend/src/mocks/products.ssafy-beauty.json   (SSAFY Beauty 8개, 한국어 원본)
전성분(ingredients)과 고객 리뷰는 대상이 아니다 — 리뷰는 고객이 쓴 글이라 이 목록의 적용 범위 밖이다.

실행 (저장소 루트에서):
    python -m unittest contracts.tests.test_product_copy_claims -v
    python contracts/tests/test_product_copy_claims.py      # 걸린 문장을 모두 찍는다
"""
from __future__ import annotations

import json
import sys
import unicodedata
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TERMS_PATH = ROOT / "contracts" / "cosmetic-claim-banned-terms.json"
TARGETS = [
    ROOT / "contracts" / "localization" / "products-ko.json",
    ROOT / "frontend" / "src" / "mocks" / "products.ssafy-beauty.json",
]


def norm(s: str) -> str:
    s = unicodedata.normalize("NFC", s or "")
    return "".join(ch for ch in s if ch.isalnum())


def load_rules(path: Path = TERMS_PATH) -> tuple[list[str], list[str]]:
    d = json.loads(path.read_text(encoding="utf-8"))
    pc = d.get("product_copy") or {}
    skip = set(pc.get("skip_groups", []))
    exempt = set(pc.get("exempt_terms", []))
    banned = [w for g, ws in d["banned"].items() if g not in skip for w in ws if w not in exempt]
    banned = list(dict.fromkeys(banned + list(pc.get("extra_banned", []))))
    allow = list((d.get("allow") or {}).get("terms", [])) + list(pc.get("allow", []))
    return banned, allow


def scan_text(text: str, banned: list[str], allow: list[str]) -> list[str]:
    raw = text or ""
    for a in allow:
        raw = raw.replace(a, " ")
    n = norm(raw)
    return [w for w in banned if norm(w) and norm(w) in n]


def product_texts(path: Path):
    """(위치, 문장) — 상품명과 description 의 모든 문자열"""
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.items() if isinstance(data, dict) else ((p.get("product_id"), p) for p in data)
    for pid, prod in items:
        if pid == "_meta" or not isinstance(prod, dict):
            continue
        yield f"{pid}.product_name", prod.get("product_name") or ""
        for k, v in (prod.get("description") or {}).items():
            for i, s in enumerate(v if isinstance(v, list) else [v]):
                if isinstance(s, str):
                    yield f"{pid}.description.{k}" + (f"[{i}]" if isinstance(v, list) else ""), s


def find_hits() -> list[tuple[str, str, list[str]]]:
    banned, allow = load_rules()
    hits = []
    for path in TARGETS:
        for where, text in product_texts(path):
            h = scan_text(text, banned, allow)
            if h:
                hits.append((f"{path.relative_to(ROOT).as_posix()}:{where}", text, h))
    return hits


class ProductCopyClaimTest(unittest.TestCase):
    def test_rules_catch_known_bad_sentences(self) -> None:
        banned, allow = load_rules()
        for bad in [
            "아토피 치료 및 피부 재생 촉진 성분",
            "아토피 피부염을 즉시 완화해주며",
            "습진 같은 심각한 피부 문제를 위한 집중 치료 제품",
            "항염 효과를 위해 사용해 온 성분",
            "자연 콜라겐 생성을 지원합니다",
        ]:
            self.assertTrue(scan_text(bad, banned, allow), bad)
        self.assertEqual([], scan_text("재생 에너지로 운영되는 시설", banned, allow))
        self.assertEqual([], scan_text("건조하고 민감한 피부를 빠르게 진정시켜 줍니다", banned, allow))

    def test_product_copy_has_no_banned_terms(self) -> None:
        hits = find_hits()
        msg = "\n".join(f"{w}: {h} ← {t[:80]}" for w, t, h in hits[:30])
        self.assertEqual([], hits, f"금지 표현 {len(hits)}곳:\n{msg}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    found = find_hits()
    for where, text, h in found:
        print(f"{where}: {', '.join(h)}\n    {text[:160]}")
    print(f"금지 표현이 남은 문장 {len(found)}개")
    sys.exit(1 if found else 0)
