# -*- coding: utf-8 -*-
"""상품 등록 폼의 한국어 라벨 — 어휘집 값에 화면 문구를 붙인다.

왜 파일로 두나
    브랜드가 자기 상품을 등록할 때 영어 목록을 보고 고를 수는 없다. 화면은
    한국어로 보여주고 **서버로 보내는 값은 어휘집 문자열 그대로** 보낸다.

    라벨을 프론트에 하드코딩하면 어휘집이 바뀔 때 조용히 갈라진다. 값 한 글자가
    달라지면 그 상품의 해당 차원이 통째로 0 이 되는데, 화면에는 아무 표시도 나지
    않는다. 그래서 **어휘집에서 값을 읽어** 이 파일을 만들고 프론트가 그대로 쓴다.

    한국어 문구는 사람이 쓴 것이라 이 스크립트가 유일한 출처다. 어휘가 늘면
    여기 KO 에 문구를 추가해야 하고, 빠뜨리면 실행이 실패한다.

산출: contracts/product-form-labels-ko.json
실행: python batch/ingest/build_form_labels.py
"""
import io
import json
import os
import sys

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
VOCAB = os.path.join(ROOT, "contracts", "product-feature-vocab.json")
OUT = os.path.join(ROOT, "contracts", "product-form-labels-ko.json")

# 화면 문구. 값(key)은 어휘집과 한 글자도 달라선 안 된다
KO = {
    # 배너 문구에 쓰려고 넓혔다 (Jira 172). 등록 폼은 성분을 전성분 텍스트로
    # 받으므로 폼에는 안 쓰이지만, 배너는 "나이아신아마이드가 들어간" 처럼
    # 값 하나를 그대로 문구에 넣는다.
    "ingredient": {
        "Hyaluronic Acid": "히알루론산",
        "Silicone": "실리콘",
        "Vitamin C": "비타민C",
        "Squalane": "스쿠알란",
        "Probiotic / Ferment": "발효·프로바이오틱",
        "Green Tea": "녹차",
        "Peptides": "펩타이드",
        "Aloe": "알로에",
        "Lactic Acid": "락틱애시드",
        "Licorice": "감초",
        "SPF": "자외선 차단",
        "Shea Butter": "시어버터",
        "Panthenol (B5)": "판테놀(B5)",
        "Niacinamide": "나이아신아마이드",
        "Jojoba": "호호바",
        "AHA/Glycolic Acid": "AHA·글리콜산",
        "Salicylic Acid": "살리실산(BHA)",
        "Ceramide": "세라마이드",
        "Rosehip / Rose": "로즈힙·장미",
        "Caffeine": "카페인",
        "Urea": "요소(우레아)",
        "Adenosine": "아데노신",
        "Allantoin": "알란토인",
        "Retinol": "레티놀",
        "Zinc": "아연",
        "Alcohol Denat": "변성알코올",
        "Centella (Cica)": "센텔라(시카)",
        "Willow Bark": "버드나무 껍질",
        "Collagen": "콜라겐",
        "Mineral Oil / Petrolatum": "미네랄오일·바셀린",
    },
    # 경계는 어휘집 `price_bin_edges` 가 정본이다. 여기 문구의 숫자를 고칠 때
    # 경계도 같이 봐야 한다 — 달러 기준이고 원화 전환은 아직 미정이다.
    "price_bin": {
        "~20": "2만원대 이하",
        "20-35": "2~4만원대",
        "35-50": "4~6만원대",
        "50-80": "6~10만원대",
        "80+": "10만원대 이상",
    },
    "secondary_category": {
        "Cleansers": "클렌저",
        "Eye Care": "아이케어",
        "Lip Balms & Treatments": "립밤·립케어",
        "Masks": "마스크·팩",
        "Moisturizers": "보습·크림",
        "Self Tanners": "셀프 태닝",
        "Sunscreen": "선케어",
        "Treatments": "집중 케어(트리트먼트)",
    },
    "tertiary_category": {
        "BB & CC Creams": "BB·CC 크림",
        "Blemish & Acne Treatments": "여드름·트러블 케어",
        "Exfoliators": "각질 제거",
        "Eye Creams & Treatments": "아이크림",
        "Eye Masks": "아이패치·아이마스크",
        "Face Masks": "페이스 마스크·팩",
        "Face Oils": "페이스 오일",
        "Face Serums": "세럼·앰플",
        "Face Sunscreen": "얼굴용 선크림",
        "Face Wash & Cleansers": "클렌징 폼·워시",
        "Face Wipes": "클렌징 티슈",
        "Facial Peels": "필링",
        "For Face": "얼굴용 (기타)",
        "Lip Balms & Treatments": "립밤·립케어",
        "Makeup Removers": "메이크업 리무버",
        "Mists & Essences": "미스트·에센스",
        "Moisturizers": "수분크림·로션",
        "Night Creams": "나이트 크림",
        "Toners": "토너·스킨",
    },
    "concern": {
        "Dullness/Uneven Texture": "칙칙함·피부결",
        "Dryness": "건조함",
        "Anti-Aging": "주름·안티에이징",
        "Pores": "모공",
        "Loss of firmness": "탄력 저하",
        "Dark Circles": "다크서클",
        "Acne/Blemishes": "여드름·트러블",
        "Redness": "홍조",
        "Dark spots": "색소침착·잡티",
    },
    "clean": {
        "Clean at Sephora": "클린 뷰티 인증",
        "Vegan": "비건",
        "Without Parabens": "파라벤 무첨가",
        "Cruelty-Free": "동물실험 반대",
        "Clean + Planet Positive": "친환경 클린",
        "Fragrance Free": "무향",
        "Oil Free": "오일 프리",
        "Without Sulfates SLS & SLES": "설페이트(SLS·SLES) 무첨가",
        "Without Silicones": "실리콘 무첨가",
        "Refill Available": "리필 가능",
        "Without Phthalates": "프탈레이트 무첨가",
        "Alcohol Free": "알코올 무첨가",
        "Without Mineral Oil": "미네랄 오일 무첨가",
        "Gluten Free": "글루텐 프리",
        "Hypoallergenic": "저자극",
        "Without Oxybenzone": "옥시벤존 무첨가",
    },
    "texture": {
        "Hydrating": "촉촉한",
        "Plumping": "탄탄한(플럼핑)",
        "Radiant Finish": "광채 마무리",
        "Natural Finish": "자연스러운 마무리",
        "High Shine Finish": "윤광 마무리",
    },
}

