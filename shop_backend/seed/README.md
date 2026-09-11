# 백엔드 시드 인계 — 프론트 화면에 뜨는 데이터 전부 (2026-09-11)

프론트가 화면에 띄우는 데이터를 **전부** shop_backend 테이블 모양(camelCase)으로 바꿔 `out/` 에 묶었다.
이 폴더의 JSON 을 INSERT 하면 프론트 정적 파일과 백엔드 DB 가 같은 내용이 되고, 그 뒤로 프론트는 백엔드 값을 먼저 쓴다.

```
python shop_backend/seed/build_seed.py     # out/ 를 다시 만든다 (원천이 바뀌었을 때)
```

| 파일 | 건수 | 들어갈 테이블 |
| --- | ---: | --- |
| `out/codes.json` | 12 종류 | `secondary_category` · `tertiary_category` · `price_bin` · `concern` · `clean_feature` · `texture_feature` · `ingredient` · `skin_type` · `skin_tone` · `hair_color` · `eye_color` · **`category`** |
| `out/brands.json` | 56 | `brand` (세포라 55 + SSAFY Beauty 1) |
| `out/products.json` | 208 | `product` · `product_variant` · `product_image` · `product_skin_type` · `product_concern` · `product_clean` · `product_texture` · `product_ingredient` |
| `out/reviews.json` | 2,000 | `review` — **스키마와 안 맞음, §4 참고** |
| `out/members-personas.json` | 100 | `member` (PA 페르소나 100명을 회원으로) |
| `out/issues.json` | — | 변환 중 정한 것·못 정한 것 |

---

## 1. 코드 테이블 (`codes.json`)

계약 어휘(`contracts/product-form-labels-ko.json`)에서 그대로 뽑았다. **`code` 는 문자열 그대로 PK**, `labelKo` 는 표시용.
지금 `mysql-erd.sql` 시드의 `label_ko` 는 영문 그대로인데 여기 한국어 라벨이 있으니 그걸로 바꾸면 된다.

| 키 | 테이블 | 비고 |
| --- | --- | --- |
| `secondary_category` (8) · `tertiary_category` (19) · `price_bin` (5) | 같은 이름 테이블 | 둘은 계층이 아니다. `Moisturizers` 가 양쪽에 있다 |
| `concern` · `clean` · `texture` | `concern` · `clean_feature` · `texture_feature` | 등록 폼 `highlights` 가 이 셋 중 하나에 속한다 |
| `ingredient` (30) | `ingredient` | 추천이 읽는 30종. 전성분 원문은 `product.ingredients_text` 에 통째로 |
| `skin_type` · `skin_tone` · `hair_color` (6, `gray` 포함) · `eye_color` | 같은 이름 테이블 | 페르소나 표·리뷰어 속성·회원 프로필이 전부 이 값 |
| `category` (8) | `category` | **`category_id` = `secondary_category` 코드.** `depth=1`, parent 없음. 이걸로 `product.category_id` FK 가 통과한다 (요청 2·9-2) |

## 2. 브랜드 (`brands.json`)

| 필드 | 컬럼 | 비고 |
| --- | --- | --- |
| `brandId` | `brand_id` | **세포라 브랜드 = 세포라 번호 문자열** (`"6125"` = LANEIGE). 데이터 `dim_brand.brand_id` 와 같은 값이라 대시보드 마트가 매핑 없이 붙는다 (계약 0.2 §8-2). SSAFY Beauty 는 제안값 `ssafy-beauty` — uuid 로 발급해도 되지만 그 값이 AI 카탈로그·dw 에도 같이 흘러가야 한다 |
| `name` | `name` | 표시명 |
| `source` | — | `seed_catalog` 55 개는 **시연 판매자 계정 하나**에 묶어도 된다 (대시보드에서 브랜드 셀렉터로 고른다). `brand.seller_account_id` NOT NULL 이라 계정이 먼저 있어야 한다 |

## 3. 상품 (`products.json`)

한 항목이 `product` 한 행 + 하위 테이블들이다.

