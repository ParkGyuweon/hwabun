# SSAFY Beauty 상품 이미지 · 성향별 배너 크리에이티브 계획

> 2026-09-09. 대상: `frontend/src/mocks/products.ssafy-beauty.json` 8종, 배너(히어로 1 + 배너 행 6, Jira 184).
> 근거: [personalized-banner-plan.md](../dashboard/personalized-banner-plan.md) §2·§4·§10, `contracts/recommendation-io-spec.md` §5-1, `contracts/event-properties-schema.md` §3.11~3.13, [ai-insight-rules.md](../dashboard/ai-insight-rules.md) R-1·R-4·§4-3.
>
> 이 문서가 답하는 것: ① 배너가 어디에 몇 개 뜨고 무엇이 그 내용을 정하나 ② 사용자가 중요하게 따지는 것(성향)에 따라 **어떤 상품**을 **어떤 강조**로 보여주나 ③ 만들 이미지가 정확히 몇 장이고 어떤 파일인가 ④ 이미지 생성 프롬프트(상품 일관성 규칙 포함) ⑤ 데이터·AI·백엔드에 전할 것.

---

## 0. 원칙 다섯 개

1. **배너는 광고가 아니다.** 유료 노출·입찰이 없고 추천 결과를 강조해 보여 주는 자리다(기획 §15-10). 문구에 "광고"라는 말을 쓰지 않고, 화장품법 금지 표현(§4-3)을 이미지·문구 어디에도 넣지 않는다. 이미지에 피부 "개선 전후"를 그리지 않는다.
2. **무엇을 보여줄지는 추천 API가, 어떻게 보여줄지는 프론트가 정한다.** API가 `banner_type`·`banner_value`·`product_id`를 내리고(§5-1), 프론트는 그 `banner_type`에 맞는 문구 틀(`bannerCopy`)과 **이미지 변형**을 고른다. 성향 → 축 → 배너 타입 → 크리에이티브. 프론트가 임의로 상품을 바꾸지 않는다.
3. **이미지에 글자를 넣지 않는다. 예외는 용기의 "SSAFY BEAUTY" 워드마크 하나.** 한국어 문구·가격·용량은 전부 프론트가 얹는다(`bannerCopy`, `formatPrice`). 이미지에 글자가 있으면 어휘 개정·번역·가격 변경 때마다 다시 만들어야 하고, 생성 모델의 글자 오류도 피한다. 대신 문구 자리(세이프존)를 비워 둔다.
4. **한 상품은 어느 변형에서도 같은 물건이어야 한다.** 용기 형태·색·라벨 위치·조명을 마스터 이미지 한 장에서 고정하고, 변형은 마스터를 참조 이미지로 걸어 배경·소품·구도만 바꾼다. 마스터 없이 변형을 따로 생성하지 않는다.
5. **없는 데이터를 그림으로 만들지 않는다.** 함량(%)·할인율·임상 수치는 데이터에 없으므로 이미지에도 암시하지 않는다(배너 기획 §4-2).

---

## 1. 배너 자리와 결정 주체

184 브랜치 구현 기준(`HeroBanner`, `BannerRow`, `bannerConfig.ts`).

```
[히어로 1]         items[0] + 축 문구. 가로 1칸. 이미지 = 상품 × 변형(banner_type)
[배너 행 6]        slot 1~4 축 배너(성향이 고른 축), slot 5~6 new_brand 전용(설정값 BANNER_RESERVED=2)
[지금 주목할 상품] items 10칸 (기존 promo_row). 배너 이미지 아님, 상품 마스터 이미지
[카테고리 탭·필터·그리드]
```

| 결정 | 누가 | 근거 |
|---|---|---|
| 어느 상품이 히어로·배너에 오르나 | 추천 API(`/api/recommend`, `hero`·`banners[]`) | recommendation-io-spec §5-1 |
| 어느 축(`banner_type`)으로 말하나 | 프론트 세션 성향 → `axes` 파라미터 → API가 slot마다 `banner_type` 확정 | banner-plan §10-4 |
| 20% 탐색군(`trait_source=explore`) | 프론트가 세션당 1회 고정(`trait.ts` EXPLORE_RATIO) | 데이터 파트 요구: Spark가 뽑으면 실험 불성립 |
| 문구 틀 | 프론트 `bannerCopy(banner_type, banner_value)` | 184 |
| **이미지 변형** | **프론트. `banner_type` → 변형 5종 매핑(§2)** | 이 문서 |
| `new_brand` 전용 칸의 상품 | API. 지금 신규 브랜드 = SSAFY Beauty 8종 | §10-2 |

**SSAFY Beauty 8종이 실제로 뜨는 자리.** 신규 브랜드라 로그·리뷰가 없어 CBF/CF 점수가 낮다. 그래서 축 배너(slot 1~4)보다 **new_brand 전용 칸(slot 5~6)** 에 주로 오르고, 히어로에는 성분·고민 축이 맞을 때(예: 지성 고객 + Pores 축 → 제로 포어 라인) 오를 수 있다. 8종 전부에 5변형을 만들되, 우선순위는 이 자리를 기준으로 정한다(§4).

---

## 2. 성향 → 축 → 크리에이티브 변형

사용자가 "무엇을 따지나"는 세션 성향 5종(`price`·`ingredient`·`review`·`concern`·`participate`, banner-plan §2)이고, API 축은 7종(`concern`·`ingredient`·`clean`·`price_bin`·`category`·`segment`·`new_brand`)이다. 이미지 변형은 7종을 다 만들지 않고 **강조 요소가 같은 것끼리 묶어 5종**으로 둔다.

| 변형 `variant` | 받는 `banner_type` | 사용자가 따지는 것(성향) | 이미지가 강조하는 것 | 프론트가 얹는 문구(bannerCopy) | 넣지 않는 것 |
|---|---|---|---|---|---|
| `V1 price` 가격·용량 | `price_bin` | 가격 | 용기 하나, 소품 없음, 용량 감이 보이는 크기 대비(손·자·동전 없이 용기 자체 비례). 여백 넓음 | "{가격대}에서 고르면" + 가격·용량 | 할인 표시, 세일 태그, 묶음 |
| `V2 ingredient` 성분 | `ingredient`, `clean` | 성분 | 상품 + 핵심 성분 원물 소품(비타민나무 열매, 버드나무 껍질, 연어 PDRN은 추상 핑크 나선, 콜라겐은 젤리 질감), 성분이 앞에 있다는 인상 | "{성분}이 들어간" / "{clean 태그} 제품 중에서" | 함량 %, "무첨가" 글자, 시험관·의약품 느낌 |
| `V3 concern` 고민·효능 | `concern`, `category` | 피부 고민 | 상품 + 고민을 연상시키는 피부 질감 클로즈업(모공·건조·톤·탄력)을 **추상적으로**. 얼굴 전체·전후 비교 없음 | "{고민}이 고민이라면" / "{카테고리} 중에서" | 개선 전후, 화살표, 수치, 붉은 표시 |
| `V4 segment` 같은 피부의 선택 | `segment` | 리뷰·같은 피부 | 상품을 손에 든 라이프스타일 컷. 피부 톤을 드러내는 손·팔. 톤 5종 중 세션 페르소나 톤에 맞는 컷을 고른다(톤별 1장씩) | "{피부타입·톤} 사용자가 반응한" | 얼굴, 유명인 연출, 별점 그래픽 |
| `V5 story` 브랜드 스토리 | `new_brand` | 같이 키우고 싶다(participate) | 라인 전체 플랫레이 또는 만드는 과정(원료·노트·손글씨 없음) 느낌. 브랜드 톤을 보여 준다 | "새로 들어온 브랜드" | 창업자 얼굴, 수상 배지, "1위" 류 |

`V4`는 톤 5종(fair·light·medium·tan·deep)이 있어야 "같은 피부"가 성립한다. 8종 × 5톤 = 40장은 과하므로 **히어로에 오를 가능성이 큰 4종만 톤별로**, 나머지는 medium 1장(§4 우선순위).

### 2-1. 같은 상품, 다른 강조 — 예: SB000002 딥 비타C 캡슐 세럼

| 변형 | 화면 | 이미지 |
|---|---|---|
| V1 price | "2~4만원대에서 고르면 · $28 · 30ml" | 아이보리 배경에 세럼 병 하나, 여백 |
| V2 ingredient | "비타민C이 들어간" | 세럼 병 옆에 비타민나무 열매(주황) 몇 알, 캡슐 알갱이가 보이는 텍스처 |
| V3 concern | "색소침착·잡티가 고민이라면" | 세럼 병 + 은은하게 밝아지는 톤의 피부 질감 추상 배경(전후 없음) |
| V4 segment | "복합성 피부 사용자가 반응한" | 손등에 세럼 한 방울 떨어뜨리는 컷, 톤 medium |
| V5 story | "새로 들어온 브랜드" | SSAFY Beauty 라인 8종 플랫레이 안에서 이 병이 앞에 |