# highlights 는 세 갈래가 한 배열로 들어간다. 화면 묶음만 나눠 준다
# 세그먼트는 어휘집 블록이 아니라 `affinity_lift.csv` 의 세그먼트다.
# 배너 축 `segment` 문구에 쓴다 — "지성 피부에서 반응이 좋았던".
SEGMENT_KO = [
    {"value": "combination", "ko": "복합성 피부", "field": "skin_type"},
    {"value": "dry", "ko": "건성 피부", "field": "skin_type"},
    {"value": "normal", "ko": "중성 피부", "field": "skin_type"},
    {"value": "oily", "ko": "지성 피부", "field": "skin_type"},
    {"value": "fair", "ko": "밝은 톤", "field": "skin_tone"},
    {"value": "light", "ko": "라이트 톤", "field": "skin_tone"},
    {"value": "medium", "ko": "미디엄 톤", "field": "skin_tone"},
    {"value": "tan", "ko": "탠 톤", "field": "skin_tone"},
    {"value": "deep", "ko": "딥 톤", "field": "skin_tone"},
    {"value": "black", "ko": "검은 모발", "field": "hair_color"},
    {"value": "brown", "ko": "갈색 모발", "field": "hair_color"},
    {"value": "blonde", "ko": "금발", "field": "hair_color"},
    {"value": "auburn", "ko": "적갈색 모발", "field": "hair_color"},
    {"value": "red", "ko": "붉은 모발", "field": "hair_color"},
    {"value": "blue", "ko": "푸른 눈", "field": "eye_color"},
    {"value": "brown", "ko": "갈색 눈", "field": "eye_color"},
    {"value": "green", "ko": "녹색 눈", "field": "eye_color"},
    {"value": "gray", "ko": "회색 눈", "field": "eye_color"},
    {"value": "hazel", "ko": "담갈색 눈", "field": "eye_color"},
]

GROUPS = [
    {"group": "concern", "ko": "피부 고민",
     "hint": "가장 중요합니다. 해당하는 것을 모두 고르세요"},
    {"group": "clean", "ko": "성분 표방", "hint": "해당 없으면 비워도 됩니다"},
    {"group": "texture", "ko": "제형·마무리", "hint": "해당 없으면 비워도 됩니다"},
]


SITE_LABELS = os.path.join(ROOT, "contracts", "localization", "labels-ko.json")

# 사이트 라벨이 우선한다 (결정 2026-09-10, 프론트). 같은 영문 키에 등록 폼과 쇼핑몰이
# 다른 한국어를 붙이면 사장님이 폼에서 고른 태그 이름과 고객 화면의 이름이 어긋난다.
# 위 KO 는 사이트 라벨에 없는 키(가격대·성분 일부·세그먼트)만 실제로 쓰인다.
SITE_GROUPS = ("highlights", "skincare_concerns", "category", "suitable_skin_types")


def overlay_site_labels(ko):
    if not os.path.exists(SITE_LABELS):
        return 0
    site = json.load(open(SITE_LABELS, encoding="utf-8"))
    merged = {}
    for g in SITE_GROUPS:
        merged.update(site.get(g, {}))
    changed = 0
    for table in ko.values():
        for key in list(table):
            if key in merged and table[key] != merged[key]:
                table[key] = merged[key]
                changed += 1
    return changed


def main():
    changed = overlay_site_labels(KO)
    if changed:
        print(f"사이트 라벨로 덮어쓴 항목 {changed}개 (contracts/localization/labels-ko.json)")
    vocab = json.load(open(VOCAB, encoding="utf-8"))
    blocks = {b["name"]: b for b in vocab["blocks"]}

    out = {
        "segment": SEGMENT_KO,
        "_note": "화면은 ko, 서버로 보내는 값은 value. value 는 어휘집 문자열이라 "
                 "한 글자도 바꾸면 안 된다. 이 파일은 "
                 "batch/ingest/build_form_labels.py 가 만든다 — 직접 고치지 말 것",
        "vocab_version": vocab["version"],
        "highlights_groups": GROUPS,
    }

    missing = []
    for name, table in KO.items():
        values = blocks[name]["vocab"]
        missing += [f"{name}: {v}" for v in values if v not in table]
        extra = [k for k in table if k not in values]
        if extra:
            raise SystemExit(f"{name}: 어휘집에 없는 값에 라벨이 붙어 있다 {extra}")
        out[name] = [{"value": v, "ko": table[v]} for v in values if v in table]

    if missing:
        raise SystemExit("한국어 라벨이 없는 값이 있다:\n  " + "\n  ".join(missing))

    io.open(OUT, "w", encoding="utf-8").write(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    total = sum(len(out[k]) for k in KO)
    print(f"폼 라벨 {total}개 -> {os.path.relpath(OUT, ROOT)}"
          f" (어휘집 {vocab['version']})")
    for k in KO:
        print(f"  {k:<20} {len(out[k]):>3}개")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
