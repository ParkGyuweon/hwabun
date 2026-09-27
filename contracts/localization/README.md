# 사이트 한국어화 데이터 (2026-09-09 · 리뷰 20,000건 확장 2026-09-11)

쇼핑몰 화면에 뜨는 **상품명·설명·전성분·용량·옵션명·가격(원)·리뷰**의 한국어 문장과,
**카테고리·하이라이트·피부 고민·피부 타입·배지**의 화면 라벨. 사람이 검수한 대조표
(`docs/localization/HWABUN_한국어화_검수본_20260909/`)를 `batch/ingest/build_ko_catalog.py` 가
JSON 으로 옮긴 것이다. **이 폴더의 JSON 은 직접 고치지 말고** 대조표를 고친 뒤 다시 만든다.

```
python batch/ingest/build_ko_catalog.py
```

빌더는 대조표의 영문 원문 열을 `frontend/src/mocks/products.sample.json` · `reviews.sample.json` 과
한 글자씩 대조해 어긋나면 실패한다. 그래서 각 행이 어느 `product_id`·`review_id` 인지 확실하다.

## 원칙

- **내부 키는 영문 그대로.** `category[]`, `highlights[]`, `skincare_concerns[]`, `suitable_skin_types[]`,
  `badges[]`, `variants[].label` 의 값은 어휘집·이벤트 계약·추천 벡터가 그대로 쓴다.
  화면에서만 `labels-ko.json` 으로 바꿔 보여준다. 값을 바꾸면 추천 매칭이 조용히 0 이 된다.
- **브랜드명 영문 유지.** (`brand_name` 은 번역 대상이 아님)
- **가격**: 고정 환율 1 USD = 1,340.86 KRW, 100원 단위 반올림 → `price_krw`.
  이벤트 금액은 원화 `unit_price`+`currency="KRW"` 로 확정됐다(Jira 303, `contracts/event-properties-schema.md` — `price_usd` 는 deprecated 입력).
- 리뷰 수·평점·좋아요 수는 숫자라 대상 아님.
- SSAFY Beauty 8종(`products.ssafy-beauty.json`)은 처음부터 한국어로 쓴 파일이라 여기 없다.

## 파일

### `products-ko.json` — 상품 200개, 키 = `product_id`

| 필드 | 뜻 | 대응하는 `Product` 필드 |
|---|---|---|
| `product_name` | 한국어 상품명 | `product_name` |
| `size` | 용량 표기 (`50ml`, `20g`). 원본이 없으면 `null` (8개) | `size` |
| `price_krw` | 원화 가격 (정수) | `price_usd` 대신 표시 |
| `variant_labels` | `{영문 label: 한국어 label}`. 옵션이 있는 6개 상품만 채워짐 | `variants[].label` 표시용 |
| `description` | `ProductDescription` 과 같은 9개 필드, 한국어. 원본에 설명이 없는 2개는 `null` | `description` |
| `ingredients` | 전성분 한국어 (원본과 같이 통짜 문자열 1개짜리 배열). 원본이 빈 1개는 `[]` | `ingredients` |

`description` 안의 줄바꿈은 원본과 같이 `\n`. `highlighted_ingredients` 는 배열.

### `reviews-ko.json` — 리뷰 20,000건(상품당 100건), 키 = `review_id`

2026-09-11 확장 (Jira 242). 09-09 의 2,000건(상품당 10)은 그대로 재사용됐고 18,000건이 더해졌다. 상품별
100건은 `batch/ingest/build_reviews_100.py` 가 원천 45.8만 건에서 별점×피부타입 층화로 뽑은 것(평균 = 화면 별점
200/200 일치). 번역은 `batch/ingest/merge_reviews_ko.py` 검수 A~G 를 20,000/20,000 통과했다.
프론트가 실제로 읽는 형태(상품별 `{product_id}.json` 200개, 제목·본문만 한국어)는 `batch/ingest/build_reviews_ko_files.py` 로 만든다.