### 2-2. 상품 마스터 이미지(배너 아님)

목록 카드·상세 갤러리·`items` 10칸에 쓰는 기본 컷. 지금 SVG 플레이스홀더를 교체한다.

| 컷 | 용도 | 비율 |
|---|---|---|
| `M1 pack` 정면 3/4 팩샷 | 목록 카드, 상세 대표, `image_url` | 1:1 |
| `M2 texture` 제형 스와치 | 상세 갤러리 2번째(`images[1]`). 질감·색을 이미지로 판단한다는 근거(PowerReviews 97% 타인 사진, Salsify 6장 기대) | 1:1 |
| `M3 inuse` 사용 컷 | 상세 갤러리 3번째. 손·용기 조작(펌프·스포이드·패드 집기) | 1:1 |

M3는 **피드백 계약의 용기 축(뚜껑·펌프·스포이드)** 과 이어진다. 사장님이 용기 피드백을 받았을 때 이 컷을 바꾸는 게 반영 루프의 한 형태다.

---

## 3. 어느 상품을 어느 배너에 — 적격 규칙

API가 정하지만, 프론트 목(`mock`)과 발표 시연에서 어떤 조합이 나와야 자연스러운지 미리 잡는다. **상품 태그(`highlights`·`skincare_concerns`)와 축 값이 맞을 때만 그 축 배너에 오른다.**

| 상품 | 카테고리 | 고민 태그 | 핵심 성분(전성분 앞쪽) | clean 태그 | 가격대 | 맞는 `banner_type` | 히어로 후보 |
|---|---|---|---|---|---|---|---|
| SB000001 제로 포어 토닝 패드 | Exfoliators | Pores, Dullness | Lactic Acid, Salicylic Acid, Panthenol | Without Parabens | 20-35 | concern(Pores) · ingredient(Salicylic Acid) · segment(oily) · price_bin | ★ 지성·모공 |
| SB000002 딥 비타C 캡슐 세럼 | Face Serums | Dark spots, Dullness | Niacinamide, Vitamin C(캡슐) | Without Parabens·Mineral Oil | 20-35 | concern(Dark spots) · ingredient(Vitamin C·Niacinamide) · category | ★ 톤·잡티 |
| SB000003 PDRN 핑크 펩타이드 세럼 | Face Serums | Loss of firmness, Anti-Aging | Sodium DNA(PDRN), Peptides, Collagen | Without Parabens | 20-35 | concern(Anti-Aging) · ingredient(Peptides·Collagen) · segment(dry) | ★ 탄력 |
| SB000004 콜라겐 젤리 크림 | Moisturizers | Dryness, Loss of firmness | Collagen, Niacinamide | Without Parabens·Mineral Oil | 20-35 | concern(Dryness) · ingredient(Collagen) · segment(dry) | ★ 건성 |
| SB000005 제로 포어 폼 클렌저 | Cleansers | Pores, Acne | (계면활성 베이스) 쇠비름·동백 | Without Parabens | ~20 | concern(Acne) · price_bin(~20) · category | — (가격 축) |
| SB000006 제로 포어 모이스처 선 세럼 | Sunscreen | Dryness, Pores | Hyaluronic Acid 8종, Niacinamide, SPF | Without Oxybenzone | ~20 | ingredient(SPF·Hyaluronic Acid) · clean(Without Oxybenzone) · category | 시즌(여름) |
| SB000007 PDRN 핑크 펩타이드 아이크림 | Eye Care | Dark Circles, Anti-Aging | PDRN, Peptides, Caffeine, Retinol | Without Parabens | 20-35 | concern(Dark Circles) · ingredient(Caffeine·Retinol) | — |
| SB000008 PDRN 콜라겐 젤리 겔 마스크 | Masks | Dryness, Loss of firmness | PDRN, Peptides, Collagen | Without Parabens | ~20 | price_bin(~20) · concern(Dryness) · new_brand | — (전용 칸) |

**규칙(프론트 목·시연용, API가 오면 API 우선):**
- `concern` 축: 상품 `skincare_concerns`에 그 값이 있어야 한다.
- `ingredient` 축: 전성분 **앞 30% 안**에 그 성분이 있어야 한다(미량 성분으로 성분 배너 금지, 재설계 명세 I2).
- `clean` 축: `highlights`에 그 태그가 있어야 한다.
- `price_bin` 축: 그 밴드 안의 상품만. 8종은 전부 `~20`·`20-35` 두 밴드다.
- `segment` 축: `suitable_skin_types`에 그 타입이 있어야 한다.
- 한 화면에서 같은 상품이 히어로와 배너 행에 동시에 뜨지 않는다(`items`·`banners` 비중복 규칙 확장).

---

## 4. 만들 이미지 목록

파일명 규칙: `frontend/public/images/ssafy-beauty/{product_id}-{variant}[-{tone}].webp`. 마스터는 `{product_id}-m1.webp` 등. 기존 `{product_id}.svg`는 마스터가 들어오면 삭제.

| # | 묶음 | 장수 | 비율·크기 | 우선순위 | 비고 |
|---|---|---|---|---|---|
| A | 상품 마스터 M1 팩샷 | 8 | 1:1 · 1200×1200 | **P0** | 모든 변형의 참조 이미지. 이것부터 |
| B | 히어로 후보 4종(SB01·02·03·04) × V1·V2·V3 | 12 | 16:9 · 1600×900, 왼쪽 45% 세이프존 | **P0** | 히어로·배너 행 공용(행은 중앙 크롭 4:5) |
| C | 히어로 후보 4종 × V4 × 톤 5 | 20 | 16:9 | P1 | "같은 피부" 배너. 톤이 맞을 때만 |
| D | 나머지 4종(SB05~08) × V1·V2·V3 | 12 | 16:9 | P1 | SB05·08은 price, SB06은 ingredient가 주 |
| E | 나머지 4종 × V4 medium 1장 | 4 | 16:9 | P2 | 톤별은 하지 않음 |
| F | V5 브랜드 스토리(라인 플랫레이) | 3 | 16:9 | **P0** | 전용 칸 2개가 항상 뜬다. 3장을 돌려 씀. 상품별로 만들지 않음 |
| G | 제형 스와치 M2 | 8 | 1:1 | P1 | 상세 갤러리 2번째 |
| H | 사용 컷 M3 | 8 | 1:1 | P2 | 상세 갤러리 3번째 |
| 합계 | | **75** | | P0 = 23장 | |

P0 23장이면 시연이 성립한다(마스터 8 + 히어로 후보 배너 12 + 스토리 3). 나머지는 순서대로.

---

## 5. 이미지 생성 프롬프트

### 5-1. 브랜드 바이블 (모든 프롬프트 앞에 붙인다)

```
SSAFY Beauty, a small Korean skincare brand. Packaging system: matte off-white (ivory #FAF7F1)
containers with a single thin sage-green (#A8C96E) accent band, minimal sans-serif wordmark area
left blank (no legible text), soft-touch finish. Product line colors: "Zero Pore" line = sage green
accent; "PDRN Pink Peptide" line = soft blush pink accent (#F2C2CC); "Deep Vita C" = pale apricot
accent (#F5C89A); "Collagen Jelly" = translucent mint-aqua accent (#CFE9E3).
Photography: real product photography look, 3/4 front view unless stated, soft diffused studio
light from upper left, gentle natural shadow, warm ivory seamless background, shallow depth of
field, 85mm lens, true-to-life color, no text, no logos, no labels with letters, no watermark,
no people's faces.
```

**일관성 규칙(필수).**
1. §5-2 마스터 M1을 상품마다 먼저 뽑고 확정한다. 시드값(또는 생성 ID)을 기록한다.
2. 변형(V1~V5, M2, M3)은 **마스터를 참조 이미지로 걸어** 생성한다. Midjourney는 `--cref {마스터URL} --cw 100 --sref {마스터URL}`, GPT-image·Nano Banana는 마스터를 입력 이미지로 넣고 "keep the exact same product container, color, proportions and label placement" 를 붙인다. Stable Diffusion은 IP-Adapter 가중 0.8 이상 + 같은 시드.
3. 배경·소품·구도만 바꾸고 용기 형태·색·라벨 위치·마감은 바꾸지 않는다. 다르게 나오면 폐기.
4. 히어로(16:9)는 상품을 **오른쪽 55%** 에 두고 왼쪽 45%를 비운다. 문구가 거기 올라간다.
5. 네거티브(공통): `text, letters, typography, logo, watermark, face, before-after, arrows, percentages, price tag, discount sticker, medical, syringe, pills, cluttered background, oversaturated`.