| 필드 | 테이블.컬럼 | 비고 |
| --- | --- | --- |
| `productId` | `product.product_id` | 세포라 `P…` 200 · SSAFY `SB000001~8` |
| `brandId` · `brandName` | `product.brand_id` | 위 brands.json 과 같은 값 |
| `productSource` · `status` | `product.product_source` · `status` | 전부 `ACTIVE` 로 넣는다 (목록은 ACTIVE 만 준다) |
| `categoryId` · `secondaryCategory` · `tertiaryCategory` · `priceBin` | 같은 이름 컬럼 | 전부 코드 문자열. **원천이 2단계까지만 있는 59개**는 tertiary 를 secondary 와 같은 값으로 채웠다 (둘 다 어휘에 있는 `Moisturizers` · `Lip Balms & Treatments`). `issues.json` 에 목록 |
| `productName` | `product.product_name` | **영문 원문.** 추천 서버 카탈로그·데이터 `dim_product` 가 이 이름을 쓴다 |
| `productNameKo` · `sizeKo` · `descriptionKo` · `ingredientsTextKo` | 없음 → **제안: `description_json` 안에 `name_ko` · `size_ko` · `ingredients_ko` 로 넣거나 `product_name_ko` 컬럼 추가** | 화면 표시명. 지금 프론트는 `contracts/localization/products-ko.json` 에서 붙이는데, 백엔드가 주면 그걸 먼저 쓴다 |
| `priceKrw` · `salePriceKrw` · `discountLabel` | `product_variant.price_krw` · `sale_price_krw` (모든 옵션 같은 값) | `priceKrw` = 달러 × 1,340.86 을 100원 단위 반올림 (`products-ko.json` 의 값과 같음). `salePriceKrw` 는 프론트 `discounts.json` 의 표시용 할인 — 넣으면 화면 할인 표시가 백엔드 값으로 바뀐다. 안 넣어도 됨 |
| `sourcePriceUsd` · `sourceRating` · `sourceReviewCount` · `sourceLovesCount` · `sourceRank` | `product.source_*` | 세포라 원천값 |
| `ratingSource` | `product.rating_source` | 원천 평점 있으면 `observed`, SSAFY 8개는 `injected` (추천 서버가 카테고리 중앙값 주입) |
| `primaryImageUrl` · `images[]` | `product.primary_image_url` · `product_image(url, sort_order)` | 세포라 CDN 주소 그대로 |
| `variants[]` | `product_variant` | `skuId→sku_id` · `label` · `labelKo` · `size` · `priceKrw` · `salePriceKrw` · `imageUrl` · `swatchUrl` · `sortOrder`. 옵션이 없던 상품은 `label="기본"` 하나 |
| `highlights[]` | `product_concern` · `product_clean` · `product_texture` (어휘에 있는 것) · 나머지 `product_unmapped_value` | 지금 `POST /api/products` 가 하는 것과 같은 분류 |
| `suitableSkinTypes[]` | `product_skin_type` | 값은 `dry` 등 코드 |
| `skincareConcerns[]` | `product_concern` | highlights 와 합쳐 dedupe |
| `ingredientsText` | `product.ingredients_text` | 전성분 원문. `product_ingredient` 는 여기서 30종을 찾아 `first_position` · `weight` 를 계산 — **쉼표 분리 규칙: 쉼표 뒤가 숫자면 자르지 않는다** (`1,2-Hexanediol`). 프론트·AI 와 같은 규칙이어야 위치가중이 맞는다 |
| `badges[]` | 없음 → 제안 `description_json.badges` | `exclusive` · `limited edition` 등 세포라 배지. 화면 "단독" 배지의 원천 |
| `description` | `product.description_json` | `what_it_is` · `suggested_usage` · `highlighted_ingredients` · `ingredient_callouts` · `what_else` · `clinical_results` · `brand_story` · `skin_type` · `concerns_text` |

## 4. 리뷰 (`reviews.json`) — 스키마와 안 맞는 부분

`review` 테이블은 `order_item_id NOT NULL UNIQUE` 라 **구매 없는 리뷰를 넣을 수 없다.** 세포라 리뷰 2,000건은 우리 몰 주문이 아니다.
그래서 지금은 프론트가 `reviews.sample.json` 을 직접 보여주고, 백엔드 상품(`source=backend`)만 `GET /api/products/{id}/reviews` 를 쓴다.

백엔드에 넣으려면 둘 중 하나:

1. **`review.order_item_id` 를 NULL 허용 + `source ENUM('shop','seed_catalog')` 컬럼 추가.** 시드 리뷰는 `order_item_id=NULL, source='seed_catalog'`. `product_id` 컬럼도 필요하다 (지금은 order_item 을 거쳐야 상품을 안다).
2. 시드 리뷰는 백엔드에 안 넣고 프론트 정적 파일로 둔다 (지금 상태).

1 을 고르면 필드 매핑: `reviewId→review_id` · `productId→product_id(신설)` · `rating` · `isRecommended→is_recommended` · `title` · `body` · `titleKo/bodyKo`(제안: `body_ko` 컬럼 또는 프론트 유지) · `submittedAt→created_at` · `skinTypeSnapshot` 등 → `*_snapshot` 컬럼 (있음) · `authorId` 는 세포라 익명 id 라 `member_id` 에 못 넣는다.

리뷰어 피부 속성 4개는 대시보드 "피부 타입별 평점 갈림" 과 추천 속성 친화도의 원천이라 **빼면 안 된다.**

## 5. 회원 (`members-personas.json`)

PA 페르소나 100명. `frontend/scripts/register-personas.ts` 가 `POST /api/auth/members` 로 보내는 것과 같은 본문이다.
`RegisterMember` 가 속성 4개(`skinTypeCode` …)를 받기 시작해야 값이 저장된다 (요청 8·9-3). 비밀번호는 전부 `hwabun1234`.
직접 INSERT 하려면 `password_hash` 는 백엔드 인코더로 만들어야 한다.

## 6. 백엔드에 없는 것 (프론트에 남는 것)

| 데이터 | 왜 프론트에 남나 |
| --- | --- |
| 완성형 배너 이미지 목록 (`banner-images.json`) · 배너 문구 조립 규칙 | 화면 크리에이티브. 상품 데이터가 아니다 |
| 세션 성향(`hwabun.trait`) · 배너 축 선택 | 브라우저 안 행동 계산. 서버는 `user_trait_daily` 마트로 따로 만든다 |
| 대시보드 모의 집계 | 마트 API 가 붙으면 사라지는 대체값 |
| 페르소나 스위처 | 시뮬레이션 신원. 회원 로그인이 대체 |

## 7. 넣는 순서

```
codes(category 포함) → seller_account(시연 계정) → brand → product → product_variant · product_image · product_* 태그 → product_ingredient → member
```

`review` 는 §4 결정 뒤에.
