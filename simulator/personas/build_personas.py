# -*- coding: utf-8 -*-
"""
페르소나 10,000명 층화추출 — artifacts/personas_9900.json · personas_100_agent.json
================================================================================

무엇을 하는가
    세포라 리뷰어 중에서 "우리 상품 200개를 실제로 써본 사람" 10,000명을 뽑아,
    각자의 구매 이력(리뷰)을 통째로 들고 있는 페르소나 레코드로 만든다.

왜 리뷰어에서 뽑는가
    사용자를 새로 지어내면 그 사람의 취향과 상품 사이에 아무 관계가 없다.
    리뷰어를 쓰면 "이 사람이 실제로 무엇을 샀는가" 가 그대로 정답이 되어,
    추천 정확도를 측정할 수 있다. 리뷰 이력 = 구매 이력으로 취급한다.

왜 층화추출인가
    무작위로 10,000명을 뽑으면 소수 세그먼트(deep 톤 2.3%)가 표본에서
    사라지거나 심하게 흔들린다. 층을 나눠 비례배분하면 모집단 분포가 보존된다.
    실제로 모든 층에서 차이가 ±0.03%p 안에 들어온다.

두 집단으로 나눠 저장한다
    PC00001~PC09900  코드 생성 — 시뮬레이터가 합성 행동 로그를 만드는 대상
    PA00001~PA00100  인터랙티브 — 프론트 드롭다운 + LLM 에이전트가 직접 조종
                     skin_type x skin_tone 20칸에서 5명씩 **균등** 추출한다.
                     어떤 조합을 골라도 시연이 되도록 하려는 것이다.
                     (시뮬레이터는 이 100명에게 로그를 쏘지 않는다.
                      합성 로그가 미리 쌓이면 사람의 클릭이 묻힌다)

입력
    <SEPHORA_DATASET>/reviews_*.csv          리뷰 원본 5개 파일 (.gitignore 대상)
    batch/ingest/data/products_200.json      상품 200개 — member_product_ids 로 리뷰를 조인
출력
    simulator/personas/data/personas_9900.json           PC 9,900명
    simulator/personas/data/personas_100_agent.json      PA 100명
    simulator/personas/data/persona_sampling_report.json 모집단 대비 표본 분포 검증

실행
    SEPHORA_DATASET=/path/to/dataset/sephora python simulator/personas/build_personas.py
    (약 20초)

    페르소나가 바뀌면 성향 파일도 다시 만들어야 한다 — 리뷰에서 파생되기 때문이다.
    python simulator/generator/build_persona_style.py
"""
import argparse, glob, json, os
from datetime import datetime, timezone
import numpy as np
import pandas as pd

# 홀드아웃 모드 — 페르소나로 이미 쓴 사람을 빼고 남은 인원에서만 뽑는다.
#   why: test 는 한 번 쓰면 소진되는 자원이라 반복 측정하면 낙관 편향이 붙는다.
#        풀에는 아직 쓰지 않은 사람이 1만 명 넘게 남아 있고 층화 표본이라
#        분포가 같다. 독립 홀드아웃을 여러 개 떼어 하나씩 소진한다.
#   기본 실행(플래그 없음)은 한 글자도 달라지지 않는다.
_ap = argparse.ArgumentParser()
_ap.add_argument("--holdout", type=int, default=0,
                 help="이 인원만큼 미사용 인원에서 홀드아웃을 뽑는다")
_ap.add_argument("--seed", type=int, default=None, help="홀드아웃용 난수 시드")
_ap.add_argument("--tag", default="a", help="홀드아웃 이름 꼬리표 (파일명·prefix)")
_ap.add_argument("--exclude", default="",
                 help="추가로 뺄 author_id 파일 (한 줄에 하나)")
_A = _ap.parse_args()
HOLDOUT = _A.holdout