> **생성 방식 변경(2026-09-09).** 장마다 따로 생성하지 않고 **§9 시트 방식**으로 간다. 한 장에 3~6개를 흰 배경 격자에 놓고 누끼를 따서 컷아웃으로 쓴다. 배너는 컷아웃을 합성해 만든다. 5-2~5-5의 개별 프롬프트는 컷아웃이 무엇을 그리나의 정의로 남기고, 실제 생성은 §9 시트 프롬프트로 한다.

### 5-2. 상품 마스터 M1 (8장, 1:1)

| ID | 프롬프트 (바이블 뒤에 이어 붙임) |
|---|---|
| SB000001-m1 | `A round matte ivory jar of daily toning pads, 155g size, wide low cylinder with a flat lid, sage-green accent band at the base of the lid, lid slightly ajar showing the edge of a stack of white embossed cotton pads inside, one pad resting against the jar showing its dotted embossed texture. Zero Pore line.` |
| SB000002-m1 | `A 30ml matte ivory glass dropper bottle with a pale apricot accent band and an ivory dropper cap, translucent window revealing tiny golden-orange vitamin C capsules suspended in a clear serum, standing upright. Deep Vita C line.` |
| SB000003-m1 | `A 30ml frosted ivory dropper bottle with a soft blush-pink accent band, the serum inside a faint natural pink (vitamin B12 tint) visible through a slim window, ivory dropper cap. PDRN Pink Peptide line.` |
| SB000004-m1 | `A 110ml squat matte ivory cream jar with a mint-aqua accent band and a flat ivory lid, lid lifted and set beside the jar, inside a glossy translucent bouncy jelly cream with a smooth dome surface. Collagen Jelly line.` |
| SB000005-m1 | `A 120g matte ivory soft squeeze tube of foaming cleanser standing on its flip cap, sage-green accent band near the cap, a small dense white foam dollop on the ivory surface beside it. Zero Pore line.` |
| SB000006-m1 | `A 50ml slim matte ivory tube of sun serum with a small ivory pump, sage-green accent band, a thin translucent white serum swipe beside it that dries clear with no white cast. Zero Pore line, SPF product.` |
| SB000007-m1 | `A 20ml slim matte ivory eye cream tube with a soft blush-pink accent band and a cool-touch rounded metal-look tip in brushed ivory, lying at a slight angle. PDRN Pink Peptide line.` |
| SB000008-m1 | `A single-use gel sheet mask pouch, matte ivory paper-touch sachet 30g with a soft blush-pink and mint-aqua dual accent band, lying flat with one corner slightly lifted, a translucent pink-tinted gel sheet mask partly visible beside it. PDRN Collagen Jelly line.` |

### 5-3. 변형 접미 프롬프트 (마스터 참조 + 아래 문장 추가)

각 변형은 `[바이블] + [해당 상품 M1 프롬프트] + [아래 접미] + --cref/참조 이미지` 로 만든다. 16:9, 상품 오른쪽 55%, 왼쪽 45% 여백.

| 변형 | 접미 프롬프트 |
|---|---|
| V1 price | `Composition for a wide banner 16:9: the product alone on the right 55% of the frame, generous empty ivory space on the left 45% for overlaid text, no props, calm and honest, the container's real size proportion is clear, soft single shadow.` |
| V2 ingredient | `Composition for a wide banner 16:9: product on the right 55%, left 45% empty. Around the base of the product a few natural ingredient props matching the formula: {INGREDIENT_PROPS}. Props are small, fresh, unstyled, not touching the label area. Feels like the ingredient list came to life, not a laboratory.` |
| V3 concern | `Composition for a wide banner 16:9: product on the right 55%, left 45% empty. Background is an abstract macro of healthy skin texture relevant to {CONCERN_CUE}, very softly blurred, warm ivory-to-skin gradient, no face, no before-after, no marks or redness, purely calm and tactile.` |
| V4 segment (톤별) | `Composition for a wide banner 16:9: a hand and forearm with {SKIN_TONE} skin tone enters from the right holding the product naturally, a small amount of product applied on the back of the hand showing its texture, no face, natural daylight from a window, left 45% of the frame empty ivory wall.` |
| V5 story | `Wide banner 16:9 flat lay from above of the complete SSAFY Beauty skincare line (8 products: toning pad jar, two 30ml dropper serums, 110ml jelly cream jar, 120g foam cleanser tube, 50ml sun serum tube, 20ml eye cream tube, sheet mask sachet) arranged loosely on an ivory linen cloth with a sprig of centella leaves and a small ceramic dish, products occupy the right 60%, left 40% empty, unhurried small-batch atelier feel, no hands, no text.` |
| M2 texture | `Square 1:1 macro swatch of the product's texture smeared on a matte ivory ceramic tile: {TEXTURE_CUE}. Product container blurred in the top corner for context, soft daylight, true color.` |
| M3 inuse | `Square 1:1: a hand with medium skin tone operating the container: {USE_CUE}. Close crop, no face, natural daylight, ivory background.` |

### 5-4. 상품별 치환값

| 상품 | `{INGREDIENT_PROPS}` (V2) | `{CONCERN_CUE}` (V3) | `{TEXTURE_CUE}` (M2) | `{USE_CUE}` (M3) |
|---|---|---|---|---|
| SB000001 | a few thin slices of willow bark and a small pile of pale lactic-acid-like crystalline powder, one small pad | refined pores and even texture, smooth matte skin | a wet embossed cotton pad pressed on the tile leaving a clear watery essence trail | fingers lifting one pad out of the jar with tweezers-free grip |
| SB000002 | a small cluster of fresh orange sea-buckthorn berries on a twig, a few loose golden capsules | brightening even tone, luminous but not glossy skin | a drop of clear serum with tiny burst golden capsules spreading | dropper releasing one drop onto the back of the hand |
| SB000003 | an abstract soft-pink translucent double-helix ribbon made of gel (no scientific labels), a few millet grains | firm bouncy skin with fine texture | a faint pink watery serum drop with a slight elastic sheen | dropper held above the hand, serum drop mid-air |
| SB000004 | a translucent mint jelly cube and two small collagen-like clear gel beads | plump hydrated skin | a bouncy translucent jelly dollop with a fingertip dent | fingertip lifting a dome of jelly cream from the jar |
| SB000005 | a sprig of fresh purslane (portulaca) and a single camellia flower | clean clear skin with minimized pores | a dense airy white foam swirl | hands lathering fine foam between palms |
| SB000006 | eight small clear water droplets in a neat row and a slice of citrus-free green leaf, warm sunlight patch | hydrated skin under sunlight, no white cast | a translucent milky-white serum swipe fading to clear at the edge | pumping one press of serum onto fingertips |
| SB000007 | a few coffee beans and a tiny abstract pink gel ribbon | rested bright under-eye area (skin only, no eye) | a small cream dab with a satin finish | tube tip gliding a dot of cream on the back of the hand |
| SB000008 | a translucent pink gel sheet draped over a glass dome, a tiny pink ribbon | plump dewy skin the morning after | a translucent pink gel sheet fragment with visible moisture beads | hands unfolding the gel mask from the sachet |

`{SKIN_TONE}` (V4): `fair porcelain` · `light` · `medium warm` · `tan` · `deep rich` 다섯 값. 파일명은 `-v4-fair` 등.

### 5-5. 완성 예시 두 개

**SB000002-v2 (성분 배너, 16:9)**
```
[바이블] A 30ml matte ivory glass dropper bottle with a pale apricot accent band and an ivory dropper
cap, translucent window revealing tiny golden-orange vitamin C capsules suspended in a clear serum,
standing upright. Deep Vita C line. Composition for a wide banner 16:9: product on the right 55%, left
45% empty. Around the base of the product a few natural ingredient props matching the formula: a small
cluster of fresh orange sea-buckthorn berries on a twig, a few loose golden capsules. Props are small,
fresh, unstyled, not touching the label area. Feels like the ingredient list came to life, not a
laboratory. Keep the exact same product container, color, proportions and label placement as the
reference image. --ar 16:9 --cref {SB000002-m1} --cw 100 --no text, letters, logo, face, before-after
```

