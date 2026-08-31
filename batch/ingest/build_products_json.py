# -*- coding: utf-8 -*-
"""
상위 200개 상품 카탈로그 생성 — artifacts/products_200.json
================================================================================

무엇을 하는가
    세포라 원본 CSV(상품 8,494개 / 리뷰 109만건)에서 우리가 쓸 상품 200개를 고른다.

왜 200개인가
    리뷰가 특정 상품에 몰려 있다. 상위 200개가 전체 리뷰의 54.4% 를 덮는다.
    꼬리 쪽 상품은 리뷰가 몇 건뿐이라 속성별 affinity 통계가 성립하지 않는다.

이 파일의 핵심은 "사이즈 변형 병합" 이다
    세포라는 같은 제품의 30ml / 50ml / 미니 사이즈를 각각 다른 product_id 로 판다.
    그대로 두면 상위 200개가 사실상 같은 제품의 중복으로 채워지고,
    "다음에 뭘 살까" 를 맞히는 문제에서 30ml 를 산 사람에게 50ml 를 추천하는
    무의미한 정답이 만들어진다. 그래서 하나로 합친 뒤 순위를 매긴다.

입력
    <SEPHORA_DATASET>/reviews_*.csv    리뷰 5개 파일
    <SEPHORA_DATASET>/product_info.csv 상품 메타 (27개 컬럼)
    원본 CSV 는 .gitignore 대상이라 레포에 없다. 환경변수로 위치를 넘긴다.
출력
    batch/ingest/data/products_200.json      상품 200개. 원본 27개 컬럼 + 파생 2개
    batch/ingest/data/excluded_products.json 리뷰 수로는 200위 안이지만 제외한 상품

실행
    SEPHORA_DATASET=/path/to/dataset/sephora python batch/ingest/build_products_json.py
    (약 25초)
"""
import ast, glob, json, os, re, sys

# 콘솔이 cp949 라 상품명의 ç 같은 문자에서 print 가 죽는다 (파일 저장은 이미 끝난 뒤라
# 결과물에는 영향이 없지만, 진단 출력이 통째로 날아가서 재현할 때 헷갈린다)
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import numpy as np
import pandas as pd

# ---- 경로 -------------------------------------------------------------------
# 원본 CSV 는 .gitignore 대상이라 레포에 없다. 개인 작업 폴더를 가리키게 하려면
#   SEPHORA_DATASET=C:\...\Research\dataset\sephora  로 넘긴다.
BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
BASE = os.environ.get("SEPHORA_DATASET", os.path.join(BD, "dataset", "sephora"))
OUT = os.path.join(BD, "data")
os.makedirs(OUT, exist_ok=True)

# ---- 상수 -------------------------------------------------------------------
# 우리가 쓰는 사용자 속성 4종. 리뷰에 이 4개가 "전부" 있어야 페르소나 재료가 된다.
UF = ["skin_type", "skin_tone", "eye_color", "hair_color"]

TOP_N = 200   # 최종 카탈로그 크기

# 스킨케어 단품이 아니라 벡터화가 부적절한 카테고리 -> 제외.
#   Mini Size        : 사이즈 변형 그 자체 (병합 대상이지 독립 상품이 아니다)
#   Wellness         : 먹는 보조제 등. 성분/concern 축이 얼굴 제품과 다른 세계다
#   Value & Gift Sets: 여러 제품 묶음. 하나의 콘텐츠 벡터로 표현할 수 없다
EXCLUDE_SECONDARY = {"Mini Size", "Wellness", "Value & Gift Sets"}

# 카테고리로는 걸러지지 않는 비(非)스킨케어 품목 (도구·소모품).
# 카테고리가 스킨케어인데 실물은 도구라서 눈으로 찾아 손으로 뺀 것이다.
EXCLUDE_PRODUCT_IDS = {
    "P173726": "Shiseido Facial Cotton - 화장솜. 전성분이 '100% Cotton'인 도구",
}

