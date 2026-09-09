from __future__ import annotations

import re
from collections import Counter
from pathlib import Path


SOURCE_DIR = Path(
    r"C:\Users\SSAFY\Downloads\HWABUN_한국어화_대조표_20260909"
)
OUTPUT_DIR = Path(__file__).resolve().parent / "HWABUN_한국어화_검수본_20260909"


CATEGORY_MAP = {
    "BB & CC Creams": "BB·CC크림",
    "Blemish & Acne Treatments": "트러블 케어",
    "Cleansers": "클렌징",
    "Exfoliators": "필링·스크럽",
    "Eye Care": "아이 케어",
    "Eye Creams & Treatments": "아이크림·아이 케어",
    "Eye Masks": "아이 패치",
    "Face Masks": "마스크팩",
    "Face Oils": "페이스 오일",
    "Face Serums": "에센스·세럼·앰플",
    "Face Sunscreen": "페이스 선케어",
    "Face Wash & Cleansers": "클렌징폼·젤",
    "Face Wipes": "클렌징 티슈·패드",
    "Facial Peels": "필링 케어",
    "For Face": "페이스용",
    "Lip Balms & Treatments": "립 케어",
    "Makeup Removers": "메이크업 리무버",
    "Masks": "마스크팩",
    "Mists & Essences": "미스트·에센스",
    "Moisturizers": "크림·로션",
    "Night Creams": "나이트 케어",
    "Self Tanners": "셀프 태닝",
    "Skincare": "스킨케어",
    "Sunscreen": "선케어",
    "Toners": "스킨·토너",
    "Treatments": "집중 케어",
}

HIGHLIGHT_MAP = {
    "AHA/Glycolic Acid": "AHA·글라이콜릭애씨드",
    "Alcohol Free": "알코올 무첨가",
    "Best for Combination Skin": "복합성 피부 추천",
    "Best for Dry Skin": "건성 피부 추천",
    "Best for Dry, Combo, Normal Skin": "건성·복합성·중성 피부 추천",
    "Best for Normal Skin": "중성 피부 추천",
    "Best for Oily Skin": "지성 피부 추천",
    "Best for Oily, Combo, Normal Skin": "지성·복합성·중성 피부 추천",
    "Black Owned at Sephora": "흑인 창업 브랜드(세포라)",
    "Clean + Planet Positive": "클린·친환경 뷰티",
    "Clean at Sephora": "세포라 클린",
    "Collagen": "콜라겐",
    "Community Favorite": "인기 제품",
    "Cream Formula": "크림 제형",
    "Cruelty-Free": "크루얼티 프리",
    "Customizable": "맞춤형",
    "Fragrance Free": "무향료",
    "Fresh Scent": "산뜻한 향",
    "Full Coverage": "풀 커버",
    "Gluten Free": "글루텐 프리",
    "High Shine Finish": "글로시 피니시",
    "Hyaluronic Acid": "히알루론산",
    "Hydrating": "수분·보습",
    "Hypoallergenic": "저자극 포뮬러",
    "Lactic Acid": "락틱애씨드",
    "Matte Finish": "매트 피니시",
    "Medium Coverage": "미디엄 커버",
    "Natural Finish": "내추럴 피니시",
    "Niacinamide": "나이아신아마이드",
    "Oil Free": "오일 프리",
    "Plumping": "플럼핑 케어",
    "Radiant Finish": "광채 피니시",
    "Recyclable Packaging": "재활용 가능 패키지",
    "Refill Available": "리필 가능",
    "Retinol": "레티놀",
    "SPF": "SPF 자외선 차단",
    "Salicylic Acid": "살리실산",
    "UV Protection": "자외선 차단",
    "Vegan": "비건",
    "Vitamin C": "비타민 C",
    "Warm &Spicy Scent": "따뜻한 스파이시 향",
    "Without Mineral Oil": "미네랄 오일 무첨가",
    "Without Oxybenzone": "옥시벤존 무첨가",
    "Without Parabens": "파라벤 무첨가",
    "Without Phthalates": "프탈레이트 무첨가",
    "Without Silicones": "실리콘 무첨가",
    "Without Sulfates SLS & SLES": "설페이트(SLS·SLES) 무첨가",
    "allure 2017 Best of Beauty Award Winner": "얼루어 2017 베스트 오브 뷰티 수상",
    "allure 2019 Best of Beauty Award Winner": "얼루어 2019 베스트 오브 뷰티 수상",
    "allure 2020 Best of Beauty Award Winner": "얼루어 2020 베스트 오브 뷰티 수상",
    "allure 2021 Best of Beauty Award Winner": "얼루어 2021 베스트 오브 뷰티 수상",
    "allure 2021: Clean Beauty Winner": "얼루어 2021 클린 뷰티 수상",
    "allure 2022 Best of Beauty Award Winner": "얼루어 2022 베스트 오브 뷰티 수상",
}

CONCERN_MAP = {
    "Acne/Blemishes": "트러블·여드름",
    "Anti-Aging": "안티에이징",
    "Dark Circles": "다크서클",
    "Dark spots": "기미·잡티",
    "Dryness": "건조함",
    "Dullness/Uneven Texture": "칙칙함·거친 피부결",
    "Loss of firmness": "탄력 저하",
    "Pores": "모공",
    "Redness": "붉은 기",
}

SKIN_TYPE_MAP = {
    "combination": "복합성",
    "dry": "건성",
    "normal": "중성",
    "oily": "지성",
}

BADGE_MAP = {
    "exclusive": "단독",
    "limited": "한정",
    "new": "신상품",
    "online_only": "온라인 전용",
}