**SB000001-v4-medium (같은 피부 배너, 16:9)**
```
[바이블] A round matte ivory jar of daily toning pads, 155g, sage-green accent band, lid ajar with
embossed cotton pads. Zero Pore line. Composition for a wide banner 16:9: a hand and forearm with medium
warm skin tone enters from the right holding one toning pad naturally against the back of the other hand
showing its dotted texture, jar standing beside, no face, natural daylight from a window, left 45% of
the frame empty ivory wall. Keep the exact same product container as the reference image. --ar 16:9
--cref {SB000001-m1} --cw 100 --no text, letters, logo, face, before-after
```

### 5-6. 검수 체크리스트 (한 장마다)

- 용기 형태·색·액센트 밴드 위치가 마스터와 같다
- 글자·로고·숫자가 없다 (있으면 폐기, 그리기 금지)
- 히어로는 왼쪽 45%가 비어 있다
- V3에 얼굴·전후·붉은 표시가 없다
- 색이 오버새처레이션 없이 아이보리 톤 안에 있다
- WebP, 1600×900 또는 1200×1200, 200KB 이하

---

## 6. 프론트 구현 메모 (이 문서 다음 작업)

- `lib/bannerCreative.ts`: `(product_id, banner_type, skin_tone?) → 이미지 경로`. 매핑 `banner_type → variant` 는 §2 표. 파일이 없으면 마스터 M1로 폴백(플레이스홀더 금지).
- `HeroBanner`·`BannerRow`가 `product.image_url` 대신 `bannerCreative()`를 쓴다. `data-*`는 그대로.
- 세이프존 규칙을 CSS로 강제: 히어로 문구 컨테이너 `width: 45%`, 이미지 `object-position: right`.
- `products.ssafy-beauty.json`의 `images[]`에 M1·M2·M3 세 장을 넣는다. 상세 갤러리가 이미 `images[]`를 읽는다.
- 로그: 어떤 변형이 떴는지는 `banner_type`으로 1:1 식별된다. 톤별 V4는 `banner_value`(segment 값)로 식별.

### 6-1. 구현 이후 바뀐 것 (2026-09-10)

**완성형 배너 이미지를 지원한다.** 글자·가격·CTA 가 이미지 안에 구워진 한 장이 있으면
CSS 조립 대신 그 이미지를 그대로 쓴다 (`AdBanner` 의 `ad--image` 경로). 목록은
`src/mocks/banner-images.json` 이고, 없는 상품·변형은 지금처럼 CSS 로 조립한다.

| 상품 | 등록 | 파일 | 비고 |
|---|---|---|---|
| SB000001 제로 포어 토닝 패드 | 5변형 | **없음** | 폴백으로 조립 배너가 뜬다 |
| SB000002 딥 비타C 캡슐 세럼 | 5변형 | **없음** | 〃 |
| SB000003 PDRN 핑크 펩타이드 세럼 | 5변형 | 5장 | 2172×724 |
| SB000004 콜라겐 젤리 크림 | 5변형 | 5장 | price 만 3:1, 나머지 넷은 2375×662 |
| SB000005 제로 포어 폼 클렌저 | 5변형 | 5장 | 2172×724 |
| SB000006 제로 포어 모이스처 선 세럼 | 5변형 | 5장 | 2172×724 |
| SB000007 · SB000008 | 미등록 | — | 조립 배너로 뜬다 |

**목록에 있는데 파일이 없으면 조립 배너로 돌아간다.** 목록은 "무엇이 있다고 주장하는가"
일 뿐 파일 존재를 보장하지 않는다 (브라우저가 미리 알 수 없어 목록을 두는 것이다).
전에는 폴백이 없어서 SB000001·SB000002 자리에 깨진 이미지 한 칸이 떴다. 지금은
`<img onError>` 가 그 주소만 기억하고 CSS 조립으로 되돌린다.

이 경로에는 세이프존 CSS 가 적용되지 않는다. 자르면 구워진 글자가 잘리므로
**`aspect-ratio: 3 / 1` 틀에 `object-fit: contain` 으로 담기만 한다.**

- 높이를 고정하면 폭 1120px 에서 위아래가 깎여 상단 브랜드명과 하단 상품명이 잘렸다.
- `cover` 도 못 쓴다. 들어오는 그림이 전부 3:1 은 아니다 — SB000004 네 장이 3.59:1 이라
  좌우 8% 씩 깎여 "SSAFY BEAUTY" 와 신상품 배지가 날아갔다.
- 그렇다고 `aspect-ratio` 를 떼고 **그림 비율을 따라가게 하면 안 된다.** `useImpression`
  의 노출 판정이 `IntersectionObserver` threshold 0.5 — "요소 자신의 50%" 라서, 배너
  높이가 변형마다 다르면 노출로 인정되는 난이도가 축마다 달라진다. `banner_daily` 가
  재려는 것이 축별 CTR 인데 분모가 그림 비율에 따라 움직이면 "concern 축이 먹혔다" 가
  아니라 "concern 그림이 납작했다" 를 재게 된다.

그래서 틀은 고정하고 담는다. 비율이 다른 그림은 위아래에 아이보리(`#FAF7F1`) 여백이
생기는데 배경과 같은 색이라 패딩처럼 보인다. **새로 뽑을 때는 2172×724 (정확히 3:1)**
로 맞춘다 — 여백이 사라지고 CSS 는 그대로 둔다.

**WebP 로 넣는다** (§5-6 검수 기준 그대로). 생성기가 PNG 를 주므로 변환해서 넣는다.
원본 PNG 15장이 20.3MB 였고 q90 WebP 로 1.26MB(최대 106KB) 가 됐다 — 15배다. 글자가
구워져 있어 품질을 확인했는데 q90 에서 육안 차이가 없다. PNG 채로 두면 히어로 한 장에
1.4MB 를 태우고 저장소도 그만큼 무거워진다.

**로그에 property 두 개가 늘었다** (데이터 파트 회신 2026-09-10). `trait_source` 는
노출에도 실어야 하고(20% 탐색군 비중의 분모), `policy_version` 은 `banner_daily` 에서
정책 배포 전후를 자르는 귀속 키다. `banner_slot` 은 1 이상이어야 한다.

**상품 마스터 컷의 누끼는 쓰지 않는다.** 누끼가 제품의 흰 부분까지 뜯어내 병 몸통과
스포이드 캡에 구멍을 냈고 잘린 소품 조각이 옆에 남았다. 원본이 이미 흰 배경이라 딸
이유가 없다. `frontend/scripts/slice_master_grid.py` 가 2x2 마스터 그리드를 네 칸으로
자르고 흰 여백만 걷어 정사각 캔버스 한가운데 앉힌다. 배경은 지우지 않는다.
제형 컷(M2)은 멀쩡하므로 건드리지 않는다.

그리드 원본 4장은 `frontend/scripts/data/master-grid/` 에 `grid-a`~`grid-d` 로 둔다.
**이 경로는 `.gitignore` 의 `data/` 규칙에 걸려 저장소에 올라가지 않는다** — 다시 자르려면
원본을 따로 받아야 한다. 결과물(`public/images/ssafy-beauty/*.webp`)만 커밋된다.
`grid-a` = SB01~04 개봉·사용(→M3), `grid-b` = SB05~08 팩샷(→M1),
`grid-c` = SB01~04 팩샷(→M1), `grid-d` = SB05~08 개봉·제형(→M3).
16장을 `--write` 로 덮어쓴다 (2026-09-10 복구 완료, 전부 1200×1200).

**넘어온 조각을 걸러낸다 (2026-09-10 추가).** 4등분만 하면 이웃 칸 제품이 경계를
넘어온 조각까지 딸려온다 — SB000002-m3 에 옆 칸 토닝 패드 조각이 왼쪽에 남았다.
그렇다고 "가장 큰 덩어리만" 남기면 안 된다. 토닝 패드 컷은 **뚜껑·용기·패드가 따로
떨어진 세 덩어리**이고 셋 다 제품이다. 구분선은 **칸 경계에 잘렸는가** 다 — 넘어온
조각은 칸 가장자리에서 끊겨 있고 제 소품은 칸 안에 온전히 들어 있다. 그래서 가장자리에
닿은 덩어리는 버리되 가장 큰 덩어리는 남긴다(제품 본체가 가장자리에 닿는 컷도 있다).
라벨링에 `scipy.ndimage` 를 쓰고, 없으면 예전처럼 통째 경계로 폴백한다.

`images[]` 의 첫 장은 `image_url` 과 같은 주소다. 상세 갤러리는 주소가 같으면 한 장으로
센다 — 그대로 이으면 첫 장이 썸네일에 두 번 나오고 세 장짜리가 네 장으로 보였다.

---