# CSV 에 "['a', 'b']" 같은 파이썬 리터럴 문자열로 저장된 컬럼 -> 진짜 리스트로 되살린다
LIST_COLS = ["ingredients", "highlights"]

# 사이즈가 달라도 동일한 제품 고유 정보 -> 대표 상품에 값이 없으면 형제에서 가져와도 된다.
# 반대로 price_usd / size / variation_value 는 사이즈마다 달라서 절대 넣으면 안 된다.
FALLBACK_COLS = ["ingredients", "highlights", "primary_category",
                 "secondary_category", "tertiary_category"]

# [리뷰 데이터용] 리뷰를 쓴 "사람" 의 피부톤을 13종 -> 5종으로 접는 표.
# 상품 속성이 아니다. product_info.csv 27개 컬럼에 skin_tone 은 없고,
# skin_type / skin_tone / eye_color / hair_color 4개는 전부 reviews_*.csv 의 컬럼이다
# (리뷰 작성자가 자기 프로필에 입력한 값).
# 접는 이유: 13종 그대로 두면 세그먼트당 표본이 부족해 affinity 통계의 분모가 안 나온다.
# 사용처는 아래 리뷰 로드 단계 한 줄뿐이다 -> r["skin_tone"] = r.skin_tone.map(TONE_BUCKET)
TONE_BUCKET = {"porcelain": "fair", "fair": "fair", "fairLight": "fair",
               "light": "light", "lightMedium": "light",
               "medium": "medium", "mediumTan": "medium", "olive": "medium",
               "tan": "tan", "deep": "deep", "rich": "deep", "dark": "deep", "ebony": "deep"}

# 상품명에서 "같은 제품인데 사이즈만 다름" 을 나타내는 군더더기를 지우는 패턴.
#   "Mini Protini Polypeptide Cream"  -> "Protini Polypeptide Cream"
#   "Protini Cream - 50 ml"           -> "Protini Cream"
# 이걸 지워야 두 이름이 같아지고 병합 후보가 된다.
SIZE_NOISE = re.compile(
    r"^\s*mini\s+|\s*(limited edition\s*)?jumbo\b|\bmini size\b|\brefill\b|"
    r"\bvalue (set|size)\b|\btravel size\b|\bdeluxe\b|\s*-\s*\d+\s*(oz|ml)\b", re.I)


def canon(name):
    """상품명을 비교 가능한 표준형(canonical form)으로 만든다.

    "The Mini Water Cream - 50 ml" -> "watercream"
    공백·기호·대소문자·관사·사이즈 표기를 전부 날려서, 표기만 다른 같은 제품이
    같은 문자열이 되게 한다. 이 문자열이 나중에 그룹 키가 된다.
    """
    n = SIZE_NOISE.sub(" ", str(name)).lower().strip()   # 사이즈 군더더기 제거 + 소문자
    n = re.sub(r"^(the|a|an)\s+", "", n)                  # 선행 관사 제거
    return re.sub(r"[^a-z0-9]+", "", n)                   # 영숫자만 남긴다


def parse_list(v):
    """CSV 에 문자열로 박제된 리스트를 진짜 리스트로 되살린다.

    ingredients / highlights 는 원본이 "['Water', 'Glycerin']" 같은 문자열이다.
    literal_eval 이 실패하면(형식이 깨진 행) 빈 리스트로 처리하고 넘어간다 —
    여기서 죽으면 8천개 중 한 행 때문에 전체가 멈춘다.
    """
    if pd.isna(v):
        return []
    try:
        return [str(x).strip() for x in ast.literal_eval(v) if str(x).strip()]
    except (ValueError, SyntaxError):
        return []


def clean(v):
    """NaN -> None, numpy 타입 -> 파이썬 기본형.

    pandas 가 돌려주는 np.int64 / np.float64 / np.bool_ 는 json.dump 가 못 쓴다.
    NaN 도 JSON 에 NaN 이라고 쓰여 표준 위반이 되므로 None(null) 으로 바꾼다.
    """
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    return v