OPTION_MAP = {
    "0.5/15ml": "15ml",
    "1.69 oz / 50 mL Refill": "50ml 리필",
    "1.69 oz/ 50 mL": "50ml",
    "1.7 oz/ 50 mL": "50ml",
    "3.33 oz / 100 mL": "100ml",
    "30 Treatments + 5 Bonus": "30회분 + 5회분 추가",
    "5 Treatments": "5회분",
    "60 Treatments": "60회분",
    "Berry": "베리",
    "Dark": "다크",
    "Grapefruit": "자몽",
    "Gummy Bear": "구미 베어",
    "Hot Cocoa": "핫 코코아",
    "Light": "라이트",
    "Limited Edition 2.5 oz/ 73.9 mL": "한정판 73.9ml",
    "Matcha Bubble Tea": "말차 버블티",
    "Medium": "미디엄",
    "Mini size - 1 oz / 28 g": "미니 28g",
    "Peach Iced Tea": "피치 아이스티",
    "Pumpkin Pie": "펌킨 파이",
    "Standard size - 2.25 oz / 64 g": "본품 64g",
    "Strawberry Shortcake": "스트로베리 쇼트케이크",
    "Sweet Candy": "스위트 캔디",
    "Taro Bubble Tea": "타로 버블티",
    "Vanilla": "바닐라",
    "Watermelon Pop": "워터멜론 팝",
}

PRODUCT_NAME_MAP = {
    "Protini Polypeptide Firming Refillable Moisturizer": "프로티니 폴리펩타이드 퍼밍 리필 모이스처라이저",
    "The Water Cream Oil-Free Pore Minimizing Moisturizer": "더 워터 크림 오일 프리 모공 케어 모이스처라이저",
    "Magic Cream Moisturizer with Hyaluronic Acid": "매직 크림 모이스처라이저 (히알루론산 함유)",
    "The True Cream Aqua Bomb": "더 트루 크림 아쿠아 밤",
    "The True Cream Moisturizing Bomb": "더 트루 크림 모이스처라이징 밤",
    "Vegan Milk Moisturizer": "비건 밀크 모이스처라이저",
    "Crème de la Mer Moisturizer": "크렘 드 라 메르 모이스처라이저",
    "Indigo Overnight Repair Serum in Cream Treatment": "인디고 오버나이트 리페어 세럼 인 크림",
    "Natural Moisturizing Factors + HA": "내추럴 모이스처라이징 팩터스 + HA",
    "Charlotte’s Magic Serum with Vitamin C": "샬롯츠 매직 세럼 (비타민 C 함유)",
    "The Silk Peony Melting Eye Cream": "더 실크 피오니 멜팅 아이크림",
    "Jet Lag Mask": "제트 랙 마스크",
    "Lip Glowy Balm": "립 글로이 밤",
    "Lippe Balm": "립페 밤",
    "Clear Sunscreen Stick SPF 50+": "클리어 선스크린 스틱 SPF 50+",
    "Squalane + Vitamin C Rose Firming Oil": "스쿠알란 + 비타민 C 로즈 퍼밍 오일",
    "Salicylic Acid Acne Healing Dots": "살리실산 트러블 케어 패치",
}