## 7. 파트별 전달 메시지

### 7-1. AI 파트 (규원님) — 배너 크리에이티브와 API

> 규원님, 배너 이미지를 성향별로 다르게 만들려고 계획을 정리했습니다(docs/planning/ssafy-beauty-creative-plan.md). API 쪽 확인 세 가지만요.
>
> 1. 이미지 변형은 프론트가 `banner_type`으로 고릅니다. 7종을 5변형으로 묶었어요: `ingredient`+`clean` → 성분 강조, `concern`+`category` → 고민 강조, `price_bin` → 가격, `segment` → 같은 피부(톤별), `new_brand` → 브랜드 스토리. API는 바꿀 것 없고, `hero`에도 `banner_type`이 항상 오는지만 확인 부탁드려요(§5-1 예시엔 있음).
> 2. 성분 축 배너는 그 성분이 전성분 **앞 30% 안**에 있는 상품에만 붙이고 싶습니다. 미량 성분으로 성분 배너를 만들면 재설계 명세 I2(미량 경고)와 충돌해서요. `banners[].banner_type=ingredient`를 고를 때 위치가중 ≥ 0.3인 상품만 후보로 잡아 주실 수 있나요? 어렵으면 프론트가 받아서 걸러도 됩니다.
> 3. SSAFY Beauty 8종은 로그·리뷰가 없어 축 배너(slot 1~4)엔 거의 안 오르고 `new_brand` 칸(5~6)에만 뜰 것 같습니다. 시연에서 히어로에 SB 상품이 한 번은 뜨게 하려면 생성기에 SB 8종을 넣는 결정 B가 필요한데, 대시보드는 결정 A로 가기로 했으니 **배너용으로만** SB를 후보에 넣는 게 가능한지 의견 주세요. 안 되면 시연은 전용 칸으로만 가겟습니다.

### 7-2. 데이터 파트 (은솔님) — 로그 식별과 실험

> 은솔님, 배너 이미지를 `banner_type`별로 다르게 만들 계획입니다. 로그 쪽 확인 두 가지요.
>
> 1. 어떤 이미지 변형이 노출됐는지는 `banner_type`(+`segment`면 `banner_value`)으로 1:1 식별됩니다. 그래서 **새 property는 안 넣습니다.** 나중에 같은 `banner_type` 안에서 이미지 A/B를 돌리게 되면 그때 `creative_id`(선택) 추가를 제안드릴게요. 지금 계약 §3.11~3.13 그대로 갑니다.
> 2. `banner_daily`에서 `banner_type × trait_source` 로 CTR을 잘라 보고 싶습니다. "성향에 맞는 강조(profile/session)가 탐색군(explore)보다 CTR이 높은가"가 이 작업의 검증 질문이라서요. 그 grain이 마트에 있는지, 없으면 추가 가능한지 봐 주세요. `policy_version`도 같이 실을게요(`banner_sort_v1`).

### 7-3. 백엔드 (민우님) — 이미지 자산과 상품 API

> 민우님, SSAFY Beauty 8종 실제 이미지(팩샷·제형·사용 컷 3장씩)와 배너 이미지(상품×변형, 최대 75장)를 만듭니다. 백엔드 쪽 두 가지요.
>
> 1. 상품 API(Jira 140)의 `Product`에 `image_url` 외에 `images[]`(문자열 배열, 순서 = 갤러리 순서)가 있는지 확인 부탁드려요. 프론트 타입엔 이미 있고 상세 갤러리가 읽습니다. 등록 폼(Jira 159)도 나중에 이미지 여러 장을 올리게 됩니다.
> 2. 정적 자산 경로를 정해 주세요. 지금은 프론트 `public/images/ssafy-beauty/{product_id}-{variant}.webp`로 두는데, 실제 브랜드가 등록하면 서버가 받아 저장해야 하니 `/static/brands/{brand_id}/{product_id}/{name}.webp` 같은 규칙과 업로드 API(용량·확장자 제한)를 정해 두면 프론트가 거기에 맞춰 경로 헬퍼를 짜겟습니다. 시연 전까지는 프론트 정적 파일로 갑니다.

---

## 8. 이 문서에서 결정한 것 · 남은 것

| 결정 | 내용 |
|---|---|
| 변형 5종 | price · ingredient · concern · segment(톤별) · story. `banner_type` 7종을 묶음 |
| 글자 없음 | 이미지에 텍스트 금지. 문구는 프론트 |
| 세이프존 | 히어로 왼쪽 45% |
| P0 23장 | 마스터 8 + 히어로 후보 4종×V1·V2·V3 12 + 스토리 3 |
| 일관성 | 마스터 참조 이미지 필수, 시드 기록 |

| 남은 것 | 누가 |
|---|---|
| 이미지 생성 도구 선택(Midjourney / GPT-image / Nano Banana)과 크레딧 | 유림 |
| SB 배너 후보 포함 여부(7-1 ③) | AI |
| `banner_type × trait_source` CTR grain | 데이터 |
| `images[]`·업로드 경로 | 백엔드 |
| "외형(사용감)을 따지는" 성향은 지금 5종에 없다. `texture` 태그 5종은 상품 쪽에만 있고 사용자 신호(`media_view`·`variant_select(shade)`)로 성향을 만들려면 가중치 표 개정이 필요 | v2, AI·데이터와 협의 |


---

## 9. 시트 방식 — 한 장에 3~6개, 누끼 따서 합성

### 9-1. 왜 시트인가

- 한 번에 많이 생성하면 품질과 일관성이 흔들린다. 시트 한 장 안의 항목은 같은 조명·같은 카메라·같은 색 처리를 받으므로 **시트 안에서는 저절로 일관**된다.
- 컷아웃(누끼)을 한 번 따 두면 가격·성분·고민·같은 피부·스토리 다섯 변형 전부에 **같은 상품 컷아웃**을 쓴다. 변형마다 상품을 다시 그리지 않으니 "다른 변형에서 다른 물건"이 되는 일이 없다.
- 배너 = `배경 타일` + `상품 컷아웃` + `소품 컷아웃` + `프론트 문구`. 합성은 Figma·Photoshop 또는 CSS 레이어. 배경만 바꾸면 변형이 바뀐다.

### 9-2. 시트 목록 (12장으로 75개 자산을 뽑는다)

| 시트 | 담는 것 | 칸 | 배경 | 결과물 |
|---|---|---|---|---|
| S1 상품 A | SB01 패드 · SB02 비타C 세럼 · SB03 PDRN 세럼 · SB04 젤리 크림 (3/4 정면) | 2×2 | 순백 | M1 팩샷 4 |
| S2 상품 B | SB05 폼 클렌저 · SB06 선 세럼 · SB07 아이크림 · SB08 마스크 파우치 | 2×2 | 순백 | M1 팩샷 4 |
| S3 상품 디테일 A | SB01~04 "열림·사용 상태"(뚜껑 연 패드, 스포이드 뺀 세럼 2, 뚜껑 연 크림) | 2×2 | 순백 | M3 재료 4 |
| S4 상품 디테일 B | SB05~08 사용 상태(거품 올린 튜브, 펌프 누른 선 세럼, 팁 보이는 아이크림, 파우치 열고 겔 시트 반쯤) | 2×2 | 순백 | M3 재료 4 |
| S5 제형 A | SB01~04 스와치(패드 에센스 자국, 캡슐 세럼 방울, 핑크 세럼 방울, 젤리 덩어리) | 2×2 | 순백 | M2 4 |
| S6 제형 B | SB05~08 스와치(거품 소용돌이, 반투명 선세럼 스와이프, 크림 점, 겔 시트 조각) | 2×2 | 순백 | M2 4 |
| S7 성분 소품 A | 비타민나무 열매 · 버드나무 껍질 · 락틱 결정 가루 · 골든 캡슐 · 핑크 젤 나선 · 기장 | 2×3 | 순백 | V2 소품 6 |
| S8 성분 소품 B | 민트 젤리 큐브 · 투명 젤 비드 · 쇠비름 · 동백꽃 · 물방울 8개 · 커피콩 | 2×3 | 순백 | V2 소품 6 |
| S9 손 A | 손등 위 세럼 방울 · 손바닥 거품 · 젤리 뜨는 손가락 × 톤 fair·light | 2×3 | 순백 | V4·M3 손 6 |
| S10 손 B | 같은 동작 × 톤 medium·tan·deep | 2×3 | 순백 | V4·M3 손 6 |
| S11 배경 타일 A | 고민 큐 추상 피부 질감 6종(모공 정돈·밝은 톤·탄력·촉촉함·맑음·눈가) | 2×3 타일 | 칸이 배경 | V3 배경 6 |
| S12 배경 타일 B | 아이보리 그라데이션 2 · 리넨 플랫레이 2 · 창가 햇빛 벽 2 | 2×3 타일 | 칸이 배경 | V1·V4·V5 배경 6 |