# 원본 CSV 는 .gitignore 대상이라 레포에 없다. 위치는 환경변수로 넘긴다.
#   SEPHORA_DATASET=C:\...\Research\dataset\sephora
BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
BASE = os.environ.get("SEPHORA_DATASET", os.path.join(BD, "dataset", "sephora"))
ART = os.path.join(BD, "data")                       # 페르소나 산출물
CATALOG = os.path.join(ROOT, "batch", "ingest", "data")   # 상품 200개는 배치 쪽에 있다
os.makedirs(ART, exist_ok=True)

# 사용자 속성 4종. 리뷰에 이 4개가 "전부" 있어야 세그먼트를 특정할 수 있다.
UF = ["skin_type", "skin_tone", "eye_color", "hair_color"]

SEED = 42                      # 재현을 위해 난수를 고정한다
if _A.seed is not None:
    SEED = _A.seed             # 홀드아웃마다 다른 사람이 뽑혀야 한다
N_TOTAL, N_AGENT = 10000, 100  # 전체 1만 = 코드 9,900 + 에이전트 100

# 계약 `contracts/persona-schema.md` §4 가 요구하는 생성·정규화 버전.
# 표본 추출 규칙(SEED·MIN_POSITIVE·극성 기준·TONE_BUCKET)이나 속성 정규화가
# 바뀌면 올린다. 산출물이 어느 규칙으로 만들어졌는지 파일만 보고 알 수 있어야 한다.
PROFILE_VERSION = "persona-v1"

# 표본 구분. 계약 §2.1 이 "분석에서 prefix 를 파싱하지 말고 persona_source 를
# 쓰라" 고 정해서, PC/PA 접두사와 별개로 필드에 적어 둔다.
PERSONA_SOURCE = {"PC": "batch_sample", "PA": "agent_sample"}
# 홀드아웃은 아직 계약(`persona-schema.md` §2.1 · §11)에 없는 대역이다.
# 계약은 persona_source 를 {batch_sample, agent_sample} 로 하드 검증하므로
# 이 산출물은 **측정용이고 계약 테이블로 평탄화하지 않는다.**
# 정식화하려면 데이터 파트가 enum 과 ID 대역을 열어 주어야 한다.
PERSONA_SOURCE["PH"] = "holdout_sample"

# 생성 시각. 한 번의 실행 안에서는 전원이 같은 값을 갖는다 — 사람마다 초가 달라지면
# 같은 배치로 만든 것을 나중에 알아볼 수 없다. 재생성하면 이 값은 바뀐다.
BUILT_AT = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

# 긍정(4~5점) 상품 최소 개수. 시드 1 + 좋아요 1 + 정답 1 을 채우기 위한 값.
# 이 하한이 없으면 "리뷰 1건짜리" 사용자가 대량으로 들어와 평가 케이스가 성립하지 않는다.
MIN_POSITIVE = 3

# 평점 -> 극성. 4~5점=긍정 / 3점=중립(버림) / 1~2점=부정
# 3점을 버리는 이유: "그럭저럭" 을 좋아함으로도 싫어함으로도 읽을 수 없다.
POS_MIN, NEG_MAX = 4, 2

# 리뷰어의 피부톤 13종 -> 5버킷. 세그먼트당 표본을 확보하기 위해 접는다.
TONE_BUCKET = {"porcelain": "fair", "fair": "fair", "fairLight": "fair",
               "light": "light", "lightMedium": "light",
               "medium": "medium", "mediumTan": "medium", "olive": "medium",
               "tan": "tan", "deep": "deep", "rich": "deep", "dark": "deep", "ebony": "deep"}

# 난수 생성기. 이 하나를 스크립트 전체가 공유하므로 **호출 순서가 바뀌면 결과가 바뀐다.**
# 층 순회 순서나 셀 순회 순서를 건드리면 표본이 통째로 달라진다.
rng = np.random.default_rng(SEED)


