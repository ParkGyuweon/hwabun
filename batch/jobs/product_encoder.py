"""
상품 벡터 인코더 — 단일 구현.
contracts/product-feature-vocab.json 만 읽어 동작하므로 어휘집이 유일한 진실 소스다.
"""
import json, os, re
import numpy as np

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
# 어휘집은 계약, 상품 카탈로그는 수집 결과라 서로 다른 곳에 있다
VOCAB = os.path.join(ROOT, "contracts", "product-feature-vocab.json")
PRODUCTS = os.path.join(ROOT, "batch", "ingest", "data", "products_200.json")
REVIEW_CONCERN = os.path.join(ROOT, "batch", "ingest", "data", "concern_from_reviews.npz")
REVIEW_CONCERN_TOPK = 2

_PAREN = re.compile(r"\([^)]*\)")
_NOISE = re.compile(r"^(water|aqua|eau)$|^\d|^and$|^or$|^may contain")
_SPLIT = re.compile("[,;" + chr(10) + "]")
_POP = re.compile(r"allure|Best of Beauty|Community Favorite|Award|Winner", re.I)

# 블록 순서. brand 는 뒤에 붙여 기존 차원 순서를 흔들지 않는다.
ORDER = ["secondary_category", "tertiary_category", "concern",
         "ingredient", "clean", "texture", "price_bin", "rating", "brand"]