PRODUCT_NAME_REPLACEMENTS = (
    (" with ", " ("),
    (" 위드 ", " ("),
    ("오일-프리", "오일 프리"),
    ("오일프리", "오일 프리"),
    ("젤-크림", "젤 크림"),
    ("아이 크림", "아이크림"),
    ("립 밤", "립밤"),
    ("비타민-C", "비타민 C"),
    ("Hyaluronic Acid", "히알루론산"),
    ("Watermelon Glow", "워터멜론 글로우"),
    ("Smart Clinical Repair", "스마트 클리니컬 리페어"),
    ("Advanced Night Repair", "어드밴스드 나이트 리페어"),
    ("Banana Bright", "바나나 브라이트"),
    ("Rose Deep Hydration", "로즈 딥 하이드레이션"),
    ("Hydro Biotic Recovery", "하이드로 바이오틱 리커버리"),
    ("Balancing Force", "밸런싱 포스"),
    ("Glow Cycle", "글로우 사이클"),
    ("Original Skin", "오리지널 스킨"),
    ("Clear Improvement", "클리어 임프루브먼트"),
    ("Advanced Génifique", "어드밴스드 제니피끄"),
    ("Squalane + Omega Repair", "스쿠알란 + 오메가 리페어"),
    ("Revitalizing Supreme+", "리바이탈라이징 수프림+"),
    ("Confidence in a Cream", "컨피던스 인 어 크림"),
    ("Santorini Grape", "산토리니 그레이프"),
    ("Moisture Surge", "모이스처 써지"),
    ("The Camellia Oil", "더 카멜리아 오일"),
    ("T.L.C. Sukari Babyfacial", "T.L.C. 수카리 베이비페이셜"),
    ("F-Balm Electrolyte", "F-밤 일렉트롤라이트"),
    ("Skinlongevity", "스킨롱제비티"),
    ("Powerful-Strength", "파워풀 스트렝스"),
    ("Advanced Night Repair", "어드밴스드 나이트 리페어"),
    ("Urban Environment", "어반 인바이런먼트"),
    ("Natural Moisturizing Factors", "내추럴 모이스처라이징 팩터스"),
    ("Protini", "프로티니"),
    ("Magic Cream", "매직 크림"),
    ("C-Rush", "C-러시"),
    ("Barrier+", "배리어+"),
    ("Lala Retro", "라라 레트로"),
    ("Lotus", "로터스"),
    ("Moisture Surge", "모이스처 써지"),
    ("Dreamskin", "드림스킨"),
    ("Plum Plump", "플럼 플럼프"),
    ("Honey Halo", "허니 헤일로"),
    ("Vinosource-", "비노수르스-"),
    ("ExfoliKate", "엑스폴리케이트"),
    ("Good Genes", "굿 진스"),
    ("Estee Lauder", "에스티 로더"),
    ("B-Hydra", "B-하이드라"),
    ("D-Bronzi", "D-브론지"),
    ("Tea Elixir", "티 엘릭시르"),
    ("Vinoperfect", "비노퍼펙트"),
    ("Violet-C", "바이올렛-C"),
    ("The Dewy Serum", "더 듀이 세럼"),
    ("Vinopure", "비노퓨어"),
    ("The Serum Stick", "더 세럼 스틱"),
    ("A-Passioni", "A-파시오니"),
    ("Glow Cycle", "글로우 사이클"),
    ("C-Firma", "C-피르마"),
    ("Superfood", "슈퍼푸드"),
    ("Beste No. 9", "베스티 No. 9"),
    ("Take The Day Off", "테이크 더 데이 오프"),
    ("Slaai", "슬라이"),
    ("5 Stars", "파이브 스타즈"),
    ("Auto Correct", "오토 코렉트"),
    ("C-Tango", "C-탱고"),
    ("Benefiance", "베네피앙스"),
    ("Brighten-i", "브라이트닝-i"),
    ("Capture Totale", "캡춰 토탈"),
    ("Ginzing", "진징"),
    ("The Kissu", "더 키수"),
    ("Brazilian Kiss", "브라질리언 키스"),
    ("Umbra", "엄브라"),
    ("Virgin Marula", "버진 마룰라"),
    ("Abeille Royale", "아베이 로얄"),
    ("Yo Glow", "요 글로우"),
    ("Lemonade", "레모네이드"),
    ("Dewtopia", "듀토피아"),
    ("The Essence", "더 에센스"),
    ("Green Clean", "그린 클린"),
    ("E-Rase", "E-레이즈"),
    ("Hydra Zen", "이드라젠"),
    ("Hello FAB", "헬로 FAB"),
    ("Cicapair", "시카페어"),
    ("Alpha Beta", "알파 베타"),
    ("Avocado", "아보카도"),
    ("GOOPGLOW", "굽글로우"),
    ("GENIUS", "지니어스"),
    ("Glow2OH", "글로우2OH"),
    ("SEA", "씨"),
    ("ICE", "아이스"),
    ("Rose", "로즈"),
    ("여드름 치료", "트러블 케어"),
    ("모공 미니마이징", "모공 케어"),
    ("모공리스", "모공 케어"),
    ("모공 클리어링", "모공 케어"),
    ("모공 레미디", "모공 케어"),
    ("링클 코렉팅", "주름 개선"),
    ("디퍼핑", "붓기 케어"),
    ("리서페이싱", "피부결 케어"),
    ("스킨-소프트닝", "피부결 케어"),
    ("메이크업-멜팅", "메이크업 멜팅"),
    ("안티옥시던트", "항산화"),
    ("프로시 페이스 워시", "포밍 클렌저"),
    ("페이스 워시", "클렌저"),
    ("포어", "모공"),
)

COMMON_REPLACEMENTS = (
    ("mL", "ml"),
    ("&quot;", '"'),
    ("&#151;", "—"),
    ("인플루언스터", "인플루엔스터"),
    ("젤-크림", "젤 크림"),
    ("아이 크림", "아이크림"),
    ("립 밤", "립밤"),
    ("오일-프리", "오일 프리"),
    ("오일프리", "오일 프리"),
    ("페이스 와이프", "클렌징 티슈"),
    ("자유 라디칼", "활성산소"),
    ("까치발 주름", "눈가 잔주름"),
    ("피부 동일 세라마이드", "피부 유사 세라마이드"),
    ("피부 질감", "피부결"),
    ("피부의 질감", "피부결"),
    ("피부 결과", "피부결과"),
    ("고르지 않은 질감", "거친 피부결"),
    ("탄력 및 탄성 저하", "탄력 저하"),
    ("잔주름 및 주름", "잔주름·주름"),
    ("칙칙함 및 고르지 못한 피부결", "칙칙함·고르지 못한 피부결"),
    ("칙칙함과 고르지 못한 피부결", "칙칙함·고르지 못한 피부결"),
    ("붉음", "붉은 기"),
    ("합성향료", "합성 향료"),
    ("타겟 케어", "집중 케어"),
    ("클린 피부", "깨끗이 세안한 피부"),
    ("한 움큼 손에 덜어", "적당량을 손에 덜어"),
    ("피부를 재충전", "피부에 영양과 생기를 더해"),
    ("피부의 갈증을 해소", "피부에 수분이 채워졌"),
    ("노화 방지", "안티에이징 케어"),
    ("여드름 치료", "트러블 케어"),
    ("여드름 치료 패치", "트러블 케어 패치"),
    ("모공 축소", "모공 케어"),
    ("모공 없는 마무리", "매끈한 모공 커버"),
    ("피부를 해독", "피부 노폐물을 딥 클렌징"),
    ("해독 쿨링", "딥 클렌징 쿨링"),
    ("깊은 해독", "딥 클렌징"),
    ("혜택을 누릴 수", "보습 효과를 느낄 수"),
    ("피부를 변화시켜", "피부 변화를 이끌어"),
    ("피부를 공격합니다", "피부를 집중 케어합니다"),
)