def bucket_reviews(n):
    """긍정 상품 개수를 4구간으로 나눈다. 층화의 세 번째 축이다.

    행동 이력이 3개인 사람과 20개인 사람은 추천 난이도가 완전히 다르다.
    구간을 나눠 비례배분해야 "이력이 많은 사람만 잔뜩 뽑혀서 정확도가 좋아 보이는"
    일이 생기지 않는다.

    하한이 MIN_POSITIVE=3 이므로 그 아래 구간은 존재하지 않는다.
    """
    if n <= 3:
        return "3"
    if n == 4:
        return "4"
    if n <= 6:
        return "5-6"
    return "7+"


# ============================================================================
# 1. 상품 200개 -> product_id 매핑
# ============================================================================
# 리뷰의 product_id 는 사이즈 변형별로 다르다(262종). 우리 카탈로그는 병합 후
# 대표 ID 200종이다. 그래서 원본 ID -> 대표 ID 사전을 먼저 만든다.
# 이걸 안 하면 50ml 리뷰가 카탈로그에 없는 상품으로 취급되어 통째로 버려진다.
prods = json.load(open(os.path.join(CATALOG, "products_200.json"), encoding="utf-8"))
pid2group, group_meta = {}, {}
for p in prods:
    for m in p["_merged"]["member_product_ids"]:   # 형제 전부를 대표에 매핑
        pid2group[m] = p["product_id"]
    group_meta[p["product_id"]] = {"rank": p["rank"]}
print(f"상품 200그룹 / product_id {len(pid2group)}개")


# ============================================================================
# 2. 리뷰 로드
# ============================================================================
# 상품 카탈로그 때와 달리 리뷰 본문(review_text)까지 읽는다.
# 페르소나 레코드에 리뷰를 통째로 넣어야 나중에 LLM 에이전트가 "이 사람이
# 어떤 말투로 무엇을 중시하는지" 를 읽을 수 있다.
RCOLS = ["Unnamed: 0", "author_id", "product_id", "product_name", "brand_name", "rating",
         "is_recommended", "review_title", "review_text", "submission_time",
         "helpfulness", "total_feedback_count", "total_pos_feedback_count",
         "total_neg_feedback_count"]
parts = []
for path in sorted(glob.glob(os.path.join(BASE, "reviews_*.csv"))):
    d = pd.read_csv(path, usecols=RCOLS + UF, low_memory=False)
    d = d[d[UF].notna().sum(axis=1) == 4].copy()   # 속성 4개가 전부 채워진 행만
    # 리뷰 고유 ID 를 만든다. 원본에 리뷰 ID 컬럼이 없고 "Unnamed: 0"(행 번호)만
    # 있는데, 파일마다 0부터 다시 시작해서 그대로 쓰면 충돌한다.
    # 파일 태그를 붙여 "RV-0-250-000042" 형태로 전역 유일하게 만든다.
    tag = os.path.basename(path).replace("reviews_", "").replace(".csv", "")
    d["review_id"] = "RV-" + tag + "-" + d["Unnamed: 0"].astype(str).str.zfill(6)
    parts.append(d)
r = pd.concat(parts, ignore_index=True)
del parts                                          # 5개 파일분 사본을 즉시 놓아준다

r = r[r.skin_tone != "notSureST"].copy()           # "잘 모르겠음" 은 값이 아니다
r["skin_tone_raw"] = r.skin_tone                   # 원본 13종 값을 보존해 둔다
r["skin_tone"] = r.skin_tone.map(TONE_BUCKET)      # 13종 -> 5버킷
r["eye_color"] = r.eye_color.replace({"Grey": "gray", "grey": "gray"})   # 영/미 표기 통일

# brunette는 brown의 표기 변형(수집 배치별 라벨 차이). 상품 200개 중 99개는 0%인데
# 4개 상품에서 40%를 넘고 그 상품의 brown은 0.6~10%로 붕괴 -> 동일 범주로 병합
r["hair_color"] = r.hair_color.replace({"brunette": "brown"})