class Encoder:
    def __init__(self, vocab_path=None, products_path=None, review_concern_path=None):
        vocab_path = vocab_path or VOCAB
        products_path = products_path or PRODUCTS
        self.V = json.load(open(vocab_path, encoding="utf-8"))
        self.products = json.load(open(products_path, encoding="utf-8"))
        self.blk = {b["name"]: b for b in self.V["blocks"]}
        self.w = {b["name"]: b["block_weight"] for b in self.V["blocks"]}
        self.w["rating"] = self.V["scalars"][0]["block_weight"]
        self.rmin = self.V["scalars"][0]["min"]
        self.rmax = self.V["scalars"][0]["max"]
        self.edges = self.V["price_bin_edges"]
        self.N = len(self.products)
        self.ing_syn = self.V["ingredient_source"]["synonyms"]
        self.pos_min = self.V["ingredient_source"]["position_min"]
        self.tag_ing = set(self.blk["ingredient"]["vocab"])
        self.clean_set = set(self.blk["clean"]["vocab"])
        self.tex_set = set(self.blk["texture"]["vocab"])
        self.review_concern = self._load_review_concern(review_concern_path)

    # ---------- 태그 분류 ----------
    def _load_review_concern(self, path):
        """리뷰에서 뽑은 concern 점수를 상위 2축 이진 태그로 바꿔 둔다.

        파일이 없으면 None 을 돌려주고 highlights 만 쓴다 — 있으면 좋고 없어도 돈다.
        만드는 법은 batch/jobs/concern_from_reviews.py 참고.
        """
        path = path or REVIEW_CONCERN
        if not os.path.exists(path):
            return None
        z = np.load(path, allow_pickle=True)
        gid, axes, S = list(z["group_id"]), list(z["axes"]), z["score"]
        vocab = self.blk["concern"]["vocab"]
        try:
            order = [axes.index(c) for c in vocab]
        except ValueError:
            return None                      # 축이 어휘집과 안 맞으면 쓰지 않는다
        out = {}
        for i, g in enumerate(gid):
            s = S[i, order]
            v = np.zeros(len(vocab))
            for j in np.argsort(-s)[:REVIEW_CONCERN_TOPK]:
                if s[j] > 0:
                    v[j] = 1.0
            out[g] = v
        return out

    def split_tags(self, x):
        c, cl, t = [], [], []
        for h in x["highlights"]:
            if h.startswith("Good for:"):
                c.append(h.split(":", 1)[1].strip())
            elif h.startswith("Best for") and h.endswith("Skin"):
                continue
            elif h in self.clean_set:
                cl.append(h)
            elif _POP.search(h):
                continue
            elif h in self.tex_set:
                t.append(h)
        return {"concern": c, "clean": cl, "texture": t}

    def parse_ingredients(self, x):
        txt = _PAREN.sub(" ", " ".join(x["ingredients"]))
        out = []
        for tok in _SPLIT.split(txt):
            s = re.sub(r"[^A-Za-z0-9 \-/]", " ", tok).strip().lower()
            s = re.sub(r"\s+", " ", s)
            if not s or len(s) < 3 or len(s) > 45 or _NOISE.match(s):
                continue
            out.append(s)
        return out

    def ingredient_values(self, x):
        """태그로 표시된 성분은 1.0, 전성분에서만 찾은 성분은 위치 기반 감쇠"""
        tagged = {h for h in x["highlights"] if h in self.tag_ing}
        lst = self.parse_ingredients(x)
        n = max(len(lst), 1)
        vals = {}
        for name in self.blk["ingredient"]["vocab"]:
            if name in tagged:
                vals[name] = 1.0
                continue
            syns = self.ing_syn.get(name)
            if not syns:
                continue
            for pos, tok in enumerate(lst):
                if any(sy in tok for sy in syns):
                    vals[name] = max(1.0 - pos / n, self.pos_min)
                    break
        return vals

    # ---------- 블록 인코딩 ----------
    def _onehot(self, val, name):
        v = np.zeros(self.blk[name]["dim"])
        vocab = self.blk[name]["vocab"]
        if val in vocab:
            v[vocab.index(val)] = 1.0
        return v

    def _multihot_idf(self, present, name):
        vocab, df = self.blk[name]["vocab"], self.blk[name]["doc_freq"]
        v = np.zeros(len(vocab))
        for j, tok in enumerate(vocab):
            if tok in present:
                v[j] = np.log(self.N / (1 + df[tok]))
        return v

    def blocks(self, x):
        tg = self.split_tags(x)
        raw = {
            "secondary_category": self._onehot(x["secondary_category"], "secondary_category"),
            "tertiary_category": self._onehot(x["tertiary_category"], "tertiary_category"),
            "concern": self._multihot_idf(set(tg["concern"]), "concern"),
            "clean": self._multihot_idf(set(tg["clean"]), "clean"),
            "texture": self._multihot_idf(set(tg["texture"]), "texture"),
        }
        # ingredient: IDF x 위치가중
        vocab, df = self.blk["ingredient"]["vocab"], self.blk["ingredient"]["doc_freq"]
        iv = self.ingredient_values(x)
        v = np.zeros(len(vocab))
        for j, tok in enumerate(vocab):
            if tok in iv:
                v[j] = np.log(self.N / (1 + df[tok])) * iv[tok]
        raw["ingredient"] = v
        pl = self.blk["price_bin"]["vocab"]
        raw["price_bin"] = self._onehot(
            pl[int(np.digitize(x["price_usd"], self.edges[1:], right=False))], "price_bin")
        raw["rating"] = np.array([(x["rating"] - self.rmin) / (self.rmax - self.rmin)])

        # brand — 다음 구매에서 유지되는 속성 중 lift 가 압도적이다 (6.08x).
        # 리뷰 15만 연속쌍에서 재보니 2위 price_bin 이 1.30x 였다.
        # 없던 신호를 넣은 것만으로 Recall@10 이 11.4% -> 23.6% 가 됐다.
        raw["brand"] = self._onehot(x["brand_name"], "brand")

        # concern 보강 — highlights 는 마케팅 문구라 "이 제품이 무엇을 해결하는가" 를
        # 다 담지 못한다. 상품당 평균 2,291건의 리뷰에서 뽑은 상위 2축을 더한다.
        # 대체가 아니라 덧셈이다. highlights 를 버리면 오히려 나빠진다.
        if self.review_concern is not None:
            r = self.review_concern.get(x["product_id"])
            if r is not None:
                raw["concern"] = raw["concern"] + r
        return raw

    def encode(self, x, weights=None):
        w = weights or self.w
        raw = self.blocks(x)
        out = []
        for nm in ORDER:
            b = raw[nm]
            n = np.linalg.norm(b)
            out.append((b / n if n > 0 else b) * w[nm])
        v = np.concatenate(out)
        n = np.linalg.norm(v)
        return v / n if n > 0 else v

    def matrix(self, weights=None, dtype=np.float32):
        return np.vstack([self.encode(x, weights) for x in self.products]).astype(dtype)

    def prior(self):
        lv = np.array([x["loves_count"] for x in self.products], dtype=float)
        lg = np.log1p(lv)
        return (lg - lg.min()) / (lg.max() - lg.min())


if __name__ == "__main__":
    e = Encoder()
    M = e.matrix()
    print(f"어휘집 {e.V['version']} / 벡터 {M.shape}")
    print(f"L2 노름 min {np.linalg.norm(M,axis=1).min():.6f} "
          f"max {np.linalg.norm(M,axis=1).max():.6f}")
    S = M @ M.T
    np.fill_diagonal(S, 0)
    off = S[~np.eye(len(M), dtype=bool)]
    print(f"상품 간 코사인  중앙 {np.median(off):.4f}  p95 {np.percentile(off,95):.4f}  "
          f"음수 {int((off<0).sum())}개  0.99이상 {int((off>=0.99).sum())//2}쌍")
    empty = [i for i, x in enumerate(e.products)
             if not e.split_tags(x)["concern"] and not e.ingredient_values(x)]
    print(f"concern+ingredient 둘 다 빈 상품: {len(empty)}개")