DESCRIPTION_REPLACEMENTS = (
    ("피부에 영양과 생기를 더해하는", "피부에 영양과 생기를 더하는"),
    ("최적의 하루 종일 수분 공급을 제공하는", "오랜 시간 촉촉함을 유지해 주는"),
    ("최상의 보호를 제공합니다", "강력한 보호 효과를 제공합니다"),
    ("최상의 보호하는 데 도움을 줍니다", "강력한 보호 효과를 제공합니다"),
    ("수분 공급을 제공하는", "수분을 공급하는"),
    ("보호를 제공합니다", "보호하는 데 도움을 줍니다"),
    ("광채를 제공합니다", "광채를 더해줍니다"),
    ("수분 공급을 선사합니다", "촉촉한 보습감을 선사합니다"),
    ("피부를 빛나게 해줍니다", "피부에 건강한 광채를 더해줍니다"),
    ("피부를 빛나게", "피부에 광채를 더해"),
    ("눈에 보이는 불순물", "눈에 보이는 노폐물"),
    ("최소한의 문질러 메이크업을 제거하며", "적게 문질러도 메이크업을 부드럽게 녹여내며"),
    ("고집 센 메이크업", "잘 지워지지 않는 메이크업"),
    ("성능을 타협하지 않는", "제품력을 놓치지 않은"),
    ("강한 화학 성분", "피부 부담이 될 수 있는 성분"),
    ("제품이나 펌프 하단을 만지지 마세요. 오염을 방지하기 위함입니다.", "오염을 방지하려면 내용물과 펌프 안쪽을 손으로 만지지 마세요."),
    ("이 제품은 동물 실험을 하지 않았습니다.", "크루얼티 프리 제품입니다."),
    ("동물 실험을 하지 않았으며", "크루얼티 프리 제품이며"),
    ("동물 실험을 하지 않은 제품", "크루얼티 프리 제품"),
    ("동물 실험 반대", "크루얼티 프리"),
    ("비건이며 동물 실험을 하지 않고", "비건·크루얼티 프리 제품이며"),
    ("비건, 동물 실험을 하지 않았으며", "비건·크루얼티 프리 제품이며"),
    ("사용 가능합니다", "사용할 수 있습니다"),
    ("적용하세요", "발라주세요"),
    ("도포하세요", "발라주세요"),
    ("바릅니다", "발라줍니다"),
    ("원을 그리며", "원을 그리듯"),
    ("피부가 젊음을 유지하는 데 필요한", "건강하고 탄력 있는 피부를 위한"),
    ("피부를 지지하고", "피부 장벽을 강화하고"),
    ("궁극의 진정과 영양을 위한", "집중적인 진정과 영양 케어를 위한"),
    ("몸과 자연에서 자연 발생하는", "피부와 자연에 존재하는"),
    ("약간의 따가움", "일시적인 따끔거림"),
    ("태닝 효과", "태닝 컬러"),
    ("황산염계 SLS 및 SLES", "설페이트계 계면활성제(SLS·SLES)"),
    ("황산염 SLS 및 SLES", "설페이트계 계면활성제(SLS·SLES)"),
    ("황산염(SLS & SLES)", "설페이트계 계면활성제(SLS·SLES)"),
    ("황산계 계면활성제(SLS & SLES)", "설페이트계 계면활성제(SLS·SLES)"),
    ("활성 여드름 개선 성분", "트러블 케어 성분"),
    ("여드름 개선 추출물", "트러블 케어 성분"),
    ("하이드로콜로이드 밴드의 치유력", "하이드로콜로이드 밴드의 보호·흡수 기능"),
    ("폭발적인 수분 공급", "풍부한 수분 공급"),
    ("즉각 사용 후", "1회 사용 직후"),
    ("피부가 영양을 받고 건강해 보인다고", "피부에 영양감이 느껴지고 건강해 보인다고"),
    ("부적절한 폐기를 삼가 주세요", "변기에 버리지 마세요"),
    ("놀라운 소녀들의 학교 하루 수업", "교육 기회가 필요한 소녀들의 하루 수업"),
    ("크루얼티 프리 제품이며 글루텐 프리 제품입니다", "크루얼티 프리·글루텐 프리 제품입니다"),
    ("단순한 선스크린 그 이상, 태양 에너지로 작동하는 스킨케어입니다", "단순한 선크림을 넘어, 햇빛으로 활성화되는 스킨케어 제품입니다"),
    ("신선하고 젊어 보인다고", "생기 있고 어려 보인다고"),
)

