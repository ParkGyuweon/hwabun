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

수집 결과:

| 상품 | SKU | 갤러리 | 옵션 | 설명 |
|---|---|---|---|---|
| P420652 LANEIGE Lip Sleeping Mask | 1966258 | 9 | 12 | O |
| P427421 Drunk Elephant Protini | 2025633 | 10 | 4 | O |
| P450271 Farmacy Green Clean (점보) | 2339554 | 1 | 0 | △ 아래 주의 참고 |
| P269122 Dr. Dennis Gross Alpha Beta | 1499482 | 1 | 3 | O |
| P429952 Summer Fridays Jet Lag Mask | 2473361 | 20 | 2 | O |
| P454380 Supergoop! Unseen Sunscreen | 2315935 | 27 | 2 | O |
| P431180 Isle of Paradise Tanning Drops | 2078319 | 6 | 6 | O |
| P443349 HUM Skin Squad | 2356756 | 8 | 0 | O |

## 이미지 URL 규칙

SKU 번호만 있으면 조립된다.

```
대표: https://www.sephora.com/productimages/sku/s<SKU>-main-zoom.jpg
추가: https://www.sephora.com/productimages/sku/s<SKU>-av-<N>-zoom.jpg
```

- `N` 은 1부터. **상품마다 시작 번호와 개수가 다르고, 중간이 비기도 한다.**
  P454380 은 `av-13` 다음 `av-14`, `av-15` 가 없고 `av-16` 부터 다시 있다.
  그래서 "404 나오면 중단" 이 아니라 **연속 3회 404** 를 종료 조건으로 썼다.
  개수 상한을 15 같은 작은 값으로 두면 뒤쪽을 통째로 놓친다 (P429952 는 19장이다).
- 추가 이미지가 아예 없는 상품도 있다 (P269122, P450271).
- 위 규칙에 안 맞고 `av-0202507240851191670700` 같은 긴 ID 를 쓰는 이미지도 섞여 있다.
  조립으로는 못 찾으므로, 페이지 JSON 의 `alternateImages` 를 우선 쓰고
  거기서 못 얻은 상품만 순차 조회로 채웠다.
- 없는 이미지는 404 + 본문 215 바이트로 응답한다. 상태 코드만 보면 판별된다.
- `?imwidth=<px>` 로 CDN 리사이즈가 된다. 원본은 장당 200~400KB 라서
  썸네일까지 원본으로 받으면 갤러리 한 번에 수 MB 가 된다.
  프론트는 `frontend/src/lib/image.ts` 의 `sizedImage()` 로 쓰이는 자리마다 폭을 지정한다.

이미지를 레포에 내려받지 않고 CDN URL 을 그대로 쓴다. localhost 에서도 로드된다
(핫링크 차단 없음). 나중에 자체 스토리지로 옮기면 `image_url` / `images` 값만 바꾸면 된다.

넣은 URL 은 전부 `curl` 로 200 을 확인했다.

## 수집 방법

세포라 라이브 사이트는 이 환경에서 전부 막힌다.

- 상품 페이지 HTML 과 `/api/*` 를 403 으로 차단한다. `curl` / `WebFetch` 로는 안 된다.
- 브라우저로 열어도 `Access Denied` 가 뜬다.
- 텍스트 추출 프록시(`r.jina.ai`)는 한동안 됐지만 지금은 자바스크립트 렌더 전
  껍데기만 돌려준다. 본문이 없으므로 설명을 못 뽑는다.
- 이미지 CDN(`/productimages/*`)만 차단이 없다.

그래서 **web.archive.org 스냅샷** 을 썼다. 세포라는 상품 페이지를 클라이언트에서
그리지만 HTML 안에 상품 JSON 을 통째로 박아두기 때문에, 스냅샷 원본 HTML 만 있으면
이미지·옵션·설명을 전부 얻을 수 있다.

```bash
# 1. 스냅샷 시각 찾기 (슬러그가 정확해야 한다)
curl -s "http://archive.org/wayback/available?url=sephora.com/product/<슬러그>-<PID>"

# 2. 원본 HTML 받기. id_ 를 붙여야 아카이브 배너 없이 원본이 온다
curl -s -L "http://web.archive.org/web/<TS>id_/https://www.sephora.com/product/<슬러그>-<PID>"
```

슬러그를 모르면 CDX 로 찾는다. 전체 `product*` 프리픽스는 너무 커서 504 가 나므로
앞부분을 최대한 좁혀야 한다.

```bash
curl -s "http://web.archive.org/cdx/search/cdx?url=sephora.com/product/<앞부분>*&collapse=urlkey&limit=15&fl=timestamp,original"
```

스냅샷마다 JSON 이 들어있기도 하고 없기도 하다. 받은 HTML 에 `shortDescription` 이
없으면 다른 시각의 스냅샷으로 바꿔서 다시 받아야 한다.
(P454380 은 2025년 스냅샷엔 없고 2020년 스냅샷에 있었다.)

파싱에서 주의할 점:

- 설명 본문은 `shortDescription` 한 덩어리에 `제목: 본문` 이 반복되는 HTML 이다.
  상품 등록 시기에 따라 `<b>` + `<br>` 이거나 `<strong>` + `<p>` 라서 둘 다 처리해야 한다.
- `longDescription` 은 보통 브랜드 소개지만, 상품 설명을 그대로 복사해 둔 상품이 있다.
  그대로 넣으면 화면에 같은 문단이 두 번 나온다.
- 영양제(P443349)는 `Skin Type` / `Skincare Concerns` 대신
  `Beauty Benefit` / `What it tastes like` 같은 다른 제목을 쓴다.

## 주의: 원본 페이지는 데이터셋과 어긋난다

데이터셋은 특정 시점 스냅샷이고 세포라 페이지는 그 뒤로 계속 바뀌었다.

- P420652 는 데이터셋 이름이 `... with Vitamin C` 인데 현재 페이지 기본 선택은
  한정판 `Acai Mango Smoothie` 다. 대표 이미지는 기본 향인 `Berry`(1966258) 로 잡았다.
- 가격도 다르다 (데이터셋 $24.00 / 현재 페이지 $25.00).
- **P450271 은 상품 페이지 자체가 아카이브에 없다.** 한정판 점보 사이즈라 단종됐고
  남은 캡처가 302 리다이렉트 하나뿐이다. 그래서 **같은 제품의 일반 사이즈
  (P417238) 페이지에서 이미지와 설명을 가져왔다.** 용량만 다른 같은 제품이지만
  점보 실물 이미지는 아니다. 옵션과 갤러리 이미지는 비어 있다.

**상품명·가격·성분 등 데이터셋 필드는 전부 원본 값을 그대로 유지했다.**
바꾼 것은 위 표의 5개 필드뿐이다.

즉 `description` 은 **참고용 표시 데이터**이고, 분석·추천의 입력으로 쓸 값은 아니다.
분석에 쓸 필드는 데이터 담당자가 내려주는 기존 필드를 그대로 써야 한다.

## 다시 돌릴 때

수집 스크립트를 상시 코드로 두지 않았다. 상품 8개짜리 초기 UI 용이고,
백엔드가 붙으면 서버가 내려줄 값이라서다. 상품이 늘어나면
슬러그 확인 → 스냅샷 HTML → JSON 파싱 → 이미지 200 검증 순서로 다시 만들면 된다.