# ============================================================================
# 1. 리뷰 로드 — 속성 4개가 전부 채워진 리뷰만 남긴다
# ============================================================================
parts = []
for path in sorted(glob.glob(os.path.join(BASE, "reviews_*.csv"))):
    # 필요한 컬럼만 읽는다. 리뷰 원문(review_text)까지 읽으면 메모리가 몇 GB로 뛴다.
    # low_memory=False: 컬럼 타입을 파일 전체를 보고 한 번에 정하게 한다
    # (기본값이면 청크마다 타입을 추론해 DtypeWarning 이 뜬다)
    d = pd.read_csv(path, usecols=["author_id", "product_id", "product_name", "brand_name", "rating"] + UF,
                    low_memory=False)
    # 4개 속성이 "전부" 있는 행만. 하나라도 비면 그 사람은 세그먼트를 특정할 수 없다.
    # notna().sum(axis=1) == 4 -> 4개 다 채워진 행
    parts.append(d[d[UF].notna().sum(axis=1) == 4])
r = pd.concat(parts, ignore_index=True)
del parts                                   # 5개 파일분 사본을 즉시 놓아준다 (메모리)

# "잘 모르겠음" 응답은 속성값이 아니라 무응답이다 -> 버린다
r = r[r.skin_tone != "notSureST"].copy()
r["skin_tone"] = r.skin_tone.map(TONE_BUCKET)                  # 13종 -> 5종으로 접기
r["eye_color"] = r.eye_color.replace({"Grey": "gray", "grey": "gray"})  # 영/미 표기 통일


# ============================================================================
# 2. 상품 그룹핑 — 사이즈 변형을 하나로 합친다
# ============================================================================
# 그룹 키 1단계: "브랜드|표준화된상품명".
# 브랜드를 앞에 붙이는 이유 — 서로 다른 브랜드가 "Vitamin C Serum" 같은
# 흔한 이름을 쓰기 때문에 이름만으로는 남의 제품과 붙어버린다.
r["canon"] = (r.brand_name.str.lower().str.replace(r"[^a-z0-9]", "", regex=True)
              + "|" + r.product_name.map(canon))

# 그룹 키 2단계: 이름이 달라도 "리뷰어 집합이 완전히 같으면" 같은 제품이다.
#
# 세포라는 사이즈 변형끼리 리뷰를 공유해서 보여준다. 그래서 30ml 와 50ml 의
# 리뷰어 명단이 글자 그대로 동일하다. 이름 표준화만으로는 못 잡는 경우
# ("Protini Polypeptide Cream" vs "Protini Moisturizer") 를 여기서 잡는다.
#
# frozenset 으로 만든 뒤 hash 를 키로 삼아 "같은 명단" 끼리 묶는다.
# (문자열 hash 는 실행마다 값이 달라지지만, 한 실행 안에서는 같은 집합이면
#  반드시 같은 값이라 그룹 분할 결과는 매번 동일하다)
pool = r.groupby("product_id").author_id.apply(lambda s: hash(frozenset(s)))
p2c = r.drop_duplicates("product_id").set_index("product_id").canon   # product_id -> canon

alias = {}                                  # 흡수될 canon -> 살아남을 canon
for _, pids in pool.groupby(pool).groups.items():   # 리뷰어 명단이 같은 product_id 묶음
    reps = sorted({p2c[p] for p in pids})           # 그 묶음에 등장하는 canon 들
    for c in reps[1:]:                              # 사전순 첫 번째를 대표로 정하고
        alias[c] = reps[0]                          # 나머지는 대표에 흡수시킨다
r["group"] = r.canon.replace(alias)         # 최종 그룹 키

# 그룹별 집계. 순위는 리뷰 수가 아니라 "고유 리뷰어 수" 로 매긴다.
# 한 사람이 여러 번 쓴 리뷰가 순위를 부풀리지 않게 하려는 것이다.
stats = r.groupby("group").agg(users=("author_id", "nunique"), reviews=("author_id", "size"),
                               avg_rating=("rating", "mean"))