REVIEW_REPLACEMENTS = (
    ("돈이 아깝습니다", "돈이 아까워요"),
    ("솔직한 후기를 남깁니다", "솔직한 후기를 남겨요"),
    ("거의 푹신한 제형이 있고 피부에 그 푹신한 탄력을 그대로 남겨줘요", "쿠션감 있는 제형이라 바르고 나면 피부도 탱탱해진 느낌이에요"),
    ("30대에 생긴 부끄러운 여드름", "30대에 생긴 신경 쓰이던 여드름"),
    ("제형도 좋고 성분도 훌륭하며 피부가 기분 좋게 느껴져요", "제형과 성분이 마음에 들고 바른 뒤 피부도 편안해요"),
    ("가격을 정당화하기는 좀 어렵네요", "이 가격에 다시 살지는 고민돼요"),
    ("이 제품은 즐겼고", "사용감은 좋았고"),
    ("제품 자체는 잘 작동하는데", "제품 자체의 효과는 괜찮은데"),
    ("메이크업 아래에 발라도 너무 잘 작동해서 놀라워요", "메이크업 전에 발라도 밀리지 않아 좋아요"),
    ("투명 스틱 제형이 잘 작동하고", "투명 스틱 제형이라 사용하기 편하고"),
    ("이보다 더 잘 작동하는 제품이", "이보다 더 잘 지워지는 제품이"),
    ("잘 작동하고 피부도 자극하지 않아요", "세정력도 좋고 피부 자극도 없어요"),
    ("메이크업 지우는 데는 정말 잘 작동하는데", "메이크업은 정말 잘 지워지는데"),
    ("꽤 잘 작동하지만 냄새가 별로고", "세정력은 괜찮지만 향이 별로고"),
    ("그래도 이 제품은 잘 작동하고 마스카라도 잘 지워지고", "그래도 세정력은 좋고 마스카라도 잘 지워지며"),
    ("패치를 붙여봤는데 잘 작동하더라고요", "패치를 붙여봤는데 효과가 있더라고요"),
    ("피부가 완전 상쾌해지고 최고의 광채를 줘요", "피부가 산뜻해지고 윤기가 예쁘게 돌아요"),
    ("완전 게임 체인저에요", "정말 만족스러운 제품이에요"),
    ("완전 게임 체인저예요", "정말 만족스러운 제품이에요"),
    ("마스크를 밤새 착용하고 나니", "마스크를 바르고 잤더니"),
    ("무료로 받은 복합 박스", "무료로 받은 체험 제품"),
    ("인그로운 헤어가 빨리 해결됨", "인그로운 헤어가 빠르게 진정됨"),
    ("립글로스나 마스카라 아래에도 잘 어울려요", "립글로스나 립스틱 전에 발라도 잘 어울려요"),
    ("강력 추천합니다", "정말 추천해요"),
    ("강력히 추천합니다", "정말 추천해요"),
    ("추천하지 않습니다", "추천하지 않아요"),
    ("꼭 추천합니다", "추천해요"),
    ("추천합니다", "추천해요"),
    ("만족합니다", "만족해요"),
    ("사용했습니다", "사용했어요"),
    ("사용 중입니다", "사용 중이에요"),
    ("사용해봤습니다", "써봤어요"),
    ("사용해 보았습니다", "써봤어요"),
    ("느꼈습니다", "느꼈어요"),
    ("좋았습니다", "좋았어요"),
    ("없었습니다", "없었어요"),
    ("있었습니다", "있었어요"),
    ("놀랍습니다", "놀랐어요"),
    ("구매할 예정입니다", "구매할 예정이에요"),
    ("반품할 예정입니다", "반품할 예정이에요"),
    ("계속 사용할 예정입니다", "계속 쓸 예정이에요"),
    ("재구매 의사 있습니다", "재구매 의향 있어요"),
    ("다시 구매할 의향 있습니다", "재구매 의향 있어요"),
    ("제품입니다", "제품이에요"),
    ("피부입니다", "피부예요"),
    ("브랜드입니다", "브랜드예요"),
    ("보습제입니다", "보습제예요"),
    ("클렌저입니다", "클렌저예요"),
    ("세럼입니다", "세럼이에요"),
    ("크림입니다", "크림이에요"),
    ("마스크입니다", "마스크예요"),
    ("오일입니다", "오일이에요"),
    ("예정입니다", "예정이에요"),
    ("좋습니다", "좋아요"),
    ("마음에 듭니다", "마음에 들어요"),
    ("도움이 됩니다", "도움이 돼요"),
    ("효과적입니다", "효과가 좋아요"),
    ("완벽합니다", "완벽해요"),
    ("추천드립니다", "추천드려요"),
    ("감사합니다", "감사해요"),
    ("생각합니다", "생각해요"),
    ("기대됩니다", "기대돼요"),
    ("놀랐습니다", "놀랐어요"),
    ("확인했습니다", "확인했어요"),
    ("보입니다", "보여요"),
    ("느껴집니다", "느껴져요"),
    ("알 수 있습니다", "알 수 있어요"),
    ("말할 수 있습니다", "말할 수 있어요"),
    ("좋은 제품입니다", "좋은 제품이에요"),
    ("훌륭한 보습제입니다", "괜찮은 보습제예요"),
    ("최고의 보습제 중 하나입니다", "써본 보습제 중 손에 꼽아요"),
    ("제 개인적인 것입니다", "제 개인적인 생각이에요"),
    ("제 솔직한 의견입니다", "솔직하게 느낀 점이에요"),
    ("제 솔직한 생각입니다", "솔직하게 느낀 점이에요"),
    ("솔직한 리뷰를 작성합니다", "직접 써본 후기를 남겨요"),
    ("솔직한 리뷰를 작성했습니다", "직접 써본 후기를 남겨요"),
    ("솔직한 리뷰를 남깁니다", "직접 써본 후기를 남겨요"),
    ("리뷰용으로 무료 제공받았습니다", "리뷰용으로 무료 제공받아 써봤어요"),
    ("리뷰 목적으로 무료로 받았습니다", "리뷰용으로 무료 제공받아 써봤어요"),
    ("테스트용으로 무료 제공받았습니다", "테스트용으로 무료 제공받아 써봤어요"),
    ("테스트용으로 무료로 받았습니다", "테스트용으로 무료 제공받아 써봤어요"),
    ("테스트용으로 받았습니다", "테스트용으로 받아 써봤어요"),
    ("리뷰용으로 무료로 받았습니다", "리뷰용으로 무료 제공받아 써봤어요"),
    ("무료로 받아 테스트하고 리뷰한 거고", "무료로 제공받아 써본 제품이고"),
    ("무료로 받아 사용해봤어요", "무료로 제공받아 써봤어요"),
    ("무료로 받아 솔직한", "무료로 제공받아 솔직한"),
    ("피부가 드디어 행복해졌어요", "피부가 한결 편안해졌어요"),
    ("고집 센 메이크업", "잘 지워지지 않는 메이크업"),
    ("정말 잘 작동해요", "효과가 정말 좋아요"),
    ("잘 작동해요", "효과가 좋아요"),
    ("잘 작용하", "효과가 있"),
    ("의도한 대로 잘 작용한다고", "기대한 만큼 효과가 있다고"),
    ("문제성 피부", "트러블이 잘 나는 피부"),
    ("얼굴이 정말 신선하고", "피부가 정말 산뜻하고"),
    ("피부가 신선하고", "피부가 산뜻하고"),
    ("신선함 그 자체예요", "바르자마자 산뜻해요"),
    ("아주 진정되고", "피부가 편안해지고"),
    ("얼마나 상쾌해 보이게 해줬는지는", "얼마나 생기 있어 보이게 해줬는지는"),
    ("사용 후 피부가 부드럽고 빛나더라고요", "쓰고 나면 피부가 부드럽고 은은하게 윤기가 나더라고요"),
    ("제형도 흡수력도 정말 대단해요", "제형과 흡수감도 마음에 들어요"),
    ("보습이 잘 되어 있었어요", "피부가 촉촉했어요"),
    ("피부가 젊어진 느낌이에요", "피부에 생기가 도는 느낌이에요"),
    ("일반 약국 브랜드 립밤", "일반 드럭스토어 립밤"),
    ("저에게는", "저한테는"),
    ("저에게", "저한테"),
    ("저의 ", "제 "),
    ("촉감", "사용감"),
    ("질감", "제형"),
    ("모이스처라이저", "보습제"),
    ("선스크린", "선크림"),
    ("훌륭한", "좋은"),
    ("보통 피부", "중성 피부"),
    ("피부에요", "피부예요"),
    ("피부가 느껴지는 감촉", "세안 후 피부 느낌"),
    ("피부결과 외관", "피부결과 전반적인 피부 상태"),
    ("포장과 외관", "패키지와 디자인"),
    ("외관상 변화", "눈에 보이는 변화"),
    ("모든 메이크업을 정말 잘 분해해줘요", "메이크업을 정말 말끔하게 녹여줘요"),
    ("오래된 메이크업", "남아 있는 메이크업"),
    ("사용해보는", "써보는"),
    ("사용도 편한", "쓰기 편한"),
    ("사용하여", "사용해서"),
    ("사용하며", "쓰면서"),
    ("사용하기", "쓰기"),
    ("사용할", "쓸"),
    ("사용했는데", "써봤는데"),
    ("사용하면", "쓰면"),
    ("그러나 ", "다만 "),
    ("하지만 개인적으로는", "다만 저한테는"),
    ("매우 ", "정말 "),
)