| 필드 | 뜻 |
|---|---|
| `product_id` | 어느 상품의 리뷰인지 (원본과 같음) |
| `review_title` | 한국어 제목. 원본 제목이 없는 6,186건은 `null` |
| `review_text` | 한국어 본문. 빈 본문 0건 (100건 추출이 본문 있는 리뷰만 뽑는다) |

별점·작성자 속성·날짜·`is_recommended` 는 원본 그대로 쓰면 된다.

### `labels-ko.json` — 화면 라벨, `{영문 키: 한국어}`

| 그룹 | 항목 수 | 붙는 곳 |
|---|---:|---|
| `category` | 26 | `category[]` 각 단계 (`Skincare > Moisturizers` → `스킨케어 > 크림·로션`) |
| `highlights` | 53 | 상품 카드·상세·필터의 하이라이트 태그 |
| `skincare_concerns` | 9 | 피부 고민 칩 |
| `suitable_skin_types` | 4 | 적합 피부 칩 (`dry` → `건성`) |
| `badges` | 4 | 배지 (`limited` → `한정`, `exclusive` → `단독`) |
| `variant_labels` | 26 | 옵션 버튼. `products-ko.json` 의 `variant_labels` 와 같은 내용을 한 곳에 모은 것 |

원본 200개가 쓰는 키는 전부 들어 있다 (빌더가 누락을 검사한다). 없는 키가 들어오면 영문 그대로 보여주면 된다.

## 화면에 붙일 때 (프론트 몫)

한국어 데이터를 **별도 파일로 두고 표시할 때만 합치는** 쪽을 권한다. `products.sample.json` 은
`scripts/build-products.ts` 가 만드는 생성 파일이고 추천·시뮬레이터·이벤트가 영문 값을 참조하므로,
그 파일을 한국어로 덮어쓰면 다른 축이 깨진다.

- 상품: `product_id` 로 `products-ko.json` 을 찾아 `product_name`·`size`·`description`·`ingredients` 를 바꿔 끼우고, 가격은 `price_krw` 를 원 단위로.
- 옵션: `variants[].label` 은 값으로 그대로 두고 표시만 `labels-ko.variant_labels[label] ?? label`.
- 태그·카테고리·배지·피부 타입: `labels-ko.<그룹>[값] ?? 값`.
- 리뷰: `review_id` 로 `reviews-ko.json` 을 찾아 제목·본문만 바꿔 끼움.
- 검색·필터가 상품명·태그 문자열을 매칭한다면 한국어 라벨과 영문 값 둘 다 대상에 넣어야 한다.

## 아직 결정이 필요한 것

**등록 폼 라벨 — 사이트 라벨로 통일됨.** `contracts/product-form-labels-ko.json`(브랜드 등록 폼·대시보드가 쓰는 라벨)을
사이트 라벨 기준으로 맞췄다. 2026-09-25 대조: 같은 영문 키 70개 중 다른 것은 **피부 타입 4개**뿐이다
(`건성 피부` vs `건성` — 가입 폼 문구라 `피부` 를 붙인 것). 카테고리·피부 고민·성분 표방·제형 태그는 0.
예전 차이(`Cruelty-Free` 폼=`동물실험 반대` / 사이트=`크루얼티 프리` 등)는 없어졌다.
다시 바꿀 때는 `batch/ingest/build_form_labels.py` 의 KO 를 고치고 다시 만든다.

**배지 라벨.** 상품 대조표 본문은 `한정판`·`단독 판매`, 열거값 대조표는 `한정`·`단독`. 열거값 대조표를
기준으로 넣었다(배지는 짧은 칩이라). 길게 쓰려면 `01_열거값_대조.md` 의 배지 절만 바꾸고 다시 만든다.

## 검수본이 남긴 배포 전 확인 항목 (00_교정_원칙 §5)

- 희귀 식물 추출물·복합 원료의 공식 한글 성분명 대조 (대한화장품협회 성분사전)
- 임상·효능 표현의 국내 표시·광고 기준 증빙
- 국내 판매명이 이미 있는 수입 브랜드 상품의 공식 상품명
- 원화 가격·옵션 용량이 실제 서비스 정책과 맞는지
