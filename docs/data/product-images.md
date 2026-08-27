# 상품 이미지 / 상세 설명 수집 메모

작성: 프론트 (2026-08-27)

데이터셋(`product_info.csv`)에 이미지 URL 과 상세 설명 문단이 없어서
(`docs/data/README.md` 4번 항목) 프론트에서 세포라 공개 페이지 기준으로 직접 채웠다.
이 문서는 **어디서 어떻게 가져왔는지**와 **다시 돌릴 때 필요한 규칙**을 남긴다.

## 채운 필드

`frontend/src/mocks/products.sample.json` 의 8개 상품에 아래 필드를 추가했다.
데이터 담당자가 내려주는 기존 필드는 하나도 건드리지 않았다.

| 필드 | 내용 |
|---|---|
| `image_url` | 대표 이미지. 기존엔 항상 `null` 이던 자리 |
| `sku_id` | 세포라 SKU 번호. 이미지 URL 조립 키 |
| `images` | 대표 이미지 외 추가 갤러리 이미지 |
| `variants` | 색상/향/용량 옵션. `{ sku_id, label, image_url }` |
| `description` | About the Product 영문 원문 |

`description` 하위 키는 `frontend/src/types/product.ts` 의 `ProductDescription` 과 같다.
페이지에 없던 항목은 `null`, 항목 전체가 없으면 `description` 자체가 `null` 이다.

## 이미지 URL 규칙

SKU 번호만 있으면 조립된다.

```
대표: https://www.sephora.com/productimages/sku/s<SKU>-main-zoom.jpg
추가: https://www.sephora.com/productimages/sku/s<SKU>-av-<N>-zoom.jpg
```

- `N` 은 1부터. **상품마다 시작 번호와 개수가 다르다.** 어떤 상품은 `av-1` 이 404 인데
  `av-2` 부터 있고, 어떤 상품은 추가 이미지가 아예 없다. 순차 조회로 실제 확인해야 한다.
- 없는 이미지는 404 + 본문 215 바이트로 응답한다. 상태 코드만 보면 판별된다.
- `?imwidth=<px>` 로 CDN 리사이즈가 된다. 원본은 장당 200~400KB 라서
  썸네일까지 원본으로 받으면 갤러리 한 번에 수 MB 가 된다.
  프론트는 `frontend/src/lib/image.ts` 의 `sizedImage()` 로 쓰이는 자리마다 폭을 지정한다.

이미지를 레포에 내려받지 않고 CDN URL 을 그대로 쓴다. localhost 에서도 로드된다
(핫링크 차단 없음). 나중에 자체 스토리지로 옮기면 `image_url` / `images` 값만 바꾸면 된다.

## 수집 방법

세포라는 상품 **페이지**(HTML)와 `/api/*` 요청을 403 으로 막는다. curl / fetch 직접 요청은 안 된다.
이미지 CDN(`/productimages/*`)만 차단이 없다.

그래서 페이지 본문은 텍스트 추출 프록시를 경유해서 읽었다.

```bash
curl -s -m 40 "https://r.jina.ai/https://www.sephora.com/product/<PRODUCT_ID>"
```

## 주의: 원본 페이지는 지금 시점의 재고를 보여준다

데이터셋은 특정 시점 스냅샷이고 세포라 페이지는 현재 판매 상태다. 그래서 어긋난다.

- P420652 는 데이터셋 이름이 `... with Vitamin C` 인데, 현재 페이지 기본 선택 옵션은
  한정판 `Acai Mango Smoothie` 다. **상품명·가격·성분은 데이터셋 값을 그대로 유지**하고
  이미지와 설명만 가져왔다.
- 가격도 다르다 (데이터셋 $24.00 / 현재 페이지 $25.00). 데이터셋 값을 유지했다.
- 단종된 상품은 페이지가 사라져서 설명을 못 채운 경우가 있다. 그 상품은 `description: null` 이다.

즉 `description` 은 **참고용 표시 데이터**이고, 분석·추천의 입력으로 쓸 값은 아니다.
분석에 쓸 필드는 데이터 담당자가 내려주는 기존 필드를 그대로 써야 한다.

## 다시 돌릴 때

수집 스크립트를 상시 코드로 두지 않았다. 상품 8개짜리 초기 UI 용이고,
백엔드가 붙으면 서버가 내려줄 값이라서다. 상품이 늘어나면 위 규칙대로
`sku_id` → 이미지 순차 확인 → 페이지 본문 파싱 순서로 다시 만들면 된다.