INGREDIENT_REPLACEMENTS = (
    ("디카프릴릴카보네이트", "다이카프릴릴카보네이트"),
    ("디메치콘", "다이메티콘"),
    ("디소듐 에데타", "다이소듐이디티에이"),
    ("디소듐에데타", "다이소듐이디티에이"),
    ("디소듐 EDTA", "다이소듐이디티에이"),
    ("폴리소르베이트", "폴리솔베이트"),
    ("소르비탄", "솔비탄"),
    ("시트르산나트륨", "소듐시트레이트"),
    ("벤조에이트나트륨", "소듐벤조에이트"),
    ("락테이트나트륨", "소듐락테이트"),
    ("메타인산나트륨", "소듐메타포스페이트"),
    ("메타바이설파이트나트륨", "소듐메타바이설파이트"),
    ("수산화칼륨", "포타슘하이드록사이드"),
    ("글리콜릭애씨드", "글라이콜릭애씨드"),
    ("글리콜릭 애씨드", "글라이콜릭애씨드"),
    ("살리실릭 애씨드", "살리실릭애씨드"),
    ("히알루론산", "하이알루로닉애씨드"),
    ("향료 (파품)", "향료"),
)


def apply_replacements(text: str, replacements: tuple[tuple[str, str], ...]) -> str:
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def canonical_metric_size(value: str) -> str:
    """Keep the metric amount Korean stores foreground, while EN preserves US units."""
    prefix = "· " if value.startswith("· ") else ""
    raw = value[2:] if prefix else value
    suffix = " 리필" if re.search(r"\bRefill\b|리필", raw, re.I) else ""

    if "Golden Hour" in raw:
        return f"{prefix}골든 아워 50ml{suffix}"

    metric = re.search(r"(?<!\d)(\d+(?:\.\d+)?)\s*(mL|ml|g)\b", raw)
    if metric:
        number, unit = metric.groups()
        unit = "ml" if unit.lower() == "ml" else "g"
        return f"{prefix}{number}{unit}{suffix}"

    patches = re.search(r"(\d+)\s*Patches?", raw, re.I)
    if patches:
        return f"{prefix}{patches.group(1)}매"

    pads = re.search(r"(\d+)\s*Pads?", raw, re.I)
    if pads:
        return f"{prefix}{pads.group(1)}매"

    dots = re.search(r"(\d+)\s*(?:Healing\s+)?Dots?", raw, re.I)
    if dots:
        return f"{prefix}{dots.group(1)}매"

    wipes = re.search(r"(\d+)\s*Wipes?", raw, re.I)
    if wipes:
        return f"{prefix}{wipes.group(1)}매"

    pack = re.search(r"(\d+)\s*Pack", raw, re.I)
    if pack:
        return f"{prefix}{pack.group(1)}매입"

    treatments = re.search(r"(\d+)\s*Treatments?", raw, re.I)
    if treatments:
        return f"{prefix}{treatments.group(1)}회분"

    ounces = re.fullmatch(r"\.?\s*(\d+(?:\.\d+)?)\s*(?:fl\.?\s*)?oz", raw, re.I)
    if ounces:
        return f"{prefix}{ounces.group(1)}oz"

    return value