S1~S10은 컷아웃용(순백 배경), S11~S12는 타일용(칸 자체가 배경). 브랜드 스토리 V5는 S1·S2 컷아웃 8개를 S12 리넨 타일 위에 플랫레이로 배치해 만든다.

### 9-3. 시트 공통 프롬프트 (모든 시트 앞에)

```
[SSAFY Beauty 브랜드 바이블 §5-1 그대로]
Layout: ONE image containing a clean {ROWS}x{COLS} grid of {N} separate items, each item centered in
its own invisible cell, equal cell size, generous even spacing, items never touch or overlap, same
camera height and same soft studio lighting for every item, same scale so relative sizes are true.
Background: pure solid white #FFFFFF everywhere, no gradient, no vignette, no surface horizon line,
no cell borders, no numbers, no text. Shadows: none or a very faint soft contact shadow directly
under each item only. Each item fully inside its cell with margin, nothing cropped.
Purpose: product photography for background removal (cut-out), so edges must be crisp and fully
visible, no motion blur, no reflections bleeding into the background.
Negative: text, letters, numbers, logo, watermark, face, people, table edge, horizon, gradient
background, colored background, overlapping items, cropped items, duplicate items.
```

**칸 순서 규칙.** 왼쪽 위부터 오른쪽으로, 그다음 줄. 결과를 `S1-1.webp`처럼 자른 뒤 §9-4 표대로 이름을 바꾼다. 모델이 순서를 바꾸면 눈으로 맞춘다. 같은 물건이 두 번 나오거나 하나가 빠지면 그 시트는 다시 생성한다.

**도구 메모.** Midjourney·GPT-image·Nano Banana 모두 투명 배경은 직접 못 만든다. 순백 배경으로 뽑고 remove.bg·Photoshop "피사체 선택"·Figma 플러그인으로 딴다. 격자 배치는 GPT-image가 가장 잘 지키고, Midjourney는 `--ar 3:2 --style raw --stylize 50`으로 사실적으로 둔다. 상품 시트(S1·S2)를 먼저 확정하고 S3~S6는 그 시트를 참조 이미지로 걸어 용기를 맞춘다.

### 9-4. 시트별 프롬프트와 칸 매핑

**S1 · 상품 A** (2×2, 1:1)
```
[공통] Items in reading order: (1) a round matte ivory jar of daily toning pads, 155g, wide low
cylinder, flat lid closed, sage-green accent band at the base of the lid, Zero Pore line; (2) a 30ml
matte ivory glass dropper bottle, pale apricot accent band, ivory dropper cap on, a slim translucent
window showing tiny golden-orange vitamin C capsules in clear serum, Deep Vita C line; (3) a 30ml
frosted ivory dropper bottle, soft blush-pink accent band, faint natural pink serum visible through
a slim window, ivory dropper cap on, PDRN Pink Peptide line; (4) a 110ml squat matte ivory cream jar,
mint-aqua accent band, flat ivory lid closed, Collagen Jelly line. All four from the same 3/4 front
angle, standing upright.
```
칸 1~4 → `SB000001-m1` · `SB000002-m1` · `SB000003-m1` · `SB000004-m1`

**S2 · 상품 B** (2×2)
```
[공통] Items in reading order: (1) a 120g matte ivory soft squeeze tube of foaming cleanser standing
upright on its flip cap, sage-green accent band near the cap, Zero Pore line; (2) a 50ml slim matte
ivory tube of sun serum with a small ivory pump, sage-green accent band, Zero Pore line; (3) a 20ml
slim matte ivory eye cream tube with a soft blush-pink accent band and a rounded brushed-ivory
cool-touch tip, standing upright; (4) a single-use sheet mask sachet, matte ivory paper-touch 30g,
soft blush-pink and mint-aqua dual accent band, standing upright leaning slightly. Same 3/4 front
angle as sheet S1, same scale (the 120g tube is the tallest).
```
칸 1~4 → `SB000005-m1` · `SB000006-m1` · `SB000007-m1` · `SB000008-m1`

**S3 · 상품 디테일 A** (2×2, S1을 참조 이미지로)
```
[공통] Same four products as the reference sheet, identical containers, now in open / in-use state:
(1) the toning pad jar with its lid lifted and set beside it, a stack of white embossed cotton pads
visible, one pad leaning on the jar; (2) the Deep Vita C dropper bottle with the dropper lifted out and
held just above the bottle neck (no hand), one clear drop with tiny golden capsules forming at the tip;
(3) the PDRN pink serum bottle with dropper lifted the same way, a faint pink drop at the tip; (4) the
jelly cream jar with lid off beside it, the glossy translucent jelly dome inside with one fingertip-
sized dent. Keep exact container shapes, colors and accent bands from the reference.
```
칸 1~4 → `SB000001..04-m3-src`

**S4 · 상품 디테일 B** (2×2, S2 참조)
```
[공통] Same four products as the reference sheet, in use: (1) the foam cleanser tube with a dense airy
white foam dollop sitting on its cap top; (2) the sun serum tube with the pump pressed, a small milky-
translucent bead of serum at the nozzle; (3) the eye cream tube with a tiny satin cream dot at the
metal-look tip; (4) the mask sachet torn open at the top with a translucent pink gel sheet mask partly
pulled out and draped over the edge. Keep exact containers from the reference.
```
칸 1~4 → `SB000005..08-m3-src`

**S5 · 제형 A** (2×2)
```
[공통] Four skincare texture swatches placed directly on the white background as if on a white tile:
(1) a wet embossed round cotton pad pressed flat leaving a clear watery essence trail beside it; (2) a
single clear serum drop spreading, with tiny burst golden-orange capsule specks inside; (3) a faint
natural-pink watery serum drop with a slight elastic sheen; (4) a bouncy translucent mint-tinted jelly
cream dollop with a soft fingertip dent. Macro, true color, crisp edges.
```
칸 1~4 → `SB000001..04-m2`

**S6 · 제형 B** (2×2)
```
[공통] Four texture swatches on white: (1) a dense airy white cleansing foam swirl; (2) a translucent
milky-white sun serum swipe that fades to clear at its edge, no white cast at the thin end; (3) a small
ivory cream dab with a satin finish and a soft ridge; (4) a fragment of translucent pink gel sheet mask
with visible moisture beads on its surface. Macro, crisp edges.
```
칸 1~4 → `SB000005..08-m2`

**S7 · 성분 소품 A** (2×3, 3:2)
```
[공통] Six small natural props for skincare ingredient storytelling: (1) a short twig with a cluster
of fresh orange sea-buckthorn berries; (2) three thin dried slices of white willow bark; (3) a small
neat pile of fine pale crystalline powder; (4) six loose translucent golden gel capsules; (5) an
abstract soft-pink translucent gel ribbon curled into a loose double-helix shape, no labels, no
scientific look; (6) a small scattered pinch of millet grains. Each prop compact, fresh, unstyled.
```
| 칸 | 파일 | 쓰는 상품 |
|---|---|---|
| 1 | prop-seabuckthorn | SB02 |
| 2 | prop-willowbark | SB01 |
| 3 | prop-lactic-powder | SB01 |
| 4 | prop-capsules | SB02 |
| 5 | prop-pink-helix | SB03 · SB07 · SB08 |
| 6 | prop-millet | SB03 |

**S8 · 성분 소품 B** (2×3)
```
[공통] Six props: (1) a translucent mint-aqua jelly cube; (2) two clear soft gel beads; (3) a fresh
sprig of purslane (portulaca oleracea) with plump leaves; (4) a single pale-pink camellia flower with
two leaves; (5) eight clear water droplets in a neat straight row on the white surface; (6) five roasted
coffee beans loosely grouped. Compact, fresh, no dishes or bowls.
```
| 칸 | 파일 | 쓰는 상품 |
|---|---|---|
| 1 | prop-jelly-cube | SB04 · SB08 |
| 2 | prop-gel-beads | SB04 |
| 3 | prop-purslane | SB05 |
| 4 | prop-camellia | SB05 |
| 5 | prop-droplets | SB06 |
| 6 | prop-coffee | SB07 |

