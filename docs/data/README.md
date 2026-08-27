# 프론트 초기 UI용 샘플 데이터

세포라 데이터셋 기준. 상품 8개 / 상품당 리뷰 5개 = 리뷰 40건.

| 파일 | 내용 |
|---|---|
| `products.sample.json` | 상품 8개 |
| `reviews.sample.json` | 리뷰 40건 (상품당 5개) |
| `field_stats.json` | 전체 데이터 기준 필드별 채움률 |

**모든 필드는 요청하신 이름 그대로 맞춰서 내보냈습니다.** 배열 요청 4개 필드(`ingredients`, `highlights`, `suitable_skin_types`, `skincare_concerns`)도 전부 JSON 배열입니다.

---

## 확인 요청 사항 답변

### 1. product_id로 상품–리뷰 연결 가능한가 → **가능**

원본 리뷰 CSV에 `product_id`, `product_name`, `brand_name`, `price_usd`가 이미 들어 있어서 조인 없이도 목록 렌더링이 됩니다. 샘플의 8개 `product_id`는 양쪽 파일에 100% 대응됩니다.

### 2. author_id로 동일 작성자 구분 가능한가 → **가능**

`author_id`는 100% 채워져 있습니다. 샘플에는 **여러 상품에 리뷰를 단 작성자 3명을 일부러 포함**시켰습니다.

| author_id | 샘플 내 리뷰한 상품 |
|---|---|
| `1288462295` | P420652, P427421, P429952, P450271, P454380 |
| `23940992103` | P269122, P420652, P427421, P450271, P454380 |
| `11981978017` | P420652, P427421, P431180, P450271, P454380 |

"이 리뷰어의 다른 리뷰 보기" 같은 UI를 이걸로 테스트하실 수 있습니다.

⚠️ **주의: 같은 작성자가 같은 상품에 리뷰를 2건 단 경우가 있습니다.** 샘플에도 2건 들어있습니다 (`1288462295` × P420652, `1288462295` × P429952). `(author_id, product_id)`를 유니크 키로 쓰면 깨집니다. **`review_id`를 키로 쓰세요.**

### 3. review_id → **원본에 없어서 생성했습니다**

원본에는 리뷰 식별자가 없고, `Unnamed: 0` 인덱스 컬럼이 있는데 **파일마다 0부터 다시 시작해서 전역 고유가 아닙니다** (총 1,094,411행인데 고유 인덱스는 602,130개).

그래서 `RV-{파일구간}-{원본인덱스}` 형식으로 생성했습니다.
```
RV-0-250-002960
RV-1250-end-014882
```
**문자열입니다.** 정수로 파싱하지 마세요. 전체 데이터에서 고유성 검증 완료했습니다.

### 4. 상품 이미지 → **데이터셋에 없습니다. 임시 이미지 사용해 주세요.**

`product_info.csv` 27개 컬럼을 다 확인했는데 이미지 URL·SKU·썸네일 관련 컬럼이 **하나도 없습니다.** 세포라 공식 이미지 URL은 SKU ID가 필요한데 그 값도 데이터셋에 없어서 URL을 조합할 수 없습니다.

샘플에는 `"image_url": null`로 넣어뒀습니다. **초기 UI에서는 플레이스홀더로 진행해 주세요.** 스키마는 지금 형태 그대로 유지할 예정이라, 나중에 이미지를 확보하면 `null`만 채우면 됩니다.

### 5. category → **배열로 변환했습니다**

원본은 `primary_category` / `secondary_category` / `tertiary_category` 3개 컬럼입니다. 계층 순서 배열로 합쳤습니다.
```json
"category": ["Skincare", "Lip Balms & Treatments"]
```
`tertiary_category`가 없는 상품이 있어서 **배열 길이는 2 또는 3으로 가변**입니다. 인덱스로 접근하지 마시고 마지막 원소를 쓰거나 breadcrumb으로 렌더링해 주세요.

### 6. suitable_skin_types / skincare_concerns → **highlights에서 파생했습니다**

원본에 이 두 필드는 없습니다. `highlights` 안에 섞여 있는 걸 분리했습니다.

| 원본 highlights 값 | 분리 결과 |
|---|---|
| `"Good for: Dryness"` | `skincare_concerns: ["Dryness"]` |
| `"Best for Dry, Combo, Normal Skin"` | `suitable_skin_types: ["combination","dry","normal"]` |

`suitable_skin_types` 값은 리뷰의 `skin_type`과 동일한 용어(`dry`/`oily`/`combination`/`normal`)로 정규화했습니다. 원본의 `Combo`는 `combination`으로 매핑했습니다.

⚠️ **8개 중 4개는 `suitable_skin_types`가 빈 배열입니다.** 원본 highlights에 피부타입 표기가 없는 상품이 많습니다. **빈 배열 처리 UI가 필요합니다.** (추후 리뷰 데이터에서 피부타입별 평균 평점으로 보완할 예정입니다)

### 7. ingredients → **배열이지만 원소가 통짜 문자열입니다**