def localize_size_list(text: str) -> str:
    return "<br>".join(canonical_metric_size(part) for part in text.split("<br>"))


def localize_product_name(original: str, current: str) -> str:
    if original in PRODUCT_NAME_MAP:
        return PRODUCT_NAME_MAP[original]

    result = current
    for old, new in PRODUCT_NAME_REPLACEMENTS:
        result = result.replace(old, new)

    # Convert a trailing "with ingredient" opened above into a Korean ingredient note.
    if " (" in result and not result.endswith(")"):
        result += " 함유)"
    result = result.replace(" 함유 함유)", " 함유)")
    return result


def localize_path(original: str) -> str:
    return " > ".join(CATEGORY_MAP.get(part.strip(), part.strip()) for part in original.split(">"))


def localize_bullets(original: str, mapping: dict[str, str], fallback: str) -> str:
    parts = original.split("<br>")
    out: list[str] = []
    for part in parts:
        lead = "· " if part.startswith("· ") else ""
        key = part[2:] if lead else part
        out.append(lead + mapping.get(key.strip(), fallback))
    return "<br>".join(out)


def polish_description(field: str, text: str) -> str:
    result = apply_replacements(text, COMMON_REPLACEMENTS)
    result = apply_replacements(result, DESCRIPTION_REPLACEMENTS)

    if field == "피부 타입":
        result = re.sub(r"(?<![가-힣])보통(?![가-힣])", "중성", result)
    if field == "피부 고민":
        result = result.replace(", ", "·")
        result = result.replace(" 및 ", "·").replace("과 고르지", "·고르지")
    if field == "주요 성분":
        result = result.replace(". - ", ".<br>· ")
    if field == "성분 특징(프리)":
        result = result.replace(" 또한 ", " ")

    result = re.sub(r"(?<!\s)-(?!\s|\d)", "- ", result)
    result = result.replace("<br>- ", "<br>- ")
    return result


def informalize_copula(match: re.Match[str]) -> str:
    noun = match.group(1)
    last = noun[-1]
    if "가" <= last <= "힣":
        has_final_consonant = (ord(last) - ord("가")) % 28 != 0
        ending = "이에요" if has_final_consonant else "예요"
    else:
        ending = "예요"
    return noun + ending + match.group(2)


def informalize_review_endings(text: str) -> str:
    safe_endings = (
        (r"([가-힣]+)했습니다([.!?])", r"\1했어요\2"),
        (r"([가-힣]+)였습니다([.!?])", r"\1였어요\2"),
        (r"([가-힣]+)었습니다([.!?])", r"\1었어요\2"),
        (r"([가-힣]+)았습니다([.!?])", r"\1았어요\2"),
        (r"([가-힣]+)됩니다([.!?])", r"\1돼요\2"),
        (r"([가-힣]+)합니다([.!?])", r"\1해요\2"),
        (r"([가-힣]+)봅니다([.!?])", r"\1봐요\2"),
        (r"([가-힣]+)줍니다([.!?])", r"\1줘요\2"),
        (r"([가-힣]+)납니다([.!?])", r"\1나요\2"),
    )
    for pattern, replacement in safe_endings:
        text = re.sub(pattern, replacement, text)
    return re.sub(r"([가-힣A-Za-z0-9+]+)입니다([.!?])", informalize_copula, text)


def polish_review(text: str) -> str:
    result = apply_replacements(text, COMMON_REPLACEMENTS)
    result = apply_replacements(result, REVIEW_REPLACEMENTS)
    result = informalize_review_endings(result)

    result = result.replace("정말 정말", "진짜")
    result = result.replace("너무 너무", "진짜")
    result = result.replace("정말 너무", "진짜")
    result = result.replace("아주 아주", "정말")
    result = result.replace("첫 쓰고 나서", "처음 쓴 뒤")
    result = result.replace("쓰고 나서에는", "쓰고 나면")
    result = result.replace("클렌저이에요", "클렌저예요")
    result = result.replace("피부이에요", "피부예요")
    result = result.replace("마스크이에요", "마스크예요")
    result = result.replace("보습제이에요", "보습제예요")
    result = result.replace("토너이에요", "토너예요")
    result = result.replace("좋어요", "좋아요")
    result = result.replace("만족스럽습니다", "만족스러워요")
    result = result.replace("어려웠습니다", "어려웠어요")
    result = result.replace("만족하고 있습니다", "만족하고 있어요")
    result = result.replace("낫습니다", "나아요")
    result = result.replace("사용해야 합니다", "사용해야 해요")
    result = result.replace("기대하고 있습니다", "기대하고 있어요")
    result = result.replace("의향이 있습니다", "의향이 있어요")
    result = result.replace("골랐습니다", "골랐어요")
    result = result.replace("100%입니다", "100%예요")
    result = result.replace("봤습니다", "봤어요")
    result = result.replace("믿음직스럽습니다", "믿음이 가요")
    result = result.replace("충격적인 재확인 후", "사용을 중단하고서야 효과를 실감해서")
    result = result.replace("거의 푹신한 제형이 있고 피부에 그 푹신한 탄력을 그대로 남겨줘요", "쿠션감 있는 제형이라 바르고 나면 피부도 탱탱해진 느낌이에요")
    result = result.replace("제형도 좋고 성분도 훌륭하며 피부가 기분 좋게 느껴져요", "제형과 성분이 마음에 들고 바른 뒤 피부도 편안해요")
    result = result.replace(
        "정말 좋은 아이크림이에요. 바를 때 느낌이 좋고, 실제로 눈 밑을 촉촉하게 유지해줘요. "
        "아직 눈가에 잔주름이나 굵은 주름이 많지 않은데(거의 30대 중반) 이 제품이 그런 부분에도 "
        "도움이 되길 기대해요! 정말 좋은 아이크림이에요. 바를 때 느낌이 좋고, 실제로 눈 밑을 "
        "촉촉하게 유지해줘요. 아직 눈가에 잔주름이나 굵은 주름이 많지 않은데(거의 30대 중반) "
        "이 제품이 그런 부분에도 도움이 되길 기대해요.",
        "정말 좋은 아이크림이에요. 바를 때 느낌이 좋고 실제로 눈 밑을 촉촉하게 유지해줘요. "
        "아직 눈가에 잔주름이나 굵은 주름이 많지 않지만, 앞으로도 눈가 관리에 도움이 되길 기대해요.",
    )
    result = result.replace("!!참고로", "!! 참고로")
    return result