**S9 · 손 A** (2×3, 톤 fair·light)
```
[공통] Six cropped hand-and-forearm shots for compositing, no face, no sleeves, plain skin, natural
relaxed poses, entering the cell from the right edge, each cut cleanly at the forearm: (1) fair
porcelain skin tone, back of hand up with one clear serum drop resting on it; (2) fair tone, open palm
with a small mound of dense white foam; (3) fair tone, index finger lifting a small dome of translucent
jelly cream toward the viewer; (4) light skin tone, same pose as 1; (5) light tone, same as 2; (6) light
tone, same as 3. Natural daylight, soft, realistic skin texture, no jewelry, no nail polish.
```
칸 → `hand-fair-drop` · `hand-fair-foam` · `hand-fair-jelly` · `hand-light-drop` · `hand-light-foam` · `hand-light-jelly`

**S10 · 손 B** (2×3, 톤 medium·tan·deep, S9 참조)
```
[공통] Six cropped hand-and-forearm shots as in the reference sheet, same three poses: (1) medium warm
skin tone, serum drop on back of hand; (2) medium, foam in palm; (3) tan skin tone, serum drop;
(4) tan, foam in palm; (5) deep rich skin tone, serum drop; (6) deep, finger lifting jelly cream.
Natural daylight, realistic skin texture, no jewelry, no nail polish.
```
칸 → `hand-medium-drop` · `hand-medium-foam` · `hand-tan-drop` · `hand-tan-foam` · `hand-deep-drop` · `hand-deep-jelly`

**S11 · 배경 타일 A · 고민 큐** (2×3 타일. 칸이 배경이라 흰 배경 규칙 대신 아래)
```
[바이블 색만] ONE image divided into a 2x3 grid of six seamless full-bleed abstract background tiles,
thin white gutters between tiles, no text. Each tile is an extreme soft-focus macro of healthy skin
texture, warm ivory-to-skin gradient, calm and tactile, no face, no pores marked, no redness, no
before-after: (1) smooth refined even-texture skin, matte; (2) softly luminous even-toned skin,
gentle glow not glossy; (3) firm bouncy skin with fine texture, warm light; (4) dewy well-hydrated
skin with tiny moisture beads; (5) clean clear skin in soft daylight; (6) rested smooth under-eye
area skin only, no eye visible.
```
칸 → `bg-concern-pores` · `bg-concern-tone` · `bg-concern-firm` · `bg-concern-hydration` · `bg-concern-clear` · `bg-concern-eye`

**S12 · 배경 타일 B · 무드** (2×3 타일)
```
[바이블 색만] ONE image divided into a 2x3 grid of six seamless full-bleed background tiles, thin white
gutters, no text, no objects: (1) plain warm ivory #FAF7F1 seamless with a very soft top-left light
falloff; (2) the same ivory with a faint sage-green tint at the lower right; (3) natural ivory linen
cloth flat lay seen from above, soft folds; (4) the same linen with a sprig of centella leaves in one
corner and a small ivory ceramic dish; (5) an ivory plaster wall with a soft diagonal patch of window
daylight; (6) the same wall with a longer, warmer late-afternoon light patch.
```
칸 → `bg-ivory-plain` · `bg-ivory-sage` · `bg-linen` · `bg-linen-props` · `bg-wall-light` · `bg-wall-warm`

### 9-5. 합성 규칙 (컷아웃 → 배너)

```
V1 price      = bg-ivory-plain   + {상품 m1}                 상품 오른쪽 55% 크게, 소품 없음
V2 ingredient = bg-ivory-sage    + {상품 m1} + 소품 1~2       소품은 상품 아래·옆, 라벨 안 가림
V3 concern    = bg-concern-{큐}  + {상품 m1}                 배경 불투명도 40%로 가라앉힘
V4 segment    = bg-wall-light    + {손 컷 톤별} + {상품 m1}   손이 상품을 든 것처럼 겹침, 손 위에 m2 소량
V5 story      = bg-linen-props   + 8종 m1 플랫레이            오른쪽 60% 느슨하게, 왼쪽 40% 비움
M2 texture    = 컷아웃 그대로 1:1 (흰 배경 유지)
M3 inuse      = {손 컷} + {상품 m3-src} 합성 1:1
```

공통: 히어로 16:9는 왼쪽 45% 비움, 배너 행은 같은 파일을 중앙 기준 4:5로 자름. 그림자는 컷아웃에 딸린 접촉 그림자만 쓰고 새로 그리지 않는다. 색 보정은 시트 단위로 한 번(전체 톤 일치), 개별 컷아웃 보정 금지.

### 9-6. 순서

1. S1·S2 생성 → 용기 8종 확정. 재생성 반복은 여기서만. 시드·생성 ID 기록
2. S3~S6 (S1·S2 참조) → 사용 상태·제형
3. S7·S8 소품, S11·S12 배경
4. S9·S10 손
5. 컷아웃 → §9-5 합성 → P0 23장 먼저 (m1 8 + 히어로 후보 V1·V2·V3 12 + V5 3)


---

## 10. 올리브영 배너 디자인 관행 — 2026-09-09 직접 관찰

올리브영 온라인몰(oliveyoung.co.kr) 메인을 직접 열어 롤링 배너 16장 중 5장, Weekly Special 타일, "오직 올리브영에서만" 소형 배너 3종, 상품 카드 배지를 봤다. 아래는 화면에서 확인한 것만 적었다. 픽셀 값은 화면 비율에서 읽은 근사치다.

### 10-1. 메인 롤링 배너(히어로) — 우리 히어로가 따를 형식

| 요소 | 관찰 | 값(근사) |
|---|---|---|
| 비율·크기 | 가로로 긴 한 칸, 카테고리 메뉴 오른콝. 약 940×640, 3:2에 가깝다 | 3:2 |
| 배경 | 슬라이드마다 **파스텔 단색 또는 부드러운 그라데이션 한 장**(하늘색·라벤더·핑크·아이보리·연회색). 사진 배경이면 물결·매끈한 바닥처럼 질감 하나만. 텍스트 뒤는 항상 차분하다 | 슬라이드당 1색 |
| 좌우 배치 | **왼쪽 45~50% 텍스트, 오른쪽 50~55% 상품**. 상품은 2~3개가 장면 안에 서 있고 오른쪽 가장자리에서 일부 잘린다 | 텍스트 좌 · 상품 우 |
| 킥커 | 맨 위 작은 굵은 글씨 1줄 + 짧은 가로선(대시) | "올영PICK", "올리브영 X 산리오" 14~16px Bold |
| 헤드라인 | **3줄**, 매우 크게, 굵기는 Regular~Medium(볼드 아님). 차콜. 줄마다 5~8자 | 56~64px, 행간 1.15 |
| 서브 카피 | 헤드라인 아래 1줄, 중간 굵기, 회색~차콜 | 18~20px Medium |
| 가격·배지 | **히어로에는 없다.** 가격·할인·배지는 상품 카드 몫 | 없음 |
| 기타 | 캐릭터 콜라보면 저작권 문구가 우하단 8~10px. 캐러셀 컨트롤(이전·n/16·다음·일시정지)은 좌하단 | |

**헤드라인 문형(관찰 5개).**
- 상황·고민 → 변화 → 카테고리 명사: "메마른 피부도 / 촉촉하게 바꾸는 / 수분진정 솔루션"
- 콜라보 → 감정: "산리오캐릭터즈와 / 매일 똑같은 / 일상도 특별하게"
- 시즌 → 묶음 명사: "~ 더모 시너지" + 서브 "9월의 더모 BEST 모아보기"
- 루틴 제안: "~ 티 리추얼" + 서브 "쿠폰&특가"
- 무드: "~ 최애 무드" + 서브 "산리오캐릭터즈 거울 키링 증정"

공통: **명사로 끝난다**(솔루션·시너지·리추얼·무드). 서술형 종결("~하세요")이 없다. 서브 카피가 기간·혜택·컬렉션을 맡고 헤드라인은 감정·효능만 맡는다.

### 10-2. Weekly Special 타일(2단) — 우리 배너 행이 따를 형식

| 요소 | 관찰 |
|---|---|
| 비율 | 약 730×530, 4:3에 가까운 가로 타일 2개 나란히 |
| 이미지 | 상품 여러 개가 **장면 안**에 놓인 사진(구름 모양 오브제, 파스텔 바닥, 소품). 상품이 타일의 60~70%를 차지 |
| 텍스트 | **하단 중앙 정렬**, 아래쪽에 어두운 그라데이션을 깔아 흰 글씨. 헤드라인 2줄 Bold 28~32px, 서브 1줄 18px |
| 문형 | 감정 과장형 허용: "귀여움 한도초과! / 역대급 혜택 한가득" + 서브 "메이크프렘 with 폼폼푸린" |
| 로고 | 우상단 "OLIVE YOUNG × Sanrio" 소형 |

