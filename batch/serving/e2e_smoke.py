# -*- coding: utf-8 -*-
"""
HWABUN E2E 스모크 — 판매자 가입 → 브랜드 → 상품 등록 → ACTIVE → 목록/상세 → 추천 카탈로그 동기화 → 추천 응답
→ 회원 가입 → 추천(속성) → 장바구니 → 주문 → 결제 → 판매자 요약 → 마트 API. 24단계, 단계마다 PASS/FAIL 한 줄.
================================================================================

    PYTHONUTF8=1 python batch/serving/e2e_smoke.py
    BE=http://127.0.0.1:8090 RS=http://127.0.0.1:8300 FE=http://127.0.0.1:5173 python batch/serving/e2e_smoke.py

어디서 끊기는지 보는 용도다 (2026-09-14, Jira 296). 백엔드가 고친 뒤 같은 스크립트를 다시 돌리면 어느 단계가 풀렸는지
바로 보인다. 크레딧 0. 09-14 로컬 결과 14/24 — 실패 10 은 전부 백엔드 붙여넣기 문서 1~9번 항목(createdAt·size·404→401·
마트 API 7개·프록시). 전제: shop_backend(8090, MySQL·JWT_SECRET) · 추천 서버(8300, SHOP_BACKEND_URL 켬) · 프론트(5173).
매 실행이 새 판매자·브랜드·상품·회원을 만든다(id 에 난수) — 시연 DB 에서는 돌리지 말 것.
"""
import os
import json, sys, time, urllib.request, urllib.error, uuid
BE = os.environ.get("BE", "http://127.0.0.1:8090"); RS = os.environ.get("RS", "http://127.0.0.1:8300"); FE = os.environ.get("FE", "http://127.0.0.1:5173")
run = uuid.uuid4().hex[:6]
def call(method, url, body=None, token=None, timeout=20):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token: req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            return r.status, (json.loads(raw) if raw.strip() else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try: return e.code, json.loads(raw)
        except Exception: return e.code, raw[:200]
    except Exception as e:
        return 0, str(e)[:200]
results = []
def step(name, ok, note=""):
    results.append((name, ok, note)); print(f"{'PASS' if ok else 'FAIL'}  {name}  {note}")

# 1 판매자 가입 + 로그인
st, r = call("POST", f"{BE}/api/auth/sellers", {"email": f"seller-{run}@e2e.local", "password": "Passw0rd!e2e", "nickname": "e2e", "name": f"E2E 판매자 {run}"})
seller_tok = (r or {}).get("token") if isinstance(r, dict) else None
step("1 판매자 가입", st in (200, 201) and bool(seller_tok), f"HTTP {st}")
if not seller_tok:
    st, r = call("POST", f"{BE}/api/auth/login", {"email": f"seller-{run}@e2e.local", "password": "Passw0rd!e2e", "role": "SELLER"})
    seller_tok = (r or {}).get("token") if isinstance(r, dict) else None
    step("1b 판매자 로그인", bool(seller_tok), f"HTTP {st}")
# 2 브랜드
st, r = call("POST", f"{BE}/api/brands", {"name": f"E2E Beauty {run}", "description": "e2e"}, seller_tok)
brand_id = (r or {}).get("id") if isinstance(r, dict) else None
step("2 브랜드 생성", st in (200, 201) and bool(brand_id), f"HTTP {st} brand_id={brand_id}")
# 3 상품 등록 (프론트 페이로드 모양)
body = {"brandId": brand_id, "categoryId": "Moisturizers", "productName": f"E2E Hydra Cream {run}",
        "secondaryCategory": "Moisturizers", "tertiaryCategory": "Moisturizers",
        "highlights": ["Hydrating", "Clean at Sephora"], "ingredients": "Water, Glycerin, Niacinamide, Hyaluronic Acid, Ceramide NP",
        "priceKrw": 32000, "size": "50ml", "primaryImageUrl": None,
        "description": {"what_it_is": "e2e 테스트 크림", "suggested_usage": None, "highlighted_ingredients": ["Niacinamide"], "ingredient_callouts": None, "brand_story": None}}
st, r = call("POST", f"{BE}/api/products", body, seller_tok)
pid = None
if isinstance(r, dict): pid = (r.get("product") or {}).get("productId") or r.get("productId")
step("3 상품 등록 POST /api/products", st in (200, 201) and bool(pid), f"HTTP {st} product_id={pid} {'' if pid else str(r)[:160]}")
if pid:
    st, r = call("PATCH", f"{BE}/api/products/{pid}/status?value=ACTIVE", None, seller_tok)
    step("4 ACTIVE 전환", st in (200, 204), f"HTTP {st}")
    st, r = call("GET", f"{BE}/api/products")
    mine = [p for p in (r or []) if p.get("productId") == pid] if isinstance(r, list) else []
    step("5 목록에 노출(익명 GET)", st == 200 and bool(mine), f"HTTP {st} 목록 {len(r) if isinstance(r, list) else '?'}개")
    step("5b 목록 요약에 createdAt", bool(mine) and "createdAt" in mine[0], f"keys={sorted(mine[0].keys()) if mine else '-'}"[:200])
    step("5c 목록 요약에 size(용량)", bool(mine) and ("size" in json.dumps(mine[0])), "요청서 9-5")
    st, d = call("GET", f"{BE}/api/products/{pid}")
    variants = (d or {}).get("variants") if isinstance(d, dict) else None
    step("6 상세 GET", st == 200 and bool(variants), f"HTTP {st} variants={len(variants) if variants else 0}")
    step("6b 상세 variant.size 보존", bool(variants) and any(v.get("size") for v in variants), f"{[v.get('size') for v in (variants or [])]}")
# 4xx → 401 함정
st, r = call("GET", f"{BE}/api/products/NOPE-{run}")
step("7 없는 상품 GET → 404 여야 함", st == 404, f"HTTP {st} (요청서 9-1: /error permitAll)")
# 추천 서버 카탈로그 동기화
st, r = call("POST", f"{RS}/api/catalog/sync", {})
step("8 추천 카탈로그 동기화 POST /api/catalog/sync", st == 200, f"HTTP {st} {json.dumps(r, ensure_ascii=False)[:200]}")
if pid:
    st, r = call("GET", f"{RS}/api/products/{pid}")
    step("9 추천 서버에 편입", st == 200, f"HTTP {st} registered_at={ (r or {}).get('registered_at') if isinstance(r, dict) else '-'} new_until={(r or {}).get('new_until') if isinstance(r, dict) else '-'}")
    # registered_at 은 백엔드 createdAt 이 없으면 편입 시각으로 대체된다(요청서 9-11). 편입 직후라 두 값이 거의 같아 자동 판별은 못 한다
# 회원 가입 → 추천
st, r = call("POST", f"{BE}/api/auth/members", {"email": f"member-{run}@e2e.local", "password": "Passw0rd!e2e", "nickname": f"e2e-{run}", "agreeTerms": True, "agreePrivacy": True})
member_tok = (r or {}).get("token") if isinstance(r, dict) else None; member_id = (r or {}).get("id") if isinstance(r, dict) else None
step("10 회원 가입", st in (200, 201) and bool(member_tok), f"HTTP {st} id={member_id}")
st, r = call("GET", f"{RS}/api/recommend?persona_id={member_id}&size=10&hero=new_brand&banner_slots=1&skin_type=dry&skin_tone=fair")
items = (r or {}).get("items", []) if isinstance(r, dict) else []
step("11 추천 직접 호출(실회원 id + 속성)", st == 200 and len(items) == 10, f"HTTP {st} attribute_source={(r or {}).get('attribute_source') if isinstance(r, dict) else '-'} hero={(r or {}).get('hero_policy') if isinstance(r, dict) else '-'} {((r or {}).get('hero') or {}).get('product_id') if isinstance(r, dict) else ''}")
if pid: step("11b 등록 상품이 신규로 추천 후보에", any(i.get("product_id") == pid for i in items) or (isinstance(r, dict) and ((r.get("hero") or {}).get("product_id") == pid)), "items 또는 hero 에 있는가 (없어도 결함은 아님, 점수순)")
st, r = call("GET", f"{FE}/api/recommend?persona_id={member_id}&size=5&hero=new_brand&banner_slots=1")
step("12 프론트 Vite 프록시 → 추천", st == 200, f"HTTP {st}")
st, r = call("GET", f"{BE}/api/recommend?size=5", None, member_tok)
step("13 백엔드 프록시 GET /api/recommend", st == 200, f"HTTP {st} (dev 미머지면 401/404)")
# 장바구니 → 주문 → 결제
if pid and variants:
    vid = variants[0].get("variantId")
    st, r = call("POST", f"{BE}/api/cart/items", {"variantId": vid, "quantity": 1}, member_tok)
    step("14 장바구니 담기", st in (200, 201), f"HTTP {st}")
    st, r = call("POST", f"{BE}/api/orders", {"idempotencyKey": f"e2e-{run}"}, member_tok)
    oid = None
    if isinstance(r, dict): oid = r.get("orderId") or r.get("id") or r.get("order_id")
    step("15 주문 생성", st in (200, 201) and bool(oid), f"HTTP {st} order_id={oid} keys={sorted(r.keys())[:8] if isinstance(r, dict) else r}")
    if oid:
        st, r = call("POST", f"{BE}/api/orders/{oid}/pay", {}, member_tok)
        step("16 결제", st in (200, 201), f"HTTP {st}")
        st, r = call("GET", f"{BE}/api/seller/dashboard?brandId={brand_id}", None, seller_tok)
        step("17 판매자 요약 4타일", st == 200 and isinstance(r, dict) and (r.get("orders") or 0) >= 1, f"HTTP {st} {json.dumps(r, ensure_ascii=False)[:120]}")
for ep in ["overview", "products", "purchase"]:
    st, r = call("GET", f"{BE}/api/seller/dashboard/{ep}?brandId={brand_id}", None, seller_tok)
    step(f"18 마트 API /api/seller/dashboard/{ep}", st == 200, f"HTTP {st}")
n_ok = sum(1 for _, ok, _ in results if ok)
print(f"\n== {n_ok}/{len(results)} PASS")