⚠️ 이게 제일 주의하실 부분입니다. 형식상 배열이지만 **대부분 원소가 1개고, 그 안에 전 성분이 쉼표로 이어붙은 1,000자짜리 문자열**입니다.

```json
"ingredients": ["Diisostearyl Malate, Hydrogenated Polyisobutene, Phyto-Steryl..."]
```

8개 중 7개가 원소 1개(길이 188~1,077자), 1개만 원소 4개입니다. 원소 개수가 성분 개수가 아닙니다.

성분을 칩(chip) 형태로 뿌리시려면 저희가 쉼표 분리 + 정규화를 해서 드려야 합니다. **초기 UI에서는 그냥 긴 텍스트 블록으로 렌더링**하시고, 칩 형태가 필요하면 말씀해 주세요.

---

## 필드 명세

### 상품 (`products.sample.json`)

| 필드 | 타입 | null | 비고 |
|---|---|---|---|
| `product_id` | string | 없음 | `"P420652"` |
| `product_name` | string | 없음 | |
| `brand_name` | string | 없음 | |
| `category` | string[] | 없음 | 길이 2~3 가변 |
| `image_url` | null | **항상 null** | 데이터셋에 없음 |
| `price_usd` | number | 없음 | USD |
| `size` | string \| null | **19.2%** | `"0.7 oz/ 20 g"` 자유 텍스트 |
| `rating` | number | 3.3% | 0~5 소수 |
| `review_count` | number | 3.3% | 원본 컬럼명은 `reviews` |
| `highlights` | string[] | 26.0% → `[]` | 피부타입/고민 항목은 제외된 나머지 |
| `ingredients` | string[] | 11.1% → `[]` | 위 7번 참고 |
| `suitable_skin_types` | string[] | 파생, 빈 배열 많음 | `dry`/`oily`/`combination`/`normal` |
| `skincare_concerns` | string[] | 파생, 빈 배열 가능 | `"Dryness"`, `"Acne/Blemishes"` 등 |

null 비율은 전체 8,494개 상품 기준입니다. 배열 필드는 원본이 null이면 `[]`로 내보냈으니 프론트에서 null 체크는 불필요합니다.

### 리뷰 (`reviews.sample.json`)

| 필드 | 타입 | null | 비고 |
|---|---|---|---|
| `review_id` | string | 없음 | 생성 필드. 유니크 키 |
| `product_id` | string | 없음 | |
| `author_id` | string | 없음 | **문자열로 내보냄** (11자리 숫자라 JS number 안전범위 밖은 아니지만 통일) |
| `rating` | number | 없음 | 1~5 정수 |
| `is_recommended` | boolean \| null | 없음 | 아래 참고 |
| `review_title` | string \| null | **31.1%** | **null 처리 필수** |
| `review_text` | string \| null | 0.16% | |
| `submission_time` | string | 없음 | `"2021-04-29"` (요청엔 없지만 정렬용으로 포함) |
| `skin_type` | string | 없음 | `combination`/`dry`/`normal`/`oily` |
| `skin_tone` | string | 없음 | `light`, `fair`, `lightMedium` 등 14종 |
| `eye_color` | string | 없음 | `brown`, `blue`, `hazel`, `green`, `Grey`/`gray` |
| `hair_color` | string | 없음 | `brown`, `blonde`, `black` 등 7종 |

**리뷰는 사용자 속성 4개(`skin_type`/`skin_tone`/`eye_color`/`hair_color`)가 전부 채워진 것만 필터링해서 드립니다.** 전체 1,094,411건 중 844,865건(77.2%)이 여기 해당하고, 앞으로도 이 기준으로 갑니다. 그래서 위 4개 필드는 **null이 안 나옵니다.**

`is_recommended`도 이 필터를 통과한 리뷰에서는 **100% 채워져 있습니다** (전체 기준으로는 84.7%). 타입은 `true`/`false`로 변환해서 보냈습니다. 원본은 `1.0`/`0.0` float입니다.

`review_title`만 31.1% 비어 있으니 **제목 없는 리뷰 레이아웃**을 준비해 주세요.

---

## 알려진 데이터 이슈

1. **`eye_color`에 `Grey`와 `gray`가 따로 존재** — 대소문자·영미 철자 혼재. 아직 정규화 전이라 샘플에도 그대로 나갑니다. 필터 UI 만드실 때 주의해 주세요. 다음 전달 때 병합해서 드리겠습니다.
2. **정가/미니 사이즈가 다른 `product_id`인데 리뷰를 공유** — 상품 2,345개 중 74쌍이 중복입니다. 샘플에서는 `Mini ` 접두 상품을 제외했습니다.
3. **`size`는 자유 텍스트** — `"3.4 oz/ 100 mL"` 형태가 많지만 통일된 포맷이 아닙니다. 파싱하지 마시고 그대로 표시해 주세요.

## 다음 전달 시 반영 예정

- `eye_color` 표기 정규화
- `ingredients` 쉼표 분리 (필요하다고 하시면)
- `suitable_skin_types` 빈 배열을 리뷰 기반 통계로 보완
- `image_url` (확보되면)

필드 추가나 형식 변경 필요하시면 말씀해 주세요.