def polish_ingredients(text: str) -> str:
    return apply_replacements(text, INGREDIENT_REPLACEMENTS)


def split_markdown_row(line: str) -> list[str] | None:
    if not line.startswith("|"):
        return None
    parts = re.split(r"(?<!\\)\|", line)
    if len(parts) < 4:
        return None
    return [part.strip() for part in parts[1:-1]]


def join_markdown_row(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def read_logical_blocks(path: Path) -> list[str]:
    """Group table cells that contain literal line breaks into one logical row."""
    lines = path.read_text(encoding="utf-8").splitlines()
    blocks: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("|") and re.search(r"(?<!\\)\|\s*$", line) is None:
            row = [line]
            index += 1
            while index < len(lines):
                row.append(lines[index])
                if re.search(r"(?<!\\)\|\s*$", lines[index]):
                    break
                index += 1
            blocks.append("\n".join(row))
        else:
            blocks.append(line)
        index += 1
    return blocks


def process_enum_file(path: Path, stats: Counter[str]) -> str:
    section = ""
    output: list[str] = []
    maps = {
        "카테고리": CATEGORY_MAP,
        "하이라이트": HIGHLIGHT_MAP,
        "피부 고민": CONCERN_MAP,
        "적합 피부 타입": SKIN_TYPE_MAP,
        "배지": BADGE_MAP,
        "옵션 라벨": OPTION_MAP,
    }

    for line in read_logical_blocks(path):
        if line.startswith("## "):
            section = line[3:].split("—", 1)[0].strip()
        cells = split_markdown_row(line)
        if not cells or len(cells) != 2 or cells[0] in {"원문 (EN)", "---"}:
            output.append(line)
            continue

        mapping = next((m for name, m in maps.items() if section.startswith(name)), None)
        if mapping and cells[0] in mapping:
            before = cells[1]
            cells[1] = mapping[cells[0]]
            if cells[1] != before:
                stats[f"01:{section}"] += 1
            line = join_markdown_row(cells)
        output.append(line)

    return "\n".join(output) + "\n"


def process_product_file(path: Path, stats: Counter[str]) -> str:
    section = ""
    output: list[str] = []

    for line in read_logical_blocks(path):
        if line.startswith("# 상품 대조표 — ") and " → " in line:
            left = line.split("—", 1)[1].split("→", 1)[0].strip()
            line = f"# 상품 대조표 — {left} → {CATEGORY_MAP.get(left, left)}"
        if line.startswith("### "):
            section = line[4:]

        cells = split_markdown_row(line)
        if not cells or cells[0] in {"항목", "별점", "---"}:
            output.append(line)
            continue

        if section == "리뷰 (10건)" and len(cells) == 4:
            before = cells[3]
            cells[3] = polish_review(cells[3])
            if cells[3] != before:
                stats["리뷰"] += 1
            output.append(join_markdown_row(cells))
            continue

        if len(cells) != 3:
            output.append(line)
            continue

        field, original, current = cells
        before = current
        if section == "기본 정보":
            if field == "상품명":
                current = localize_product_name(original, current)
            elif field == "브랜드":
                current = original
            elif field == "카테고리":
                current = localize_path(original)
            elif field == "용량":
                current = localize_size_list(original)
            elif field == "하이라이트":
                current = localize_bullets(original, HIGHLIGHT_MAP, current)
            elif field == "피부 고민":
                current = localize_bullets(original, CONCERN_MAP, current)
            elif field == "적합 피부":
                current = localize_bullets(original, SKIN_TYPE_MAP, current)
            elif field == "옵션":
                parts = []
                for item in original.split("<br>"):
                    lead = "· " if item.startswith("· ") else ""
                    raw = item[2:] if lead else item
                    localized = OPTION_MAP.get(raw, canonical_metric_size(raw))
                    parts.append(lead + localized)
                current = "<br>".join(parts)
        elif section == "상품 설명":
            current = polish_description(field, current)
        elif section == "전성분" and field == "전성분":
            current = polish_ingredients(current)

        cells[2] = current
        if current != before:
            stats[section or "기타"] += 1
        output.append(join_markdown_row(cells))

    return "\n".join(output) + "\n"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stats: Counter[str] = Counter()

    source_files = [SOURCE_DIR / "01_열거값_대조.md"]
    source_files.extend(sorted(SOURCE_DIR.glob("*_상품_*.md")))
    if len(source_files) != 20:
        raise RuntimeError(f"Expected 20 source files, found {len(source_files)}")

    for source in source_files:
        if source.name == "01_열거값_대조.md":
            polished = process_enum_file(source, stats)
        else:
            polished = process_product_file(source, stats)
        (OUTPUT_DIR / source.name).write_text(polished, encoding="utf-8", newline="\n")

    print(f"Wrote {len(source_files)} files to {OUTPUT_DIR}")
    for key, count in sorted(stats.items()):
        print(f"{key}: {count} cells changed")


if __name__ == "__main__":
    main()