r["group_id"] = r.product_id.map(pid2group)        # 원본 ID -> 대표 ID
r = r[r.group_id.notna()]                          # 카탈로그 200개 밖 상품 리뷰는 버린다
print(f"상위 200개 상품 리뷰: {len(r):,}건 / 사용자 {r.author_id.nunique():,}")


# ============================================================================
# 3. 페르소나 풀 — 누가 후보가 될 수 있는가
# ============================================================================
# (사용자, 상품) 단위로 축약해 긍정/부정을 판정한다.
# 같은 상품에 리뷰를 여러 번 쓴 경우가 59%라 평점 평균으로 하나로 합친다.
# 합치지 않으면 한 사람이 같은 상품에 5점을 세 번 준 것이 "긍정 상품 3개" 가 된다.
pu = r.groupby(["author_id", "group_id"], as_index=False).rating.mean()

# 평균이라 3.5 같은 값이 나온다. 경계를 0.5 옮겨 "4점 이상 = 긍정" 을 만든다.
#   rating >= 3.5 -> pos   (POS_MIN 4 - 0.5)
#   rating <= 2.5 -> neg   (NEG_MAX 2 + 0.5)
#   그 사이        -> neutral (버림)
pu["polarity"] = np.where(pu.rating >= POS_MIN - 0.5, "pos",
                  np.where(pu.rating <= NEG_MAX + 0.5, "neg", "neutral"))

# 사용자 x 극성 교차표 -> 한 사람의 긍정/중립/부정 상품이 각각 몇 개인가
cnt = pu.pivot_table(index="author_id", columns="polarity", aggfunc="size", fill_value=0)
for c in ("pos", "neg", "neutral"):
    if c not in cnt: cnt[c] = 0                    # 그 극성이 하나도 없으면 컬럼이 안 생긴다

pool_ids = cnt[cnt.pos >= MIN_POSITIVE].index      # 긍정 상품 3개 이상인 사람만 후보
pool = r[r.author_id.isin(pool_ids)]
print(f"(사용자,상품) 쌍 {len(pu):,} - 긍정 {int((pu.polarity=='pos').sum()):,} / "
      f"중립 {int((pu.polarity=='neutral').sum()):,} / 부정 {int((pu.polarity=='neg').sum()):,}")
print(f"페르소나 풀 (긍정 상품 {MIN_POSITIVE}개 이상): {len(pool_ids):,}명 / 리뷰 {len(pool):,}건")
print(f"  그중 부정 상품 보유: {int((cnt.loc[pool_ids].neg >= 1).sum()):,}명 "
      f"({(cnt.loc[pool_ids].neg >= 1).mean()*100:.1f}%)")


# ============================================================================
# 4. 사용자 속성 확정 — 리뷰마다 값이 다를 수 있다
# ============================================================================
# 세포라는 리뷰를 쓸 때마다 프로필 속성을 다시 받는다. 그래서 같은 author_id 인데
# 리뷰A는 dry, 리뷰B는 combination 인 경우가 생긴다(13.4%).
#
# '가장 최신 리뷰' 의 값을 채택한다. 피부는 계절·나이에 따라 실제로 변하므로
# 최빈값보다 최신값이 "지금 이 사람" 에 가깝다고 본다.
#
# submission_time 오름차순 정렬 후 마지막 값 = 최신.
# 같은 날짜가 여러 건이면 review_id 순으로 결정 (재현 가능하도록)
pool_sorted = pool.sort_values(["author_id", "submission_time", "review_id"])
attrs = pool_sorted.groupby("author_id")[UF].last()