### 10-3. 소형 배너(3단, "오직 올리브영에서만")

| 요소 | 관찰 |
|---|---|
| 비율 | 약 470×200, 가로 2.3:1 |
| 배경 | 파스텔 단색(핑크·라벤더·민트) 각각 다르게 |
| 배치 | 왼콝 텍스트, 오른쪽 상품 컷아웃 1~2개(부드러운 그림자) + 작은 캐릭터 |
| 텍스트 | 헤드라인 **2줄 Bold** 22~24px 차콜, 서브 1줄 13px(해시태그 "#헬로키티 #한교동" 또는 "9/7~ 키티타포린백 증정★") |

### 10-4. 상품 카드와 배지 — 배너 밖에서 쓰는 것

| 요소 | 관찰 |
|---|---|
| 이미지 위 스티커 | 원형 "올영 PICK"(연두), "ONLY 올리브영 단독기획"(연두), "베스트"(빨강 원), 큰 숫자 "1등", 원형 "재구매 1위"·"한정 기획" |
| 상품명 | 대괄호 접두 "[9월 올영픽/산리오콜라보]", "[한정기획출시/1등퍼프]" 뒤에 브랜드·상품명 |
| 가격 | 정가 취소선 회색 + 판매가 **빨강 Bold** 큼 |
| 필 배지 | 세일(빨강) · 오늘드림(핑크) · 쿠폰(연두) · 증정(하늘) 라운드 필, 12px |

### 10-5. 우리 배너에 적용 — 바꾸는 것과 지키는 것

| 항목 | 올리브영 | 우리 적용 | 이유 |
|---|---|---|---|
| 히어로 배경 | 파스텔 단색·그라데이션 한 장 | **같이 간다.** 변형별 파스텔 1색: 가격=아이보리, 성분=세이지 틴트, 고민=변형 큐 파스텔(하늘·라벤더·블러시), 같은 피부=따뜻한 살구, 스토리=리넨 | 텍스트 뒤가 차분해야 3줄 헤드라인이 읽힌다 |
| 히어로 배치 | 좌 텍스트 45% · 우 상품 55% | **같다.** 이미 세이프존 45%로 잡아 둔 것과 일치 | |
| 헤드라인 | 3줄, 56~64px, Regular~Medium, 명사 종결 | **바꾼다.** `bannerCopy`가 지금 1줄("{성분}이 들어간")이라 3줄 명사형으로 확장. 굵기는 Medium(500) | 볼드 3줄은 광고처럼 읽힌다. 올리브영도 굵기를 낮췃다 |
| 킥커 | 작은 Bold + 대시 | **같다.** 킥커 = 축 이름("성분으로 고르기", "피부 고민", "새로 입점") | 이미 `copy.kicker`가 있다 |
| 서브 카피 | 기간·혜택·컬렉션 | **바꾼다.** 우리는 할인·기간이 없으니 서브 = 가격·용량 또는 근거 한 줄(추천 API `reason`) | 데이터에 없는 혜택을 쓰지 않는다 |
| 배너 행(6칸) | Weekly Special 식 하단 그라데이션 + 흰 2줄 | **같다.** 4:5 크롭에 하단 그라데이션, 헤드라인 2줄 Bold 흰색, 서브 1줄 | 카드 안에서 텍스트가 이미지 위에 얹혀야 칸이 작아도 읽힌다 |
| 배지 | 올영PICK·베스트·1등·재구매 1위 | **일부만.** "새로 입점"(new_brand), "{피부타입} 반응"(segment)만 원형 스티커로. **1등·베스트·재구매 1위는 쓰지 않는다** | 순위·재구매 데이터가 없다. 만들지 않는다 |
| 가격 | 취소선 + 빨강 판매가 | **할인율 · 할인가 · 취소선 정가** (PriceTag). 빨강 대신 브랜드 로즈 | 2026-09-10 결정으로 할인을 넣었다. 이벤트·추천은 정가를 보고 할인은 표시와 열린 속성에만 있다 (`frontend/src/lib/discount.ts`) |
| 감정 과장 | "역대급", "한도초과" | **쓰지 않는다.** 대신 상황·고민 → 변화 → 명사 문형만 | 광고 아님 원칙(§0). 표시광고 금지 표현 회피 |
| 대괄호 접두 | "[9월 올영픽/…]" | 상품명엔 안 붙인다. 배너 킥커가 그 역할 | 상품명은 등록 계약 그대로 |

### 10-6. 헤드라인 3줄 틀 (bannerCopy 확장안)

| 축 | 킥커 | 헤드라인 3줄 | 서브 |
|---|---|---|---|
| concern | 피부 고민 | "{고민}이 신경 쓰이는 날 / 한 단계 정돈하는 / {카테고리}" | 가격 · 용량 |
| ingredient | 성분으로 고르기 | "{성분}이 / 전성분 앞에 있는 / {카테고리}" | 가격 · 용량 |
| clean | 성분 표방 | "{clean 태그} / 조건을 지키는 / {카테고리}" | 가격 · 용량 |
| price_bin | 가격대 | "{가격대}에서 / 용량까지 보고 고른 / {카테고리}" | 가격 · 용량 |
| segment | 같은 피부의 선택 | "{피부타입} 피부가 / 오래 들여다본 / {카테고리}" | "{피부타입} 리뷰 n건" (n≥20일 때만) |
| new_brand | 새로 입점 | "이번 주 새로 들어온 / 작은 브랜드의 / 첫 {카테고리}" | 브랜드명 |

명사 종결, 줄당 5~9자, 표시광고 금지어(개선·치료·재생 등) 없음. `{카테고리}`는 `product-form-labels-ko.json` 라벨.

### 10-7. 추가 시트 S13 — 파스텔 배경 타일 (올리브영식 히어로 배경)

S11(피부 질감)·S12(아이보리·리넨·벽)만으로는 올리브영 히어로처럼 선명한 파스텔 배경이 없다. 6장 추가.

```
Background tile sheet for skincare hero banners, brand SSAFY Beauty. Layout: ONE single image divided into a clean 2x3 grid (2 rows, 3 columns) of 6 separate full-bleed background tiles, every tile completely filled edge to edge, separated only by thin pure-white gutters, equal tile size, no cell numbers, no text, no objects, no products. Each tile is a smooth soft pastel studio backdrop: a single gentle color with a very subtle vertical gradient (slightly lighter at the top left, slightly deeper at the bottom right), matte, calm, like a seamless paper backdrop in a product studio, with a faint soft horizontal floor line at the lower third so a product can stand on it. Keep the left half of every tile visually calm for text.

Tiles in reading order:
(1) top-left: soft sky blue (#DCEBF7 to #C9DDF0).
(2) top-center: soft lavender (#E6DFF5 to #D6CCEE).
(3) top-right: soft blush pink (#F7E1E6 to #F2CFD8).
(4) bottom-left: soft mint (#DDF0EA to #CDE6DE).
(5) bottom-center: soft apricot (#FBE7D6 to #F6D7BD).
(6) bottom-right: warm ivory (#FAF7F1 to #F1EBDF).

Negative: text, letters, numbers, logo, watermark, face, people, hands, products, bottles, objects, patterns, harsh shadows, strong contrast, oversaturation, cell borders other than thin white gutters.
```
칸 → `bg-pastel-sky` · `bg-pastel-lavender` · `bg-pastel-blush` · `bg-pastel-mint` · `bg-pastel-apricot` · `bg-pastel-ivory`

변형 ↔ 배경 매핑(§9-5 갱신): 가격=ivory, 성분=mint, 고민=sky(모공·맑음)·lavender(톤·탄력)·blush(건조·눈가), 같은 피부=apricot, 스토리=리넨(S12). 피부 질감 타일(S11)은 고민 배너에서 파스텔 위에 20~30% 불투명도로 겹친다.

### 10-8. 출처

- 올리브영 온라인몰 메인 직접 관찰 (2026-09-09): https://www.oliveyoung.co.kr/store/main/main.do
- 올리브영 광고 소재 디자인 리뷰(Lady Learner): 텍스트 과다 시 "메인 카피를 두 줄로 나누어 가독성 개선", 제품 인지 어려운 소재 지적 — https://theladylearner.com/2523/
- 올리브영 행사 배너 포트폴리오(노트폴리오, 이미지만) — https://notefolio.net/jeeyunn/360764
- 올리브영 배너 모음(Pinterest) — https://kr.pinterest.com/ideas/%EC%98%AC%EB%A6%AC%EB%B8%8C%EC%98%81-%EB%B0%B0%EB%84%88/899761968241/