ranked_groups = stats.sort_values("users", ascending=False)


# ============================================================================
# 3. 상위 그룹을 순회하며 카탈로그 레코드를 만든다
# ============================================================================
products = pd.read_csv(os.path.join(BASE, "product_info.csv"))
ALL_COLS = list(products.columns)           # 원본 27개 컬럼을 하나도 버리지 않는다
pinfo = products.set_index("product_id")    # product_id 로 바로 찾을 수 있게

out, missing, excluded = [], [], []
rank = 0
for gname, srow in ranked_groups.iterrows():
    if len(out) >= TOP_N:                   # 200개를 채웠으면 종료
        break

    # 이 그룹에 속한 product_id 들 (= 사이즈 변형 형제들)
    members = sorted(r.loc[r.group == gname, "product_id"].unique())
    # 그중 product_info.csv 에 메타가 있는 것만 쓸 수 있다
    known = [m for m in members if m in pinfo.index]
    if not known:
        missing.append(gname)               # 리뷰는 있는데 상품 메타가 없는 그룹
        continue

    # --- 대표 상품 고르기 ---------------------------------------------------
    # 정렬 키 (False < True, 음수라 큰 값이 앞) 이므로
    #   1순위: 이름이 "Mini " 로 시작하지 않는 것   (본품 우선)
    #   2순위: 리뷰가 가장 많은 것                  (대표성 확보)
    cnt = r[r.group == gname].groupby("product_id").size()
    ranked = sorted(known, key=lambda m: (str(pinfo.at[m, "product_name"]).startswith("Mini "),
                                          -int(cnt.get(m, 0))))
    rep = ranked[0]                         # 대표 product_id
    row = pinfo.loc[rep]                    # 대표의 메타 한 줄

    # --- 제외 판정 -----------------------------------------------------------
    # 여기서 걸리면 rank 를 올리지 않고 건너뛴다 = 다음 그룹이 그 자리를 차지한다.
    # 그래서 최종 200개는 "리뷰어 수 상위 204개 중 4개를 뺀 것" 이 된다.
    if row["secondary_category"] in EXCLUDE_SECONDARY or rep in EXCLUDE_PRODUCT_IDS:
        excluded.append({"product_id": rep, "product_name": row["product_name"],
                         "brand_name": row["brand_name"],
                         "secondary_category": row["secondary_category"],
                         "unique_reviewers": int(srow.users),
                         "reason": EXCLUDE_PRODUCT_IDS.get(
                             rep, f"secondary_category={row['secondary_category']}")})
        continue

    rank += 1
    rec = {"rank": rank, "product_id": rep}
    filled_from = {}                        # 어떤 필드를 어느 형제에서 가져왔는지 기록

    # --- 원본 27개 컬럼을 그대로 복사 (필요하면 형제에서 보완) ----------------
    for c in ALL_COLS:
        if c == "product_id":               # 이미 rec 에 넣었다
            continue
        val = parse_list(row[c]) if c in LIST_COLS else clean(row[c])

        # 대표에 값이 없으면 병합된 형제(같은 제품의 다른 사이즈)에서 보완.
        # size/price/variation 등 사이즈마다 다른 값은 FALLBACK_COLS 에 없어서 제외된다.
        if c in FALLBACK_COLS and val in (None, []):
            for sib in ranked[1:]:          # 대표 다음 순위부터 훑는다
                alt = parse_list(pinfo.at[sib, c]) if c in LIST_COLS else clean(pinfo.at[sib, c])
                if alt not in (None, []):
                    val, filled_from[c] = alt, sib
                    break                   # 처음 찾은 값을 쓰고 멈춘다
        rec[c] = val

    # tertiary_category 결측 시 secondary_category 로 대체.
    # 립 제품처럼 세포라가 2단계까지만 분류하는 카테고리가 있다.
    # 비워 두면 어휘집의 tertiary 원핫이 영벡터가 되어 그 상품만 손해를 본다.
    if not rec.get("tertiary_category"):
        rec["tertiary_category"] = rec.get("secondary_category")
        filled_from["tertiary_category"] = "secondary_category"

    # --- 파생 필드 1: 병합 이력 (_merged) ------------------------------------
    # 나중에 "이 상품은 몇 개가 합쳐진 것인가" 를 추적할 수 있어야 한다.
    sub = r[r.group == gname]
    rec["_merged"] = {
        "group_key": gname,                          # 그룹 키 (= 다른 산출물의 group_id)
        "member_product_ids": members,               # 합쳐진 원본 product_id 전부
        "member_count": len(members),
        "merged": len(members) > 1,                  # 실제로 합쳐졌는가
        "filled_from_sibling": filled_from or None,  # 형제에서 채운 필드 (없으면 None)
    }

    # --- 파생 필드 2: 리뷰 통계 (_review_stats) -------------------------------
    # segment_counts 가 핵심이다. "이 상품 리뷰어 중 지성 피부가 몇 명인가" 를
    # 담고 있어서, build_affinity_lift.py 가 이걸로 속성별 affinity 를 만든다.
    rec["_review_stats"] = {
        "unique_reviewers": int(srow.users),
        "review_count": int(srow.reviews),
        "avg_rating": round(float(srow.avg_rating), 3),
        "segment_counts": {a: sub[a].value_counts().to_dict() for a in UF},
    }
    out.append(rec)