# 이 선택이 얼마나 영향을 주는지 기록해 둔다. 리포트에 남겨 나중에 재검토할 근거로 쓴다.
nuniq = pool.groupby("author_id")[UF].nunique()
incons = int((nuniq > 1).any(axis=1).sum())                    # 값이 흔들리는 사람 수
mode_attrs = pool.groupby("author_id")[UF].agg(lambda x: x.value_counts().index[0])
diff_vs_mode = int((attrs != mode_attrs).any(axis=1).sum())    # 최빈값과 결과가 갈리는 사람 수
print(f"속성이 리뷰마다 다른 사용자: {incons:,}명 ({incons/len(pool_ids)*100:.2f}%) -> 최신 리뷰 값 사용")
print(f"  그중 최빈값과 결과가 달라지는 사용자: {diff_vs_mode:,}명")
for c in UF:
    d = int((attrs[c] != mode_attrs[c]).sum())
    print(f"    {c:<11} {d:>5}명")

# --- 사용자 단위 요약 테이블 만들기 ------------------------------------------
users = attrs.copy()
users["n_reviews"] = pool.groupby("author_id").size()               # 리뷰 건수
users["n_products"] = pool.groupby("author_id").group_id.nunique()  # 고유 상품 수
users["avg_rating"] = pool.groupby("author_id").rating.mean().round(3)
users["n_positive"] = cnt.loc[users.index, "pos"]
users["n_negative"] = cnt.loc[users.index, "neg"]
users["n_neutral"] = cnt.loc[users.index, "neutral"]

# 층화의 세 번째 축은 리뷰 건수가 아니라 **긍정 상품 수** 다.
# 시드/정답으로 쓸 수 있는 재료의 개수가 곧 난이도이기 때문이다.
users["review_bucket"] = users.n_positive.map(bucket_reviews)

# 층 = 세 축의 조합. 4 x 5 x 4 = 최대 80개
users["stratum"] = users.skin_type + "|" + users.skin_tone + "|" + users.review_bucket


# ============================================================================
# 5. 비례 배분 (최대잔여법)
# ============================================================================
# 각 층에서 몇 명을 뽑을지 정한다. 층 크기에 비례하되 정수여야 한다.
#   raw   = 소수점이 있는 이상적 배정량 (예: 1234.7명)
#   alloc = 일단 내림 (1234명) -> 합계가 10,000 에 못 미친다
#   rem   = 버린 소수부 (0.7)
# 소수부가 큰 층부터 1명씩 더 주며 10,000을 채운다. 이것이 최대잔여법이다.
# --- 홀드아웃: 이미 페르소나로 쓴 사람을 모집단에서 뺀다 -------------------
# 여기서 빼야 층 비율이 **남은 인원 기준**으로 다시 잡힌다. 뽑고 나서 거르면
# 층화가 깨진다.
if HOLDOUT:
    used = set()
    for fn in ("personas_9900.json", "personas_100_agent.json"):
        fp = os.path.join(ART, fn)
        if os.path.exists(fp):
            used |= {r["author_id"] for r in json.load(open(fp, encoding="utf-8"))
                     if r.get("author_id")}
    extra = set()
    if _A.exclude and os.path.exists(_A.exclude):
        extra = {ln.strip() for ln in open(_A.exclude, encoding="utf-8") if ln.strip()}
    before = len(users)
    drop = {a for a in users.index if str(a) in used or str(a) in extra}
    users = users.drop(index=list(drop))
    N_TOTAL = HOLDOUT
    N_AGENT = 0                      # 홀드아웃은 에이전트 대역을 만들지 않는다
    print("")
    print(f"[홀드아웃] 모집단 {before:,} - 사용 {len(used):,} - 추가제외 "
          f"{len(extra):,} -> 후보 {len(users):,}명 / {N_TOTAL:,}명 추출 (seed {SEED})")
    if len(users) < N_TOTAL:
        raise SystemExit(f"후보 {len(users):,}명 < 요청 {N_TOTAL:,}명")

sizes = users.stratum.value_counts()
raw = sizes / sizes.sum() * N_TOTAL

