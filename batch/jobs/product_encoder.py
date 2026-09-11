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
_AND = re.compile(r"\(\s*and\s*\)", re.I)        # INCI 블렌드 구분자 "(and)"
_NOISE = re.compile(r"^(water|aqua|eau|정제수|물)$|^\d|^and$|^or$|^may contain")
_SPLIT = re.compile("[,;" + chr(10) + "]")
_SPF_NAME = re.compile(r"\bspf\s*\d", re.I)   # 제품명의 자외선차단지수 표기 (Jira 243)
_POP = re.compile(r"allure|Best of Beauty|Community Favorite|Award|Winner", re.I)

# 블록 순서. brand 는 뒤에 붙여 기존 차원 순서를 흔들지 않는다.
ORDER = ["secondary_category", "tertiary_category", "concern",
         "ingredient", "clean", "texture", "price_bin", "rating", "brand"]


# 카테고리 중앙값을 쓰려면 표본이 이만큼은 있어야 한다 (등록 계약 §4.2 와 동일).
# 미만이면 전체 중앙값으로 내려간다
RATING_MIN_N = 3



def brand_key(x):
    """브랜드 식별 키 — 이름이 아니라 **id** 로 묶는다 (2026-09-11, Jira 247).

    원천 상품은 세포라 `brand_id`(정수, 55개 ↔ 이름 55개 1:1) 를 문자열로, 등록 상품은 쇼핑몰 백엔드의
    `brand_id`(문자열) 를 그대로 쓴다. id 가 없으면(시연 시드 SSAFY Beauty) `name:` + brand_name.
    쇼핑몰 `brand` 테이블은 (판매자, 이름) 만 유일해서 **다른 판매자가 같은 이름을 등록할 수 있다** —
    이름을 키로 쓰면 그 상품이 원천 브랜드의 원핫 벡터와 재구매 효과(lift 6x)를 빌리게 된다.
    어휘집 brand 블록의 vocab, 서버의 brands/known, LTR same_brand, new_mask 가 전부 이 키를 쓴다."""
    bid = x.get("brand_id")
    if bid is None or str(bid).strip() == "":
        return "name:" + (x.get("brand_name") or "")
    return str(bid)


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
        self.clean_set = set(self.blk["clean"]["vocab"])
        self.tex_set = set(self.blk["texture"]["vocab"])
        self.review_concern = self._load_review_concern(review_concern_path)
        self._rating_med = None      # 카테고리별 평점 중앙값 (등록 상품 기본값)

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
        # INCI 블렌드 표기 "A (and) B" 는 성분 두 개다 — 괄호를 지우기 전에 쉼표로 바꿔 분리한다.
        # 안 그러면 "dimethyl isosorbide hydroxypinacolone retinoate" 처럼 한 토큰이 45자를 넘어 버려진다
        # (P393718 Luna Retinoid Oil 의 레티노이드가 이래서 빠졌다, 2026-09-10 Jira 243)
        txt = _AND.sub(",", " ".join(x["ingredients"]))
        txt = _PAREN.sub(" ", txt)
        out = []
        for tok in _SPLIT.split(txt):
            # **한글을 남긴다.** 국내 브랜드는 한글 전성분표를 붙여넣는다.
            # 지우면 토큰이 통째로 사라져 성분 매칭이 0 이 된다 (가중치 0.27)
            s = re.sub(r"[^A-Za-z0-9가-힣 \-/]", " ", tok).strip().lower()
            s = re.sub(r"\s+", " ", s)
            # 한글 성분명은 영문보다 짧다 (세라마이드 5자, 판테놀 3자)
            floor = 2 if any("\uac00" <= c <= "\ud7a3" for c in s) else 3
            if not s or len(s) < floor or len(s) > 45 or _NOISE.match(s):
                continue
            out.append(s)
        return out

    def ingredient_values(self, x):
        """성분 값은 **전성분 텍스트에서만** — 위치 기반 감쇠 (앞쪽 1.0 → 끝 pos_min).

        highlights 의 성분 태그(원천 200개 중 110개가 가짐)는 쓰지 않는다 — 계약
        product-registration-spec §3.1. 등록 상품은 폼이 성분 태그를 받지 않으므로 두 집합이
        같은 규칙을 써야 하고, 태그를 1.0 으로 두면 함량 순서가 무시된다. 2026-09-10 까지는
        코드가 태그를 1.0 으로 쓰고 있어 계약과 어긋나 있었다(측정: 부록 참조, 차이 없음).
        """
        lst = self.parse_ingredients(x)
        n = max(len(lst), 1)
        vals = {}
        for name in self.blk["ingredient"]["vocab"]:
            syns = self.ing_syn.get(name)
            if not syns:
                continue
            for pos, tok in enumerate(lst):
                if any(sy in tok for sy in syns):
                    vals[name] = max(1.0 - pos / n, self.pos_min)
                    break
        # SPF 는 제품명의 법정 표기("SPF 36", "SPF50+")로도 켠다. 미국 선크림은 자차 활성성분을 Drug Facts 에
        # 따로 적어 Sephora 전성분 텍스트에 없다(원천 2개: P456392·P456398). 등록 상품 이름도 같은 표기를
        # 쓰므로 두 집합에 같은 규칙이다. 규제 표기라 1.0 (2026-09-10, Jira 243)
        if "SPF" in self.ing_syn and "SPF" not in vals and _SPF_NAME.search(str(x.get("product_name") or "")):
            vals["SPF"] = 1.0
        return vals

    # ---------- 블록 인코딩 ----------
    def rating_value(self, x):
        """평점을 0~1 로. **등록 상품은 평점이 없다** (2026-09-03).

        신규 상품은 리뷰가 0건이라 `rating` 이 없다. 그대로 두면 정규화식이
        터지고(None), 0 을 넣으면 -2.22 라는 음수가 나온다. 브랜드에게 직접
        입력받을 수도 없다 — 자기 평점을 적으면 그게 곧 추천 점수가 된다.

        그래서 **같은 카테고리의 중앙값**을 채운다. 그 카테고리 상품들 사이에서
        평균적인 위치에 놓이므로 유리하지도 불리하지도 않다.

        범위 밖 값은 잘라 낸다. 카탈로그에서 잰 min/max 라, 등록 상품에 실제
        리뷰가 쌓이면 그 범위를 벗어날 수 있다.
        """
        r = x.get("rating")
        if r is None:
            r = self._rating_median(x.get("tertiary_category"))
        v = (r - self.rmin) / (self.rmax - self.rmin)
        return min(max(v, 0.0), 1.0)

    def _rating_median(self, category):
        """카테고리별 평점 중앙값. **표본이 RATING_MIN_N 미만이면 전체 중앙값**.

        상품이 1~2개뿐인 카테고리의 "중앙값" 은 그 상품 한둘의 평점일 뿐이다.
        카탈로그 200개에서 19개 카테고리 중 7개가 표본 3개 미만이고, 전체
        중앙값과 최대 0.489 까지 벌어진다 (For Face n=2 -> 3.833, 전체 4.322).
        등록 상품이 그 카테고리에 들어오면 남의 상품 한 개 평점을 물려받는다.
        데이터 파트 등록 계약 §4.2 와 같은 기준이다.
        """
        if self._rating_med is None:
            by = {}
            for p in self.products:
                if p.get("rating") is None:
                    continue
                by.setdefault(p.get("tertiary_category"), []).append(p["rating"])
            allv = [p["rating"] for p in self.products if p.get("rating") is not None]
            self._rating_med = {c: float(np.median(v)) for c, v in by.items()
                                if len(v) >= RATING_MIN_N}
            self._rating_med[None] = float(np.median(allv)) if allv else self.rmin
        return self._rating_med.get(category, self._rating_med[None])

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
        raw["rating"] = np.array([self.rating_value(x)])

        # brand — 다음 구매에서 유지되는 속성 중 lift 가 압도적이다 (6.08x).
        # 리뷰 15만 연속쌍에서 재보니 2위 price_bin 이 1.30x 였다.
        # 없던 신호를 넣은 것만으로 Recall@10 이 11.4% -> 23.6% 가 됐다.
        raw["brand"] = self._onehot(brand_key(x), "brand")     # 키는 brand_id (Jira 247)

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
        """인기도 0~1. **등록 상품은 loves_count 가 없다** — 0 으로 본다"""
        lv = np.array([x.get("loves_count") or 0 for x in self.products], dtype=float)
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