# ============================================================================
# 4. 저장 + 진단 출력
# ============================================================================
path = os.path.join(OUT, "products_200.json")
# ensure_ascii=False: 한글·악센트 문자를 \uXXXX 로 뭉개지 않고 그대로 저장
json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

json.dump(excluded, open(os.path.join(OUT, "excluded_products.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)

print(f"저장: {path}  ({len(out)}개, {os.path.getsize(path)/1024:.0f}KB)")

# 제외된 상품 — 어떤 상품이 왜 빠졌는지 눈으로 확인할 수 있어야 한다
print(f"카테고리 사유로 제외: {len(excluded)}개")
for e in excluded:
    print(f"   {e['product_name'][:40]:<40} | 리뷰어 {e['unique_reviewers']:>6,} | {e['reason'][:46]}")

# 200위의 리뷰어 수 — 이 값이 너무 작으면 카탈로그 꼬리가 통계적으로 부실하다는 뜻
print(f"200위 리뷰어 하한: {out[-1]['_review_stats']['unique_reviewers']:,}")
print(f"product_info 원본 컬럼 {len(ALL_COLS)}개 전부 포함")

if missing:
    print(f"⚠ product_info에 없어 제외된 그룹: {len(missing)}")

# 병합이 실제로 일어났는지 확인 — 이 숫자가 0이면 사이즈 병합 로직이 죽은 것이다
merged = [x for x in out if x["_merged"]["merged"]]
print(f"병합된 그룹: {len(merged)} / 총 포함 product_id: {sum(x['_merged']['member_count'] for x in out)}")

# 형제에서 필드를 빌려온 상품 목록 — 데이터 출처를 속이지 않으려고 전부 찍는다
filled = [x for x in out if x["_merged"]["filled_from_sibling"]]
print(f"형제 상품에서 필드 보완된 그룹: {len(filled)}")
for x in filled:
    print(f"  {x['rank']:>3}위 {x['product_name'][:40]:<40} <- {x['_merged']['filled_from_sibling']}")

# 남은 결측 — 어휘집을 만들 때 어느 블록이 빌지 여기서 미리 보인다
# (예: highlights 가 비면 concern 블록이 영벡터가 된다)
nulls = {c: sum(1 for x in out if x.get(c) in (None, [])) for c in ALL_COLS if c != "product_id"}
print("\n[상위 200개 내 결측/빈값 필드]")
for c, n in sorted(nulls.items(), key=lambda kv: -kv[1]):
    if n:
        print(f"  {c:<22} {n:>3}/200")