# clip(upper=sizes): 층에 있는 사람보다 많이 뽑을 수 없다.
# 소규모 층에서 배정량이 모집단을 넘는 것을 막는다.
alloc = np.floor(raw).astype(int).clip(upper=sizes)
rem = raw - alloc
while alloc.sum() < N_TOTAL:
    room = rem[(sizes - alloc) > 0]      # 아직 더 뽑을 사람이 남은 층만 후보
    if room.empty:
        break                            # 전부 소진 — 10,000을 못 채우고 끝난다
    k = room.idxmax()                    # 소수부가 가장 큰 층
    alloc[k] += 1
    rem[k] -= 1                          # 한 번 받았으면 우선순위를 낮춘다
print(f"\n층 개수: {len(sizes)} / 배정 합계: {alloc.sum():,}")

# 층 전체를 다 뽑아버린 소규모 층 경고 — 그 층은 표본이 아니라 전수라
# 다양성이 없고, 같은 사람이 반복 등장하는 것과 같은 효과가 난다.
short = [(s, int(sizes[s]), int(alloc[s])) for s in sizes.index
         if alloc[s] >= sizes[s] and sizes[s] < 40]
if short:
    print(f"  [주의] 층 전체를 뽑은 소규모 층 {len(short)}개")
    for s, n, a in short[:10]:
        print(f"     {s:<26} 모집단 {n:>3} -> {a}")

# --- 실제 추출 ---------------------------------------------------------------
# sizes(=value_counts) 의 순서대로 층을 돈다. **이 순서가 난수 소비 순서를 정하므로
# 순서가 바뀌면 표본 전체가 달라진다.** 재현성이 여기에 걸려 있다.
picked = []
for s, n in alloc.items():
    if n <= 0:
        continue
    ids = users.index[users.stratum == s].to_numpy()
    picked.extend(rng.choice(ids, size=int(n), replace=False))   # 비복원 추출
sample = users.loc[picked].copy()
print(f"표본: {len(sample):,}명")


# ============================================================================
# 6. 에이전트 100명 — skin_type x skin_tone 균등
# ============================================================================
# PC 9,900 과 달리 PA 100 은 **비례배분이 아니라 균등배분**이다.
# 비례로 뽑으면 deep 톤이 2~3명뿐이라 드롭다운에서 고를 수가 없다.
# 20칸(4 x 5)에서 5명씩 뽑아 어떤 조합을 골라도 시연이 되게 한다.
cells = [(t, c) for t in sorted(users.skin_type.unique())
         for c in sorted(users.skin_tone.unique())]
per_cell = N_AGENT // len(cells)          # 100 / 20 = 5명
agent_ids, thin = [], []
for t, c in cells:
    # 이미 뽑힌 10,000명(sample) 안에서 고른다. 모집단에서 새로 뽑는 게 아니다.
    ids = sample.index[(sample.skin_type == t) & (sample.skin_tone == c)].to_numpy()
    take = min(per_cell, len(ids))        # 그 칸에 5명이 없으면 있는 만큼만
    if take:
        agent_ids.extend(rng.choice(ids, size=take, replace=False))
    if take < per_cell:
        thin.append((f"{t}|{c}", int(len(ids))))

# 빈 칸 때문에 100명이 안 되면 나머지에서 무작위로 채운다.
# 이 경우 균등이 완벽하지 않게 되므로 thin 경고를 함께 남긴다.
if len(agent_ids) < N_AGENT:
    rest = sample.index.difference(pd.Index(agent_ids)).to_numpy()
    agent_ids.extend(rng.choice(rest, size=N_AGENT - len(agent_ids), replace=False))
agent_set = set(agent_ids)
print(f"에이전트 {len(agent_set)}명 / 코드 {len(sample) - len(agent_set):,}명")
if thin:
    print(f"  [주의] {per_cell}명 미만인 셀: {thin}")


