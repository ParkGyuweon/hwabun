# -*- coding: utf-8 -*-
"""쇼핑몰 백엔드(shop_backend, 8090)의 판매 중 상품을 추천 카탈로그에 맞춘다 (Jira 222).

왜
    등록 상품이 추천에 들어오는 정식 경로는 "백엔드가 승인 시 POST /api/products 를 부른다" (요청서 4-1).
    그 훅이 없어도 카탈로그가 어긋나지 않게, 추천 서버가 **백엔드 공개 API 를 주기적으로 읽어**
    ACTIVE 상품은 편입·갱신하고 목록에서 사라진 상품은 판매 중단 처리한다. 훅이 생기면 둘이 같이
    돌아도 된다 — 같은 product_id 는 갈아 끼우기라 충돌이 없다.

무엇을 읽나 (shop_backend CatalogController, 인증 없음)
    GET /api/products         ACTIVE 상품 요약 — productId·brandId·brandName·secondaryCategory·
                              tertiaryCategory·highlights·priceKrw(활성 옵션 최저가)·rating·lovesCount
    GET /api/products/{id}    상세 — ingredients(전성분 문자열). 요약에 없어 상품마다 한 번 더 부른다

매핑 → 등록 입력 (contracts/product-registration-spec §3)
    product_id ← productId · product_name ← productName · brand_name ← brandName(없으면 brandId)
    secondary/tertiary_category · highlights · ingredients ← detail.ingredients · price_krw ← priceKrw
    rating 은 넘기지 않는다 — 백엔드도 중앙값을 주입한 값이라, 우리 §4.2 규칙으로 다시 주입해 기준을 하나로 둔다

변경 감지
    매핑한 입력의 해시를 기록에 남겨(sync_hash) 같으면 다시 인코딩하지 않는다.
    이전 동기화에서 들어왔던(sync_source=shop_backend) 상품이 목록에서 빠지면 deactivate.
    시연 시드(SSAFY Beauty 8개, sync_source 없음)는 백엔드 목록에 없어도 건드리지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request

SYNC_SOURCE = "shop_backend"


def _get(opener, url, timeout):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with opener(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def to_registration(summary: dict, ingredients: str | None) -> dict:
    """백엔드 ProductSummary(+상세 전성분) → POST /api/products 입력"""
    return {
        "product_id": summary["productId"],
        "product_name": summary.get("productName"),
        "brand_name": summary.get("brandName") or summary.get("brandId"),
        "brand_id": summary.get("brandId"),
        "secondary_category": summary.get("secondaryCategory"),
        "tertiary_category": summary.get("tertiaryCategory"),
        "highlights": list(summary.get("highlights") or []),
        "ingredients": ingredients or "",
        "price_krw": summary.get("priceKrw"),
        "image_url": summary.get("primaryImageUrl"),
        "review_count": 0,
        # 백엔드 등록 시각(요청서 6-2). 없으면 registry 가 동기화 시각을 넣는다 — 그만큼 신규 기간이 늦게 시작된다
        "registered_at": summary.get("createdAt"),
    }


def input_hash(inp: dict) -> str:
    return hashlib.sha256(json.dumps(inp, sort_keys=True, ensure_ascii=False, default=str)
                          .encode("utf-8")).hexdigest()[:16]


def sync(engine, base_url: str, opener=None, timeout: float = 10.0, log=print) -> dict:
    """한 번 동기화. 결과 요약 dict 를 돌려준다 (health 에 실린다)."""
    opener = opener or urllib.request.urlopen
    base = base_url.rstrip("/").replace("://localhost", "://127.0.0.1")
    t0 = time.perf_counter()
    out = {"source": base, "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "listed": 0,
           "added": [], "replaced": [], "unchanged": 0, "deactivated": [], "rejected": {}, "error": None}
    try:
        listed = _get(opener, base + "/api/products", timeout)
    except Exception as ex:
        out["error"] = f"list: {ex.__class__.__name__}: {ex}"
        log(f"[catalog-sync] 백엔드 목록을 못 읽었다 — {out['error']}")
        out["ms"] = round((time.perf_counter() - t0) * 1000, 1)
        return out
    out["listed"] = len(listed)

    # 이미 들어와 있는 백엔드 상품과 그 해시
    known = {}
    for p in engine.products:
        if p.get("sync_source") == SYNC_SOURCE:
            known[p["product_id"]] = p.get("sync_hash")

    seen = set()
    to_register = []
    for s in listed:
        pid = s.get("productId")
        if not pid:
            continue
        seen.add(pid)
        # 상세는 전성분이 필요할 때만 (새 상품이거나 요약이 달라졌을 때) 부른다
        probe = to_registration(s, None)
        probe_hash = input_hash({k: v for k, v in probe.items() if k != "ingredients"})
        if pid in known and known[pid] and known[pid].startswith(probe_hash) and pid not in engine.inactive:
            out["unchanged"] += 1
            continue
        try:
            d = _get(opener, f"{base}/api/products/{pid}", timeout)
            ing = d.get("ingredients") if isinstance(d, dict) else None
        except Exception as ex:
            out["rejected"][pid] = [f"detail: {ex.__class__.__name__}"]
            continue
        inp = to_registration(s, ing)
        inp["_sync_hash"] = probe_hash + "-" + input_hash({"ingredients": ing})
        to_register.append(inp)

    for inp in to_register:
        h = inp.pop("_sync_hash")
        try:
            res = engine.register([inp])[0]
            row = engine.products[engine.index[inp["product_id"]]]
            row["sync_source"] = SYNC_SOURCE
            row["sync_hash"] = h
            (out["added"] if res["action"] == "added" else out["replaced"]).append(inp["product_id"])
        except Exception as ex:                     # 계약 위반 등 — 하나 때문에 전체가 멎지 않는다
            errs = getattr(ex, "errors", None) or [f"{ex.__class__.__name__}: {ex}"]
            out["rejected"][inp["product_id"]] = list(errs)

    # 목록에서 사라진 백엔드 상품 → 판매 중단
    for pid in known:
        if pid not in seen and pid not in engine.inactive:
            engine.deactivate(pid)
            out["deactivated"].append(pid)

    out["ms"] = round((time.perf_counter() - t0) * 1000, 1)
    log(f"[catalog-sync] {base} 목록 {out['listed']} · 추가 {len(out['added'])} · 갱신 {len(out['replaced'])} · "
        f"그대로 {out['unchanged']} · 중단 {len(out['deactivated'])} · 거부 {len(out['rejected'])} · {out['ms']}ms")
    return out
