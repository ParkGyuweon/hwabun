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

_PAREN = re.compile(r"\([^)]*\)")
_NOISE = re.compile(r"^(water|aqua|eau)$|^\d|^and$|^or$|^may contain")
_SPLIT = re.compile("[,;" + chr(10) + "]")
_POP = re.compile(r"allure|Best of Beauty|Community Favorite|Award|Winner", re.I)

ORDER = ["secondary_category", "tertiary_category", "concern",
         "ingredient", "clean", "texture", "price_bin", "rating"]


class Encoder:
    def __init__(self, vocab_path=None, products_path=None):
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

    # ---------- 태그 분류 ----------
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