# ============================================================================
# 7. JSON 출력
# ============================================================================
# 페르소나 레코드에 넣을 리뷰 컬럼. 원본 필드 + 우리가 만든 review_id / group_id /
# skin_tone_raw 를 포함한다. skin_tone_raw 를 남기는 이유는 5버킷으로 접기 전
# 원래 값(예: olive)을 나중에 되살릴 수 있게 하려는 것이다.
REV_COLS = ["review_id", "product_id", "group_id", "product_name", "brand_name", "rating",
            "is_recommended", "review_title", "review_text", "submission_time",
            "helpfulness", "total_feedback_count", "total_pos_feedback_count",
            "total_neg_feedback_count"] + UF + ["skin_tone_raw"]


def clean(c, v):
    """pandas 값을 JSON 에 넣을 수 있는 형태로 바꾼다.

    build_products_json.py 의 clean() 과 같은 문제를 다룬다 —
    np.int64 / np.float64 는 json.dump 가 못 쓰고, NaN 은 JSON 표준에 없다.

    is_recommended 만 특별 취급하는 이유: 원본이 0.0/1.0 실수라
    그대로 두면 JSON 에 1.0 으로 찍힌다. 의미상 불리언이므로 변환한다.
    """
    if pd.isna(v):
        return None
    if c == "is_recommended":
        return bool(v)
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.floating):
        return float(v)
    return v


def to_records(ids, prefix):
    """author_id 목록 -> 페르소나 레코드 목록.

    필드 구성은 `contracts/persona-schema.md` §4 `persona_profile` 을 따른다.
    이 파일은 중첩 JSON(사람 1명 + reviews 배열)이고 계약은 grain 별 평탄
    테이블이라, 평탄화·적재는 데이터 파트가 이 산출물을 입력으로 받아서 한다.

    prefix 가 "PC" 면 PC00001, "PA" 면 PA00001 부터 번호를 매긴다.
    persona_id 는 **파일 안에서의 순번**이라 author_id 와 무관하다.
    두 파일의 번호가 겹치지 않는 이유는 접두사가 다르기 때문이다.
    """
    # 한 번에 groupby 해두고 사전으로 꺼내 쓴다.
    # 사람마다 pool[pool.author_id == a] 로 필터링하면 9,900번 전체 스캔이라 훨씬 느리다.
    by = {a: g for a, g in pool[pool.author_id.isin(set(ids))].groupby("author_id")}
    out = []
    for i, a in enumerate(ids, 1):
        u = sample.loc[a]
        revs = []
        # 시간순으로 정렬한다. 평가에서 "마지막 1개를 정답으로" 쓰려면
        # 이 순서가 곧 구매 순서여야 한다.
        for _, x in by[a].sort_values("submission_time").iterrows():
            rec = {c: clean(c, x[c]) for c in REV_COLS}
            rec["product_rank"] = group_meta[x.group_id]["rank"]   # 인기 순위(가독성용)
            revs.append(rec)
        pid = f"{prefix}{i:05d}"
        out.append({
            "persona_id": pid,
            "author_id": str(a),                  # 원본 추적용. 조인 키가 아니다
            # 계약 §4 가 요구하는 식별·버전 필드. 값을 새로 계산하는 게 아니라
            # "이 레코드가 무엇인지" 를 적는 자리다.
            "user_id": pid,                       # Synthetic 분석 ID. 기본값이 persona_id
            "persona_source": PERSONA_SOURCE[prefix],
            "profile_version": PROFILE_VERSION,
            "profile_scope": "full",              # seed 만 쓰는 eval Profile 은 §5 로 따로 낸다
            "created_at": BUILT_AT,
            "updated_at": BUILT_AT,
            "skin_type": u.skin_type, "skin_tone": u.skin_tone,
            "eye_color": u.eye_color, "hair_color": u.hair_color,
            "stratum": u.stratum, "review_bucket": u.review_bucket,
            "n_reviews": int(u.n_reviews), "n_products": int(u.n_products),
            "n_positive": int(u.n_positive), "n_negative": int(u.n_negative),
            "n_neutral": int(u.n_neutral),
            "avg_rating": float(u.avg_rating),
            "reviews": revs,                      # 구매 이력 전체
        })
    return out


