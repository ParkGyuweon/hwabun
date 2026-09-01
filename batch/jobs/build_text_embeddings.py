"""
텍스트 임베딩 산출 — hidden preference 의 `seed_review_text_match` 재료.

    페르소나 쪽: seed 긍정 리뷰 텍스트 -> 문장별 임베딩 -> 평균 -> L2 정규화
    상품 쪽:     이름·브랜드·하이라이트·전성분·수집한 상세 설명 -> 조각별 임베딩 -> 평균

    산출: batch/ingest/data/text_embeddings.npz
          persona_ids · persona_vecs(9,900 x 384) · product_ids · product_vecs(200 x 384)

**추천 모델에는 쓰지 않는다.** 리뷰 임베딩으로 추천 정확도를 올리려던 시도는 27개
구성이 전부 실패해 닫은 길이다. 여기서 쓰는 곳은 **행동 생성을 추천에서 떼어내는
hidden preference** 뿐이다 (docs/ai/evaluation-framework.md 2절).

누출 방지
    - `eval_metadata.jsonl` 의 **seed 상품 리뷰만** 임베딩한다. target 상품에 대해
      그 사용자가 쓴 리뷰는 들어가지 않는다.
    - 상품 텍스트는 사용자와 무관하므로 그대로 쓴다.

실행: python batch/jobs/build_text_embeddings.py [--device cuda] [--model all-MiniLM-L6-v2]
"""
import argparse
import json
import os
import sys
import time

import numpy as np

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
sys.path.insert(0, BD)
from eval_metadata import POSITIVE, load as load_metadata     # noqa: E402

PERSONAS = os.path.join(ROOT, "simulator", "personas", "data", "personas_9900.json")
PRODUCTS = os.path.join(ROOT, "batch", "ingest", "data", "products_200.json")
DESCRIPTIONS = os.path.join(ROOT, "frontend", "src", "mocks", "products.collected.json")
OUT = os.path.join(ROOT, "batch", "ingest", "data", "text_embeddings.npz")
DEFAULT_MODEL = "all-MiniLM-L6-v2"
MAX_CHARS = 900        # 조각 하나의 길이 상한. 모델이 256토큰에서 자르므로 그 전에 나눈다


def _load(path, default=None):
    if not os.path.exists(path):
        if default is None:
            raise SystemExit(f"파일이 없습니다: {path}")
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def product_chunks(product, description):
    """상품 하나를 여러 조각으로 나눈다. 긴 글을 한 벡터로 뭉개면 신호가 흐려진다"""
    chunks = [f"{product.get('brand_name', '')} {product.get('product_name', '')}"]
    highlights = product.get("highlights") or []
    if highlights:
        chunks.append(", ".join(str(h) for h in highlights))
    ingredients = str(product.get("ingredients") or "")[:MAX_CHARS]
    if ingredients.strip():
        chunks.append(ingredients)
    if isinstance(description, dict):
        body = description.get("description") or description
        for value in body.values():
            if isinstance(value, str) and value.strip():
                chunks.append(value[:MAX_CHARS])
            elif isinstance(value, list):
                joined = " ".join(str(v) for v in value)[:MAX_CHARS]
                if joined.strip():
                    chunks.append(joined)
    return [c for c in chunks if c.strip()]


def persona_chunks(persona, seeds):
    """seed 긍정 리뷰만. 리뷰 한 건이 조각 하나다"""
    seed_set = set(seeds)
    out = []
    for r in persona.get("reviews", []):
        if r.get("group_id") not in seed_set:
            continue
        if (r.get("rating") or 0) < POSITIVE:
            continue
        text = f"{r.get('review_title') or ''} {r.get('review_text') or ''}".strip()
        if text:
            out.append(text[:MAX_CHARS])
    return out


def encode_grouped(model, groups, batch_size, label):
    """[[조각...], ...] -> 그룹별 평균 벡터. 한 번에 인코딩하고 나눠 담는다"""
    flat, spans = [], []
    for chunks in groups:
        spans.append((len(flat), len(flat) + len(chunks)))
        flat.extend(chunks)
    print(f"  {label}: 그룹 {len(groups):,}개 · 조각 {len(flat):,}개")
    if not flat:
        return np.zeros((len(groups), model.get_sentence_embedding_dimension()),
                        dtype=np.float32)
    t0 = time.time()
    vecs = model.encode(flat, batch_size=batch_size, convert_to_numpy=True,
                        normalize_embeddings=True, show_progress_bar=False)
    print(f"    인코딩 {time.time() - t0:.1f}초 ({len(flat) / max(time.time() - t0, 1e-9):,.0f} 조각/초)")

    dim = vecs.shape[1]
    out = np.zeros((len(groups), dim), dtype=np.float32)
    for i, (lo, hi) in enumerate(spans):
        if hi > lo:
            mean = vecs[lo:hi].mean(axis=0)
            norm = np.linalg.norm(mean)
            out[i] = mean / norm if norm > 1e-9 else mean
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--device", default=None, help="cuda / cpu (기본: 있으면 cuda)")
    ap.add_argument("--batch-size", type=int, default=256)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()

    import torch
    from sentence_transformers import SentenceTransformer
    device = a.device or ("cuda" if torch.cuda.is_available() else "cpu")
    print(f"모델 {a.model} · 장치 {device}")
    model = SentenceTransformer(a.model, device=device)

    products = _load(PRODUCTS)
    descriptions = _load(DESCRIPTIONS, {})
    product_ids = [p["product_id"] for p in products]
    product_vecs = encode_grouped(
        model, [product_chunks(p, descriptions.get(p["product_id"])) for p in products],
        a.batch_size, "상품")

    profiles = {p["persona_id"]: p for p in _load(PERSONAS)}
    rows = load_metadata()
    persona_ids = [r["persona_id"] for r in rows]
    persona_vecs = encode_grouped(
        model,
        [persona_chunks(profiles[r["persona_id"]], r["seed_product_ids"])
         for r in rows],
        a.batch_size, "페르소나 seed 리뷰")

    empty = int((np.linalg.norm(persona_vecs, axis=1) < 1e-6).sum())
    np.savez_compressed(
        a.out, model=a.model, dim=product_vecs.shape[1],
        product_ids=np.array(product_ids), product_vecs=product_vecs,
        persona_ids=np.array(persona_ids), persona_vecs=persona_vecs)
    size = os.path.getsize(a.out) / 1024 / 1024
    print(f"\n저장 {os.path.relpath(a.out, ROOT)} ({size:.1f}MB)")
    print(f"  상품 {product_vecs.shape} · 페르소나 {persona_vecs.shape}"
          f" · 빈 벡터 {empty}명 (seed 긍정 리뷰에 텍스트가 없는 사람)")

    # 눈으로 확인 — 같은 브랜드끼리 붙는지
    sim = product_vecs @ product_vecs.T
    np.fill_diagonal(sim, -1)
    i = 0
    order = np.argsort(-sim[i])[:3]
    print(f"\n  '{products[i]['product_name'][:40]}' 와 가까운 상품")
    for j in order:
        print(f"    {sim[i][j]:.3f}  {products[j]['brand_name'][:12]:<12}"
              f" {products[j]['product_name'][:40]}")


if __name__ == "__main__":
    main()