# sample.index 순서를 그대로 따른다 — 층 순회 순서가 그대로 persona_id 순서가 된다
code_ids = [a for a in sample.index if a not in agent_set]
agent_list = [a for a in sample.index if a in agent_set]
OUTPUTS = ([(f"personas_holdout_{_A.tag}.json", code_ids, "PH")] if HOLDOUT
           else [("personas_9900.json", code_ids, "PC"),
                 ("personas_100_agent.json", agent_list, "PA")])
for fn, ids, pf in OUTPUTS:
    recs = to_records(ids, pf)
    p = os.path.join(ART, fn)
    # indent=1 — 사람이 읽을 수 있으면서 파일 크기를 억제하는 절충값 (indent=2 면 약 10% 커진다)
    json.dump(recs, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n저장: {fn}  {len(recs):,}명  {os.path.getsize(p)/1024/1024:.1f}MB  "
          f"리뷰 {sum(len(x['reviews']) for x in recs):,}건")


# ============================================================================
# 8. 분포 검증 — 층화가 실제로 먹혔는지 확인한다
# ============================================================================
# 모집단(users)과 표본(sample)의 분포를 축별로 비교한다.
# 차이가 크면 층화가 깨졌다는 뜻이라 여기서 잡아야 한다. 실측 ±0.03%p 이내.
print("\n[모집단 vs 표본 분포]")
rows = []
for col in ["skin_type", "skin_tone", "review_bucket"]:
    a = users[col].value_counts(normalize=True) * 100
    b = sample[col].value_counts(normalize=True) * 100
    print(f"\n  {col}")
    for k in a.index:
        print(f"    {k:<12} 모집단 {a[k]:5.2f}%  표본 {b.get(k, 0):5.2f}%  "
              f"차이 {b.get(k, 0) - a[k]:+.2f}%p")
        rows.append({"field": col, "value": k,
                     "population_pct": round(float(a[k]), 3),
                     "sample_pct": round(float(b.get(k, 0)), 3)})

# 층화 축이 아닌 값들도 같이 본다. 이쪽이 안 흔들려야 표본이 진짜로 대표성이 있다.
print(f"\n  평균 평점 모집단 {users.avg_rating.mean():.3f} / 표본 {sample.avg_rating.mean():.3f}")
print(f"  리뷰 수   모집단 {users.n_reviews.mean():.2f} / 표본 {sample.n_reviews.mean():.2f}")
print(f"  상품 수   모집단 {users.n_products.mean():.2f} / 표본 {sample.n_products.mean():.2f}")

# 재현·검토에 필요한 파라미터를 전부 리포트로 남긴다.
# 나중에 "이 페르소나는 어떤 기준으로 뽑혔나" 를 이 파일 하나로 답할 수 있어야 한다.
json.dump({"seed": SEED, "n_total": int(len(sample)), "n_agent": len(agent_set),
           "n_code": len(code_ids), "pool_size": int(len(pool_ids)),
           "min_positive": MIN_POSITIVE, "polarity_cut": {"pos_min": POS_MIN, "neg_max": NEG_MAX}, "n_strata": int(len(sizes)),
           "inconsistent_attr_users": incons,
           "attr_rule": "latest_review",
           "differs_from_mode": diff_vs_mode, "distribution": rows,
           "population_avg_rating": round(float(users.avg_rating.mean()), 4),
           "sample_avg_rating": round(float(sample.avg_rating.mean()), 4),
           "population_avg_reviews": round(float(users.n_reviews.mean()), 4),
           "sample_avg_reviews": round(float(sample.n_reviews.mean()), 4)},
          open(os.path.join(ART, f"holdout_{_A.tag}_sampling_report.json" if HOLDOUT
                            else "persona_sampling_report.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
