# 브랜드 대시보드 인사이트 옵션 + AI 해석 규칙 카탈로그 (근거판)

> 목적: 브랜드 사장님이 보는 대시보드 화면마다 어떤 인사이트를 줄 수 있는지 옵션을 펼치고, AI 파트가 인사이트 문장을 생성하는 프롬프트에 그대로 넣을 수 있도록 **"이 데이터는 → 이런 뜻이다"** 해석 규칙을 **공개된 근거와 함께** 정리한다.
>
> 이 판은 2026-09-08 웹 조사(5개 영역, 1차 출처 직접 확인 원칙)로 각 항목에 출처를 붙였다. 조사에서 **확인되지 않은 것은 삭제하거나 "확인 불가"로 남겼다.** 계산식·화면 배치는 [insight-catalog.md](./insight-catalog.md), [metric-basis.md](./metric-basis.md) 를 따르고 여기서는 의미·문장·근거만 다룬다. 어휘는 `contracts/product-feature-vocab.json` · `contracts/product-form-labels-ko.json` 이 단일 출처다.

## 근거 등급 표기

| 표기 | 뜻 |
|---|---|
| `[법령]` | 법률·고시·규정 원문 |
| `[공식]` | 기업·기관의 공식 문서·보도자료·도움말 |
| `[연구]` | 피어리뷰 논문, 대규모 사용성 연구(Baymard·NN/g), 메타분석 |
| `[리서치]` | 조사기관 설문 (Mintel·Circana·오픈서베이·YouGov·PowerReviews 등). 표본·연도 병기 |
| `[벤더]` | 분석 도구·솔루션 업체의 자사 데이터·사례. 방향은 참고, 수치는 과신 금지 |
| `[실측]` | 우리 카탈로그·로그로 확인한 값 |
| `[전문가]` | 피부과·UX 전문가 의견 수준. RCT 없음 |
| `[추정]` | 우리 가설. 실측이 생기면 교체 |

번호 `[n]` 은 문서 끝 출처 목록을 가리킨다.

---

## 0. 이번 조사로 바뀐 것 (정직하게 먼저)

| 이전 판의 주장 | 조사 결과 | 처리 |
|---|---|---|
| "대시보드 지표 8~12개 상한" | 벤더 블로그에만 있고 Few·NN/g·Tableau 공식 문서에 없음 [50][51] | 근거 없는 수치로 표기. Few의 "단일 화면·한눈에" 정의로 대체 [49] |
| "5초 규칙" | 5초 테스트는 Perfetti가 명명했고 5초라는 숫자는 anecdotal [52] | 검증 방법으로만 쓰고 "규칙"이라 부르지 않음 |
| "선언 34% vs 관찰 89%" 류 수치 | 1차 연구 없음 | 삭제. Morwitz et al. 2007 메타분석의 조건 목록으로 대체 [53] |
| 재구매 주기 "세럼 6~8주, 크림 8~12주" | 브랜드 FAQ 3곳이 30ml 세럼을 4~5주·6주·8~10주로 안내. 크림·클렌저 주기는 공개 근거 없음 [40][41][42] | 세럼만 "브랜드 안내 기준 4~10주"로, 나머지는 실측 대기 |
| "겨울 세라마이드 매출 급증" | 매출 정량 보고 없음. 피부 과학 근거(겨울 TEWL 최고)만 있음 [35][36] | 매출 주장 삭제, 피부 생리 근거로 서술 |
| 비타민C + 나이아신아마이드 병용 주의 | 근거 없음(1960년대 니코틴산 연구 오해). 병용 문제 없음 [27] | 주의 목록에서 제거 |
| 시어버터·스쿠알란·호호바 "지성에 무거움/코메도제닉" | 등급표는 토끼귀 실험 기반, 사람 대조 데이터 없음 [33][34] | "코메도제닉 등급은 근거 약함"으로 표기 |
| "아마존 매출 35%가 추천" | McKinsey 2013 컬럼의 각주 없는 추정 [59] | 인용 시 "McKinsey 추정"으로만 |
| 뷰티 전용 전환율 벤치마크 | Contentsquare 공개 탐색기에 뷰티 세부 없음 [7] | Retail 벤치마크로 대체 |

---

## 1. 브랜드의 질문 다섯 개 — 왜 이 다섯인가

대시보드의 모든 문장은 아래 다섯 질문 중 하나에 답해야 한다.

| # | 브랜드의 질문 | 결정하는 것 | 실제 업계가 브랜드에 주는 같은 종류의 지표 |
|---|---|---|---|
| Q1 | **무엇을 써야 팔리나** | 상세페이지 콘텐츠·순서·배지·문구 | Contentsquare 존 지표: Exposure Rate → Attractiveness Rate → Conversion Rate per Click → Revenue per Click. 페이지 요소 단위로 노출·클릭·전환·매출을 귀속 [8][9][10][11] `[공식]` |
| Q2 | **누구에게 팔아야 하나** | 타깃 고객군·소구 포인트 | Amazon Brand Analytics Demographics(연령·소득·성별, ASIN당 고객 100명 이상일 때만) [45]; Walmart Scintilla Shopper Behavior(침투율·교차구매·스위칭·세그먼트) [46] `[공식]` |
| Q3 | **다음 제품은 무엇인가** | 성분·고민 축·가격대·용량 | Amazon ABA Market Basket(함께 구매 상위 3)·Repeat Purchase Behavior [45]; L'Oréal이 Revuze 리뷰 분석으로 "트렌드 vs 하이프" 구분 [55] `[벤더]` |
| Q4 | **고객이 무엇을 고쳐 달라 하나** | 처방·용기·향·가격 개선 | Glossier Milky Jelly Cleanser: 블로그 댓글 ~400건을 화학자에게 전달해 개발 [56][57]; 디마프: 선크림 백탁·발림·건조 불만 개선 후 5,000개 재생산 무상 발송 [58] `[공식·언론]` |
| Q5 | **내 위치는 어디인가** | 가격·전환·콘텐츠의 상대 수준 | Shopify Benchmarks: 코호트(주문량·시장·카테고리) 대비 중앙값·25·75 백분위만 제공, 유사 스토어 부족 시 미표시 [47] `[공식]` |

**왜 브랜드에게 해석이 필요한가.** 온라인 뷰티 쇼핑객 99.5%가 리뷰를 읽고 [14], 화해 앱에는 리뷰 1,000만 건이 쌓여 있다 [19]. 데이터는 넘치는데 브랜드 담당자가 그것을 읽어 "무엇을 고칠지"로 바꾸는 단계가 비어 있다. 디마프는 이 단계를 "수만 건 후기를 AI로 분석"하는 것으로 풀었다고 밝혔다 [58].

---

## 2. 화면별 인사이트 옵션 (브랜드 사업자 시점)

현재 대시보드 9화면(Overview · 상품 등록 · 상품 분석 · 정보 관심도 · 고객군 · 행동 분석 · 리뷰 분석 · 성분 분석 · 고객 피드백) 기준. ★ 는 뷰티 특화. "근거" 열은 §3 규칙 번호 또는 출처.

### 2-1. Overview — 지금 손봐야 할 것 한 줄

| 옵션 | 문장 예시 | 근거 |
|---|---|---|
| 이번 주 가장 큰 변화 1개 | "세럼 A의 성분 섹션 이탈이 지난주보다 늘었습니다 (n=412)" | Few: 대시보드는 한 화면에서 한눈에 [49]. 단일 결론 우선 |
| 신상품 첫 반응 | "등록 3일차: 노출 1,200 · 상세 진입 8% · 담기 2건. 코호트 첫 주 중앙값 5%" | Shopify식 코호트 중앙값 비교 [47] |
| 재구매 배지 | "라인 재구매 27% · 상품 재구매 14%" | Amazon ABA Repeat Purchase Behavior가 같은 지표를 브랜드에 제공 [45] |
| 피드백 신규 건수 + 최다 분류 | "이번 주 피드백 12건, 향 5건" | R-7 |
| 교차 브랜드 유입 | "내 상품 조회의 31%가 다른 브랜드를 보던 고객입니다" | R-9. Amazon New-to-Brand 개념 [60] |
| 추천 기여 | "담기 중 22%가 추천 카드에서 왔습니다" | R-9 |
| 커먼즈 한 줄 | "몰 전체에서 PDRN 관심이 2주 연속 올랐습니다" | 올리브영이 성분 검색량 증가를 뉴스로 발표하는 것과 같은 형태 [21] |
| 표본 배너 | "표본 200 미만 지표는 흐리게 표시됩니다" | Amazon 100명 [45], Shopify "충분한 유사 스토어" [47] 관행 |

### 2-2. 상품 분석

| 옵션 | 문장 예시 | 근거 |
|---|---|---|
| 퍼널 병목 위치 | "노출→클릭은 상위, 상세→담기가 하위 30%. 상세페이지 문제" | 전환 세션은 비전환 대비 페이지뷰 5배 [5]. 단계별 위치 비교 |
| 이탈 지점 + 이유 힌트 ★ | "사용법에서 오래 보고 나갑니다" | R-1c |
| 예측 적합 고객 vs 실측 ★ | "예측: 건성 1.9배 / 실측: 건성 담기율 3.1%" | R-2 스킨케어 구매 최중요 요인 = 피부타입 적합 93% [23] |
| 옵션 왕복 | "용량 옵션을 평균 3.2회 오갑니다" | R-6 |
| 대신 산 상품의 특징(익명) | "이 상품 본 뒤 다른 브랜드 산 87명. 평균 1.2만 원 저렴, 70% 세라마이드" | Walmart Scintilla 'switching' 리포트가 같은 개념 [46]. 실명 금지 규칙 |
| 비교된 상품 수 | "평균 3.4개와 비교됨" | 중가 상품 구매 전 54%가 2~3채널 검토 [62] |
| 퀵룩→상세 전환 | "퀵룩 열고 상세로 안 넘어가는 비율 62%" | Baymard: 시각 주도형 제품엔 퀵뷰 유효, 스펙 주도형엔 부적합 [17] |
| 찜 대비 담기 | "찜은 많은데 담기가 적다" | NN/g: 사용자는 장바구니를 임시 보관·비교 공간으로 씀 [16] |
| 장바구니 제거·이탈 | "담은 뒤 제거 28%" | 장바구니 이탈 평균 70.22%, 이유 1위 추가 비용 40% [15] |
| 미량 성분 경고 ★ | "태그로 내세운 센텔라가 전성분 25위(미량)" | 식약처 기능성 고시는 함량 기준(나이아신아마이드 2~5% 등) [30]. 함량 없는 성분 소구는 실증 대상 [38] |

### 2-3. 정보 관심도 ★

| 옵션 | 문장 예시 | 근거 |
|---|---|---|
| 콘텍츠별 주목도 × 전환 기여 | "임상 근거는 짧게 보지만 본 사람의 담기율이 1.6배" | Contentsquare 존 지표 체인 [8][9][10]; 주목의 66%는 폴드 아래 [4] |
| 긁어간 성분 TOP | "나이아신아마이드를 긁어 밖에서 검색합니다" | R-1f |
| 긁어간 문장 유형 | "클레임 문장을 긁어감 → 근거를 찾고 있다" | R-1f |
| 성분 표시 모드 효과 | "핵심 성분 모드 담기율이 전성분 모드보다 높음" | R-1e |
| 배지 신뢰도 | "비건 배지 체류 0.3초, 무향 2.1초" | R-4 클레임 신뢰 어려움 79% [24] |
| 선언 이유 vs 행동 ★ | "성분 때문에 샀다고 답했지만 리뷰를 가장 오래 봄" | R-5 |
| 리뷰 필터 효과 | "'내 피부 리뷰' 필터 쓴 고객 전환 2.3배" | 리뷰 필터 유용 77% [13]; 세포라는 리뷰어 피부타입·톤 공개 [18] |
| 검증 행동 실행률 | "전성분 펼친 방문의 담기율 4.8% vs 1.9%" | R-1d |
| 이미지 소비 | "갤러리 3장 이상 본 고객이 담기 2배" | 쇼핑객 97%가 타인 사진·영상 찾음 [14]; 상품당 약 6장 이미지 기대 [63] |
| 스크롤 도달 | "리뷰(75% 지점) 도달 38%" | 평균 스크롤 도달 50% [5]; GA4는 90% 도달 1회만 기록 [1] |

### 2-4. 고객군

| 옵션 | 문장 예시 | 근거 |
|---|---|---|
| 피부타입×톤 격자 전환 | "건성·밝은 톤 담기율 최고" | 리뷰 읽을 때 77%가 피부타입·효과, 73%가 톤·쉐이드 주목 [14] |
| 복합성은 톤으로 ★ | "복합성 고객(55%)은 타입보다 톤이 반응을 가릅니다" | `[실측]` 타입 편차 0.053 vs 톤 0.269 |
| 고객군별 가장 오래 본 콘텐츠 | "건성은 성분, 지성은 리뷰" | R-2 |
| 고객군별 구매 이유 1위 | "지성은 '같은 피부 리뷰'가 1위" | R-5 |
| 고객군 × 가격 밴드 | "건성 고객은 4~6만 원대에 가장 반응" | `[실측]` price_bin 유지 lift 1.30x; 74%가 저가 메이크업도 효과 동일 [25] |
| 고민 커버 격자 ★ | "내 고객 고민 2위 모공인데 라인에 모공 상품 없음" | 미국 여성 고민 주름 46%·여드름 26%·민감 23%·홍조 22%·모공 21% [22] |
| 놓치는 고객군 | "코호트는 지성에서 잘 파는데 나는 하위 25%" | Shopify 분위 [47] |
| 기피 성분 세그먼트 | "무향 필터를 켠 고객 18%" | 향료 = 화장품 접촉피부염 최다 원인(30~45%) [31]; 한국 '민감 피부용' 클레임 26%→35% [26] |

### 2-5. 행동 분석

| 옵션 | 문장 예시 | 근거 |
|---|---|---|
| 의도 단계 분포 | "탐색 62% · 검증 25% · 결정 13%" | Clarity 세션 intent Low/Medium/High(5초 체류·상호작용 기준) [3] |
| 마찰 위치 | "성분 섹션에 rage_click 집중. 펼치기 버튼 문제" | R-8 |
| 되돌아간 지점 | "리뷰→성분으로 되돌아감" | R-1 scroll_backtrack |
| 빠른 이탈 | "3초 내 이탈 41%" | 55%가 15초 미만 체류 [4]; 단일 페이지 이탈 53% [6] |
| 진입 경로별 전환 | "추천 카드 진입이 목록 진입보다 담기 1.8배" | 추천 시스템 필드 실험: 조회 +15.3%, 전환 +7.5% [61] |
| 정렬·필터 사용 | "고민 필터 사용자가 가격 필터보다 전환 높음" | — (우리 로그) |

### 2-6. 리뷰 분석

| 옵션 | 문장 예시 | 근거 |
|---|---|---|
| 주요 평가 요소 | "보습·흡수 긍정, 향 부정" | 아마존 화장품 리뷰 LDA 6주제: 피부 자극, 보습, 색상·지속, 향·성분, 커버력, 패키징 [54] |
| 자극·트러블 언급 | "민감성 리뷰어의 자극 언급 12%" | 향료 알레르기 Fragrance Mix I 양성률 12.8% [32] |
| 피부타입별 평점 갈림 | "건성 4.6 / 지성 3.4" | 리뷰에서 피부타입 주목 77% [14] |
| 재구매 선언 | "'재구매' 언급 23%" | R-6 |
| 리뷰 열람률 | "리뷰 펼침 34%" | 95% 사용자가 제품 파악에 리뷰 활용 [12] |
| 사진 리뷰 | "사진 리뷰 우선 열람" | 47%가 사진+텍스트 리뷰 최고 영향 [64] |

### 2-7. 성분 분석 ★

| 옵션 | 문장 예시 | 근거 |
|---|---|---|
| 성분 갭 | "고객이 찾는 성분 1위 세라마이드, 내 라인에 없음" | 특정 성분 찾는 구매자 밀레니얼 61%·Gen Z 46% [20] |
| 성분 × 피부 반응 | "살리실산은 지성 1.8배, 건성 0.5배" | `[실측]` 친화도; 살리실산 OTC 여드름 표준 [28] |
| 함량 위치 | "히알루론산 3위(주요), 레티놀 22위(미량)" | 식약처 고시 함량 [30] |
| 주의 성분 포함 상품 수 | "변성알코올 포함 3종" | R-3 |
| 성분 트렌드 | "PDRN 관심 2주 연속 상승" | 올리브영 PDRN 검색 +695% [21]; Spate PDRN YoY +609.8% [65] `[벤더]` |
| 병용 주의 조합 | "레티놀 세럼과 AHA 토너가 같은 장바구니 15%" | R-3 병용 |
| 시즌 곡선 | "선케어는 5~6월 피크" | 선케어 매출 47%가 여름, 5~6월 피크 [37] |

### 2-8. 고객 피드백 ★ (비공개)

| 옵션 | 문장 예시 | 근거 |
|---|---|---|
| 개별 AI 요약 + 원문 | "**용기 사용성 개선 요청** — 잔량 적을 때 펌프가 안 나옴" + 원문 | R-7 |
| 분류별 건수 | "향 31% · 용기 24% · 가격 18%" | ABSA 논문 속성: 가격·패키징·향·지속력·보습 [54] |
| 반복 요청 그룹 | "'무향 버전' 요청 7건" | Glossier가 댓글 키워드 mild·glowy·moist를 모아 제형 결정 [56] |
| 종합 요약 | "성능 만족 높고 향·용기 개선 요청 반복" | — |
| 담당 라우팅 ★ | "처방 3 · 포장 4 · 마케팅 2 · 가격 3" | R-7 |
| 피부타입별 피드백 | "자극 피드백 5건 중 4건이 민감·건성" | Yotpo 사례: 구매 후 피부타입·고민 질문 수집 [66] |
| 구매자 vs 비구매자 | "구매자는 용기, 비구매자는 가격" | 구매 후 설문 응답률 20~30% 양호, 45~50% 벤더 평균 [67][68] `[벤더]` |
| 반영 루프 상태 | "읽음 8 · 반영 3 · 답글 3" | Medallia×Benefit: 피드백→매장 NPS 9개월 +5.8p [69] `[벤더]` |

### 2-9. 추가 제안 화면

| 화면 | 이유 | 근거 |
|---|---|---|
| 커먼즈 리포트 | 혼자 쌓아도 못 만드는 시장 지식 | 올리브영이 연 1억 건 데이터로 트렌드 리포트를 정례 발간 [70] |
| 내 위치(벤치마크) | "이 수치가 좋은 건가" | Shopify Benchmarks 모델 [47] |
| 재구매·리마인드 | 소모품 특성 | Amazon ABA Repeat Purchase [45]; 선케어 연 구매 약 3회 [37] |
| 신상품 첫 14일 | 콜드스타트 | 콘텐츠+협업 결합 콜드스타트 [71] |
| 매출·정산 | PAID 주문 기준 | — |

---

## 3. AI 해석 규칙 카탈로그 — "이 데이터는 → 이런 뜻이다"

프롬프트의 시스템 지식으로 넣을 규칙이다. 각 규칙은 **신호 → 의미 → 근거 → 권고 → 함정** 순서다.

### R-1. 스크롤·체류

| 신호 | 의미 | 근거 | 권고 | 함정 |
|---|---|---|---|---|
| a. `section_dwell(ingredients)` 길다 | 적합성 검증 | PDP에서 찾는 핵심 정보 = 재료·성분·제조 관행 [12b] `[연구]`; 특정 성분 찾는 구매자 43~61% [20] | 성분 설명·함량 위치 보강 | 체류가 길다=좋다 아님. Contentsquare도 노출(Exposure)과 클릭 유인(Attractiveness)을 분리 [8][9] |
| b. `section_dwell(reviews)` 길다 | 확인 단계 | 95%가 리뷰로 제품 파악 [12]; 77%가 리뷰어 피부타입·효과 주목 [14] | 리뷰어 피부타입 표기 | 리뷰 수 적으면 체류 길어도 못 산다 |
| c. `how_to_use` 길다 + 이탈 | 설명 난이도 | 설명 부족 시 1~3분 다른 섹션 뒤지거나 포기 [12c] `[연구]` | 단계 이미지·양·주기 | 구매 가정 탐색일 수도. 이탈 여부로 가른다 |
| d. 검증 행동(펼침·필터·리뷰 확장) 실행 후 전환 비교 | 능동 확인자가 더 사나 | Clarity intent: 상호작용 없는 체류는 Low intent [3] | 검증 요소를 앞으로 | 상호작용 없음 ≠ 부정 |
| e. `ingredient_view_mode_change` | 전성분=기피 성분 검색, 핵심=효능 확인 | "BPA-free" 류 불포함 표기에 긍정 반응 [12b] | 기피 성분 유무 배지 | 펼친 뒤 이탈이면 기피 성분 발견 |
| f. `text_selection`·`text_copy` | **관심의 크기.** 드래그·복사된 성분 = 사용자가 가장 관심을 두는 성분 | 복사 = 해당 텍스트 관심 추론(특허) [72]; Tynt가 복사 단어 수를 콘텐츠 관심 지표로 사용 [73] | 그 성분을 상세·소구의 중심에 | "설명 부족" 으로 단정 금지. 어려움 여부는 같은 구간의 `scroll_backtrack`·이탈·담기율 lift 를 함께 봐야 한다(R-1f-2). 복사-전환 상관 공개 연구 없음 `[추정]` |
| f-2. 드래그 + 같은 성분 구간 되돌아 읽기↑ + 이탈↑ + 담기 lift<1 | 관심은 있는데 이해가 안 됨(설명 난이도) | 설명 부족 시 다른 섹션을 뒤지거나 포기 [12c] `[연구]` | 그 성분 설명·근거 추가 | 네 신호 중 둘 이상 동반될 때만. 드래그만으로는 판단하지 않는다 |
| f-3. 드래그 + 담기 lift≥1.3 | 관심이 결정으로 이어짐(소구 성분) | Contentsquare 존 지표 체인 [8][9][10] | 그 성분을 카드·첫 화면에 | — |
| g. `scroll_depth` 최대 25% 이하 다수 | 첫 화면 기대 불일치 | 평균 스크롤 도달 50% [5]; 55%가 15초 미만 [4] | 목록 카드 문구와 상세 첫 줄 일치 | 누적 합산 금지. GA4도 90% 도달 1회만 [1] |
| h. `similar_products` 길다 | 현재 상품 불만족 | `[추정]` | 차별점 상단 | 다음 클릭으로 보강 |
| i. `co_visible_blocks > 2` | 귀속 불명 | Contentsquare Exposure Rate는 존 중간선 150ms 표시 기준으로 존별 분리 [8] | 집계 제외 | 제외 안 하면 주목도 왜곡 |
| j. `media_view` 3장+ | 질감·색을 이미지로 판단 | 97% 타인 사진·영상 찾음 [14]; 상품당 약 6장 기대 [63]; 61% 이미지·영상이 최대 결정 요인 [74] `[벤더]` | 텍스처 클로즈업 | 이미지 수-전환 정량 없음 |

### R-2. 피부타입·고민 → 어떤 콘텍츠·어떤 소구

| 신호 | 의미 | 근거 |
|---|---|---|
| 페르소나 피부타입 | 스킨케어 구매 최중요 요인 | 피부타입 적합 93%, 문제 해결 89%, 성분 89%, 효과 증거 78%, 가격 70% [23] `[리서치, 2차 인용]`; 화해 설문 1위 "내 피부 타입·고민" [19b] |
| 복합성 | 타입 판별력 없음, 톤이 유효 | `[실측]` |
| 고민 축 | 고민별 소구 우선순위 | YouGov 2024: 여성 주름 46%·여드름 26%·민감 23%·홍조 22%·모공 21%; 30세 미만 60% 여드름 [22] |
| 민감 피부 | 한국·일본 시장 클레임 성장 | 한국 '민감 피부용' 클레임 26%(2021)→35%(2023) [26]; 올리브영 진정·장벽 검색 +150% [75] |
| 리뷰 필터 사용 | "같은 피부" 후기 탐색 | 리뷰 필터 유용 77% [13]; 세포라 리뷰어 피부톤·타입·모발·눈색 공개 [18] |
| 개인화 기대 | 없으면 불만 | McKinsey 2021: 71% 기대, 76% 없으면 불만 (뷰티 특화 아님) [76] |

### R-3. 성분 → 어떤 고객·어떤 고민 (30종)

`[실측]`은 우리 카탈로그 친화도(`ingredient_skin_affinity.csv`). 근거 강도를 반드시 함께 쓴다. **성분 문장에는 그 성분을 찾는 고객군을 붙인다.**

| 성분 | 타깃 피부·고민 | 근거 강도·출처 | 주의·병용 |
|---|---|---|---|
| 히알루론산 | 건성 `[실측 1위]`, 전 타입 보습 | Harvard Health: 안전, 레티놀·BPO·살리실산 병용 가능, 여드름 유발 안 함 [77] `[전문가]`; 8주 연구는 소규모·업체 후원 [78] | 자극 거의 없음 |
| 세라마이드 | 건성·민감 장벽 | Man/Feingold/Elias 1996: 세라마이드:콜레스테롤:지방산 등몰 혼합이 회복, 단일 지질은 지연 [79] `[연구]`; 각질층 지질 ~50% [80] | 단독보다 3종 배합이 근거 |
| 판테놀(B5) | 건성·손상 | Proksch 2017 리뷰: 보습·장벽·재상피화 [81] `[연구]` | — |
| 스쿠알란·호호바·시어버터 | 건성 에몰리언트 `[실측]` | 스쿠알란 1차 문헌 없음 `[벤더]`; 호호바 리뷰 [82]; 시어버터 항염은 동물 모델 [83] | "지성에 코메도제닉"은 토끼귀 실험 기반, 사람 대조 없음 [33][34] |
| 센텔라(시카) | 민감·손상, 홍조 | 상처치유 SR 2022 [84]; 아토피는 보조 수준 | 약한 감작원, 접촉피부염 증례 [85] |
| 알란토인 | 진정 | FDA OTC 피부보호제 0.5~2% [86] `[법령]` | — |
| 알로에 | 화상·자극 후 | 2도 화상 메타분석: 치유 4.44일 단축 [87] `[연구]` | 접촉피부염 증례 |
| 녹차(EGCG) | 지성·여드름 | 메타분석 5 RCT n=247: 국소 녹차 병변 유의 감소 [88] `[연구]` | 경구는 효과 미미 |
| 감초(글라브리딘) | 색소침착 | JDD 2020 리뷰: 대두·감초 임상 근거 최다 [89] | — |
| 살리실산(BHA) | 지성 `[실측 1위]`·여드름·모공 | OTC 0.5~2% 표준; AAD 임신 시 2% 초과 회피 [28] `[전문가·규제]` | 광민감 근거 없음(AHA와 구분) |
| AHA·글리콜산 | 칙칙함·피부결 `[실측 지성]` | FDA: 4주 사용 후 UV 홍반 민감 18% 증가, 중단 1주 후 정상 [29] `[규제]`; CIR ≤10%, pH ≥3.5 | 자외선차단 필수. 레티놀 동시 사용 자극은 `[전문가]` |
| 락틱애시드 | 건성·거침 | Smith 1996: 12% 3개월 표피·진피 두께 증가 [90]; 세라마이드 합성 증가 [91] `[연구]` | 12% 이상 자극 |
| 윌로우바크 | 마일드 각질 | 0.5% 살리신 12주 n=30 비대조 [92] `[연구, 약함]` | "천연 BHA" 주장 근거 약함 |
| 아연 | 지성·트러블 | Gupta 2014 리뷰 [93] | — |
| 나이아신아마이드 | 모공·색소·피지 `[실측 상위]` | Hakozaki 2002 RCT 5% 4주 색소 감소 [94]; Draelos 2006 2% 피지 감소 n=100 [95] `[연구]`; 식약처 미백 고시 2~5% [30] `[법령]` | **비타민C 병용 금기 근거 없음** [27] |
| 비타민C | 칙칙함·색소 `[실측 중성]` | Pullar 2017 리뷰: pH<3.5 침투, 비타민E 시너지 [96] `[연구]` | 산화 불안정, 저pH 자극 |
| 레티놀 | 주름·광노화 | AAD: 밤에만, 자외선차단 필수, 격일 시작 [97]; **임신 중 금지(OTC 포함)** [28] `[전문가]`; 식약처 주름 고시 2,500 IU/g [30] | 트레티노인은 BPO+광에서 2시간 50% 분해 [98]; AHA/BHA 동시 자극은 `[전문가]` |
| 아데노신 | 주름 | Abella 2006 n=126 위약대조(로레알) [99]; 식약처 0.04% [30] | 업체 후원 위주 |
| 펩타이드 | 주름·탄력 | 팔미토일 펜타펩타이드 12주 n=93 [100] | 소규모·업체 후원 |
| 콜라겐(국소) | 표면 보습 | 진피 콜라겐 증가 임상 근거 **확인 불가** | 효능 주장 주의 |
| 카페인 | 혈관형 다크서클 | 소규모 젤 시험만 | 색소형엔 무효 |
| 발효·프로바이오틱 | 민감·장벽(보조) | 리뷰 다수, 근거 초기 [101] | 확정 권고 불가 |
| 로즈힙·장미 | 건성·흉터 / 향 | 로즈힙 리뷰 2024 [102] | 로즈는 EU 26개 표시의무 향료 알레르겐 함유 [103] |
| 요소(우레아) | 건성·각화 | ≤10% 보습, 10~20% 박리, 40% 각질용해 [104] | 고농도 작열감 |
| SPF | 전 타입 | AAD: SPF30+, 브로드스펙트럼, 2시간마다 [105]; 임신·민감은 징크옥사이드/티타늄디옥사이드 [28] | 백탁·끈적임 피드백 잦음 `[추정]` |
| 실리콘(다이메티콘) | 보호막·발림 | FDA OTC 피부보호제 1~30% [86] | "무실리콘" 기피 대상 |
| 미네랄오일·페트롤라툼 | 극건성 | Kligman 1996: 토끼·사람 모두 비코메도제닉 [34]; Rawlings 2012 리뷰 [106] | 지성 "모공 막힘" 우려는 근거 약함 |
| 변성알코올 | (기피) | 에탄올이 각질층 지질 제거 → 장벽 투과 가능, 연구 상충 [107] `[연구]`; 건성·민감 회피는 `[전문가]` | 민감·건성 이탈 원인 후보 |

### R-4. 마케팅 태그(clean 16 · texture 5) → 누가 반응하나

| 태그 | 반응 고객 | 근거 | 함정 |
|---|---|---|---|
| 무향 / 저자극 / 알코올 무첨가 | 민감·건성 | 향료 = 화장품 접촉피부염 최다(30~45%) [31]; NACDG 2019-20 Fragrance Mix I 양성 12.8%, 3위 [32]; ACDS 2007 Allergen of the Year = 향료 [31b] `[연구]` | 있으면 좋은 게 아니라 없으면 탈락 |
| 파라벤·설페이트·프탈레이트 무첨가 | 안전 지향 | Mintel: 22% 무첨가 추구, 21% 민감 전용 관심 [26b] `[리서치 2차]` | — |
| 클린 / 비건 / 친환경 | 가치 소비 | **클레임 피로:** 79%가 지속가능성 클레임 신뢰 어려움, 85% 독립 검증 더 신뢰 [24]; 절반 이상 "클린" 진정성 의심 [24b]; Circana: 클린 기준 부재로 혼란, 임상 브랜드로 이동 [24c] | 배지 체류 짧으면 "읽히지 않는다" |
| 리필 가능 | 재구매 | — | 용기 피드백과 연결 |
| 옥시벤존 무첨가 | 선케어 | — | 선케어 외 무의미 |
| 촉촉한 / 광채 / 자연 마무리 | 사용감·톤 | 스킨케어 리뷰 토픽에서 텍스처·투명감이 감각 속성 1위 [108] `[연구 2차]` | 톤 축과 함께 |

**규칙:** 배지가 많을수록 각 배지 주목도는 떨어진다 `[추정]`. 배지 체류 짧고 전환 기여 없으면 "읽히지 않는다"로 결론.

### R-5. 구매 이유 선언(10종) ↔ 행동 대조

근거: Morwitz, Steckel, Gupta 2007 메타분석 — 구매의향은 기존 제품·특정 브랜드 질문·단기·비교 모드에서 판매를 잘 예측하고, 신제품·카테고리 질문에서는 약하다 [53] `[연구]`. 우리 설문은 구매 직후·특정 상품·선택지 고정이라 예측력이 높은 조건에 해당한다. 그럼에도 행동과 갈리는 셀이 인사이트다.

| 선언 | 기대 행동 | 갈리면 |
|---|---|---|
| `ingredient` | 성분 체류·펼침·긁기 | 성분을 안 봤는데 성분이라 답함 → 배지가 성분처럼 보임 |
| `skin_fit` | 리뷰 피부 필터, persona_match 체류 | 적합 근거 콘텐츠 부재 |
| `reviews` / `review_same_skin` | 리뷰 체류·필터 | 평점·건수만 보고 결정 |
| `price` | 옵션 왕복, 가격 텍스트 선택 | — |
| `brand_trust` | 브랜드 스토리 체류, 라인 재방문 | 신규 브랜드면 추천 신뢰 전이 |
| `texture_finish` | 미디어 3장+ | — |
| `clean_claim` | 배지 체류, 전성분 펼침 | — |
| `recommendation` | `recommendation_click` 진입 | 진입 없이 선언 → 노출 인지 |
| `restock` | 같은 상품 2회 구매 | 행동 재구매와 갈리면 추론 한계 표시 |

### R-6. 옵션·가격·용량

| 신호 | 의미 | 근거 |
|---|---|---|
| 소용량 선택 高 | 시험 구매 | 올리브영 2026 트렌드 "소용량 프리미엄" [75] `[공식]`; 세포라 샘플링 트라이얼→구매 31%는 `[벤더 자사 사례]` [109] |
| 대용량 선택 高 | 충성·재구매 | `[추정]` |
| `price_bin` 밴드 집중 | 지불 의사 | `[실측]` lift 1.30x; 74%가 저가도 효과 동일, 18~34세 1/3 SNS 듑 구매 [25] |
| 찜 高·담기 低 | 가격 저항 | NN/g: 장바구니가 임시 보관 공간 [16] |
| 세럼 재구매 주기 | 브랜드 안내 4~10주 | 30ml 세럼 1일 2회: 4~5주 [40], 약 6주 [41], 8~10주 [42] `[공식 브랜드 FAQ]`. 크림·클렌저는 공개 근거 없음 → 실측 대기 |
| 선케어 구매 빈도 | 연 약 3회 | Circana 2026 [37] |
| 뷰티 재구매율 | 21~35% 범위 주장 | `[벤더 2차, 방법론 불명]` [110] — 참고만 |

### R-7. 리뷰·피드백 언어 → 담당 부서

논문이 실제로 쓴 화장품 리뷰 속성: 가격·패키징·향·지속력·보습 (Female Daily 계열 ABSA) [54b][54c]; 피부 자극·보습·색상 지속·향/성분·커버력·패키징 (아마존 LDA, KCI 2024) [54]. Revuze가 화장품 산업에 보고하는 차원: 텍스처·성분·패키징·쉐이드·포뮬러 성능·향·SPF·지속력 [55b] `[벤더]`. 우리 8종은 이들의 합집합이다. **6축을 한 번에 쓴 단일 논문은 없다.**

| 표현 | aspect | 담당 | 개선 방향 |
|---|---|---|---|
| 끈적임, 밀림, 백탁, 흡수 안 됨 | `texture` | 처방(제형) | 디마프가 백탁·발림성 불만으로 선크림 재생산 [58] |
| 자극, 따가움, 붉어짐, 트러블 | `ingredient` | 처방(성분) | 향료·변성알코올·고농도 산 확인 (R-3) |
| 향 강함, 무향 있으면 | `scent` | 처방(향) | 무향 버전. 향료 알레르기 근거 [31] |
| 펌프, 뚜껑, 위생, 용량 표시 | `packaging` | 포장 | 리필 |
| 효과 없음, 기대와 다름 | `effect` | 마케팅(클레임)·처방 | 클레임 톤 조정. **표시광고 규제 확인 (§4-3)** |
| 순서 모름, 양 모름 | `usage` | 콘텐츠 | 사용법 이미지 (R-1c) |
| 비쌈, 소용량, 세트 | `price` | 가격·상품기획 | 소용량 [75] |
| 재구매, 계속 쓸 것 | (긍정) | 마케팅 | 리마인드 |

**규칙:** 요약은 원문과 함께. 명사형 제목 + 한 문장. 원문에 없는 원인을 추가하지 않는다.

### R-8. 마찰 신호는 화면 문제로 먼저

| 신호 | 공식 정의 | 근거 | 절대 하지 말 것 |
|---|---|---|---|
| `rage_click` | 짧은 시간 동일 영역 반복 클릭 | Microsoft Clarity [2]; Fullstory [2b] `[공식]` | 상품 선호로 해석 |
| `dead_click` | 클릭 후 합리적 시간 내 피드백 없음 | Clarity [2] | 선호 점수 합산 |
| quick back / `scroll_backtrack` | 임계 시간 내 복귀 / 과도 스크롤은 이탈 기여 | Clarity Quick back·Excessive scrolling [2] | — |
| 좌절 세션 비율 | 2024년 방문 40% 좌절 경험, 참여 -15%; 2025년 35.2% [6][6b] `[벤더]` | 레이지 클릭 -1.5%p → 세션당 +1 PV [6b] | 좌절-전환 상관계수는 미공개 |

### R-9. 세션·교차 브랜드·추천

| 신호 | 의미 | 근거 |
|---|---|---|
| 세션 첫 브랜드 ≠ 내 브랜드 → 내 상품 조회 | 교차 브랜드 유입 | Amazon New-to-Brand: 12개월 내 미구매 고객 [60] `[공식]`; 마켓플레이스가 리서치 채널 54% [62] |
| 내 상품 조회 후 타 브랜드 구매 | 경쟁 열위(익명) | Walmart Scintilla switching 리포트 [46]. 실명 금지 |
| 추천 클릭 경유 | 추천 기여 | 추천 도입 필드 실험 조회 +15.3%·전환 +7.5% [61]; "아마존 35%"는 McKinsey 추정 [59], Netflix 80%는 자체 서술이며 2026 논문은 -4~-12% [59b][59c] |
| 추천 노출 | 가중 0, 분모만 | 암묵 피드백은 부정 신호 없음·노이즈, 횟수는 신뢰도 [111] `[연구]`; 클릭은 informative but biased [112] |
| 체류 시간 | 클릭보다 나은 타깃 | Yi et al. 2014: dwell time 최적화가 참여·CTR 개선 (뉴스 도메인) [113]; YouTube 2012 시청시간 전환 [114] |
| 추천 다양성 | 만족 상승 | Ziegler 2005: 다양화가 만족 개선, 정확도 소폭 하락 [115]; Steck 2018 캘리브레이션 [116] |
| 추천 이유 표시 | 수용도 향상 | Herlocker 2000: 설명이 CF 수용도 개선 [117]; 커머스 "왜 추천" A/B 수치는 확인 불가 |

### R-10. 시간·시즌

| 축 | 근거 | 문장 방향 |
|---|---|---|
| 여름(5~8월) 선케어 | 선케어 매출 47%가 여름, 5~6월 피크 [37] `[리서치]`; 올리브영 선케어 매출 전년 7~9월 대비 +281% [39]; 5월 선스틱 검색 +115%·선스프레이 +196% [39b] `[공식·언론]` | "선케어 관심 상승 시작" |
| 겨울 건조 | 각질층 수분 여름 최고·겨울 최저, TEWL 겨울 최고 (72명 4계절) [35]; 여름 전환 시 TEWL -22% [36] `[연구]` | 장벽·보습 소구. **매출 정량은 확인 불가** |
| 환절기(9월) | 9월 올영세일 PDRN +695%, 펩타이드 +72%, 나이아신아마이드 +65% [21]; 고보습 수요 [21b] | 진정·장벽 |
| 연중 SPF | 비수기 유럽 프레스티지 SPF +20% [37] | 계절 기저 상승 |
| 성분 트렌드 | Spate: PDRN, Volufiline, beta glucan, HOCl, peptides [65b] `[벤더]` | 커먼즈 |

### R-11. 신상품·콜드스타트

| 상황 | 해석 | 근거 |
|---|---|---|
| 로그 0 신규 상품 | 속성으로 코호트 실적 빌림 | Schein 2002 콘텐츠+협업 결합 [71] |
| 리뷰 0 | 성분·임상 근거가 결정 대신 | Google messy middle: 가상 브랜드가 리뷰+혜택만으로 28% 선호 [118] — 사회적 증거 부재의 무게 |
| rating 주입값 | 실측 아님 | 화면 표시 금지 (`rating_source=injected`) |

---

## 4. 인사이트 문장 생성 프롬프트 골격

### 4-1. 입력 슬롯

```
brand_id, 기간, 화면(Q1~Q5)
지표: [{name, value, n, cohort_median, cohort_p25, cohort_p75, prev_value}]
엔티티: 내 상품명(실명), 성분 표준명, content_kind, 피부타입×톤 셀, aspect
어휘 사전: product-feature-vocab.json (성분 30·고민 9·clean 16·texture 5)
해석 규칙: 이 문서 §3 R-1~R-11
금지어 사전: §4-3
```

### 4-2. 출력 형식 (고정)

```
1) 결론 한 줄 — 뷰티 명사(성분·피부타입·고민·콘텐츠) 필수
2) 근거 2~3개 — 숫자 + (n=표본) + 코호트 중앙값
3) 권고 액션 1~2개 — 상세페이지/타깃/제품/처방·포장/가격 중 어느 단위인지
4) 신뢰도 — 높음/보통/낮음 + 이유
```

### 4-3. 금지·억제 규칙

**데이터 해석**
1. 표본 200 미만으로 결론을 쓰지 않는다. (관행: Amazon 100명 [45], Shopify "충분한 유사 스토어" [47])
2. 인과를 단정하지 않는다. "~에서 이탈했다. ~일 가능성".
3. 타 브랜드·상품 실명·절대 매출 금지. 코호트 분위와 속성 차이만. (Shopify: 중앙값·25·75만 [47])
4. 코호트 브랜드 5개 미만, 한 브랜드 50% 이상 지배면 비교 문장 생성 금지.
5. 마찰 신호를 상품 선호로 해석하지 않는다 (R-8).
6. 체류 길다 = 좋다 금지. 전환 기여와 함께 (R-1a).
7. 피드백 원문은 피드백 화면에서만 인용.
8. 주입 평점을 실측처럼 쓰지 않는다.
9. 복합성은 톤으로 서술 `[실측]`.
10. 성분에는 찾는 고객군·고민을 붙인다 (R-3).
11. 벤더 수치·관행 수치는 "업계 관행 기준"/"벤더 자료" 표기.
12. 한 화면 결론 1개, 권고 2개까지.

**표시·광고 규제 (AI가 브랜드에 권고 문구를 제안할 때 반드시 적용)** `[법령·공식]`
13. 화장품법 제13조: 의약품 오인, 기능성 오인, 기만 표시·광고 금지. 위반 시 1년 이하 징역 또는 1천만 원 이하 벌금 [119].
14. 제14조 실증제: 식약처 요청 시 15일 내 실증자료 제출, 미제출 시 광고 중지 [120].
15. 식약처 「화장품 표시·광고 관리 지침」(2025-08-14) 별표1 **금지 표현**을 권고 문장에 쓰지 않는다: 아토피·건선·소양증·여드름·기미·주근깨·화상 "치료", 살균·소독·항염·항균·해독, 혈액순환·피부재생·세포 재생·호르몬, "홍조·홍반 개선·제거", "뾰루지 개선", "상처 치료" [121].
16. **실증 대상 표현**은 "실증자료 필요" 꼬리표를 붙인다: "여드름성 피부에 사용 적합", "다크서클 완화", "피부장벽 손상 개선에 도움", "피지분비 조절", "붓기 완화", "미세먼지 차단" [121].
17. 2025-01 추가 금지: "병원용·피부과 전용", "엑소좀"(인체유래 오인), "마이크로니들", "피부나이 n세 감소" [122].
18. 기능성화장품으로 심사된 효능(미백·주름·자외선차단)만 해당 표현 허용. 고시 함량: 나이아신아마이드 2~5%, 아데노신 0.04%, 레티놀 2,500 IU/g 등 [30].

> 예: 피드백 "홍조가 좋아졌어요"를 근거로 AI가 "홍조 개선" 소구를 권고하면 15번 위반이다. "진정 사용감 만족 후기가 많습니다. 홍조 개선은 광고 표현으로 쓸 수 없습니다"로 써야 한다.

### 4-4. 문장 템플릿 예시 30개

| 화면 | 템플릿 |
|---|---|
| Overview | "{피부타입} 고객이 {상품}의 {섹션}에서 이탈합니다 (n={n})" |
| Overview | "{상품} 등록 {d}일차: 상세 진입 {x}%, 코호트 첫 주 중앙값 {m}%" |
| Overview | "이번 주 피드백 {n}건, {aspect} {k}건이 가장 많습니다" |
| 상품 | "{상품}은 {단계}에서 코호트 하위 {p}%. {다음 콘텐츠} 점검" |
| 상품 | "예측 적합 고객({피부타입} {lift}배)과 실측 담기율이 {일치/갈림}" |
| 상품 | "{상품}을 본 뒤 다른 브랜드를 산 고객 {n}명: 평균 {Δ가격} 저렴, {p}%가 {성분} 함유" |
| 상품 | "{성분}을 태그로 내세웠지만 전성분 {k}위(미량)입니다" |
| 정보관심도 | "{content_kind}는 체류 {s}초로 짧지만 본 고객의 담기율이 {lift}배" |
| 정보관심도 | "{성분}을 긁어 밖에서 검색합니다 → {성분} 설명 추가 ({피부타입} 대상)" |
| 정보관심도 | "'{배지}' 배지는 읽히지 않습니다 (체류 {s}초, 전환 기여 없음)" |
| 정보관심도 | "'{이유}' 때문에 샀다고 답했지만 {content_kind}를 가장 오래 봤습니다" |
| 정보관심도 | "'내 피부 리뷰' 필터 사용 고객 전환 {lift}배 → 리뷰어 피부타입 표기 권고" |
| 고객군 | "{피부타입}·{톤} 담기율 최고({x}%), {피부타입}·{톤} 최저({y}%)" |
| 고객군 | "복합성 고객은 톤이 반응을 가릅니다: {톤} {x}% vs {톤} {y}%" |
| 고객군 | "{피부타입}은 {content_kind}, {피부타입}은 {content_kind}를 봅니다" |
| 고객군 | "내 고객 고민 {k}위 {concern}, 라인에 {concern} 상품 없음 → 다음 제품 후보" |
| 고객군 | "{피부타입} 고객은 {price_bin} 밴드에 가장 반응합니다" |
| 행동 | "{섹션}에 rage_click 집중. 상품이 아니라 {UI 요소} 문제 가능성" |
| 행동 | "추천 카드 진입이 목록 진입보다 담기 {lift}배" |
| 리뷰 | "{피부타입} 리뷰어 평점 {a} vs {피부타입} {b} → 타깃 문구를 {피부타입}으로" |
| 리뷰 | "자극 언급 {p}% (카테고리 평균 {q}%). {의심 성분} 포함" |
| 성분 | "고객이 찾는 성분 1위 {성분}, 내 라인에 없음 ({피부타입} 수요)" |
| 성분 | "{성분}은 {피부타입} {lift}배, {피부타입} {lift}배" |
| 성분 | "{성분} 관심 {k}주 연속 상승, 보유 브랜드 {a}개 중 {b}개" |
| 성분 | "{성분A} 상품과 {성분B} 상품이 같은 장바구니 {p}% → 사용 순서 안내" |
| 피드백 | "**{aspect} 개선 요청** — {한 문장 요약}" + 원문 |
| 피드백 | "'{요청}' 요청 {n}건(서로 다른 고객) → {담당} 검토" |
| 피드백 | "자극 피드백 {n}건 중 {k}건이 {피부타입}" |
| 커먼즈 | "{계절} 진입: {카테고리}·{성분} 관심 상승 시작" |
| 커먼즈 | "{카테고리}는 '{구매 이유}' 때문에 삽니다" (재구매 주기는 실측 후 추가) |

---

## 5. AI 파트가 데이터 파트에 요청할 것

| 필요 | 이유 | 지금 상태 |
|---|---|---|
| `brand_id` 붙은 fact | 브랜드 스코프·교차 유입 | 스키마 수정 필요 |
| `persona_id` 조인 세션 fact | 피부 격자 | 페르소나 테이블 있음 |
| `section_dwell` × `content_kind` × 상품 마트 (`co_visible_blocks ≤ 2`) | 정보 관심도 | 부분 |
| `text_selection.matched_ingredients` 주간 집계 | 성분 관심·트렌드 | 스냅샷만 |
| `purchase_fact` (user, product, brand, ts) | 재구매율·주기 | `purchase` 미활성 |
| 코호트 정의 + 분위 | B층 배지 | 없음 |
| Feedback 테이블 (aspect, text, persona_id, purchased, status) | Q4 | FE localStorage. 백엔드 Jira 146 대기 |
| `rating_source`, `product_source` | 주입 평점 구분 | 계약만 |

## 6. 우선순위 (2주 MVP)

| 순서 | 항목 | 이유 |
|---|---|---|
| 1 | 피드백 개별 요약 + aspect 분류 + 담당 라우팅 (R-7) + 금지어 필터 (§4-3) | 서비스 핵심. 규제 위반 문구 차단은 필수 |
| 2 | Overview 결론 한 줄 (§4 골격) | Few 정의: 한눈에 [49] |
| 3 | 정보 관심도 자동 문장 (R-1) | 우리만 있는 데이터 |
| 4 | 성분 → 고객군 문장 (R-3) | 뷰티 명사 규칙 |
| 5 | 커먼즈 시즌·트렌드 (R-10) | 시계열 마트 필요 |

---

## 출처

**행동 분석 도구·벤치마크**
- [1] Google Analytics Help, Enhanced measurement (scroll 90%) — https://support.google.com/analytics/answer/9216061
- [2] Microsoft Learn, Clarity semantic metrics (rage/dead click, quick back, excessive scrolling), 2025-12 — https://learn.microsoft.com/en-us/clarity/insights/semantic-metrics
- [2b] Fullstory Help, Frustration signals — https://help.fullstory.com/hc/en-us/articles/360020624154
- [3] Microsoft Learn, Clarity user intent metrics — https://learn.microsoft.com/en-us/clarity/insights/user-intent-metrics
- [4] Haile (Chartbeat), TIME 2014, 20억 방문: 55%가 15초 미만, 주목 66% 폴드 아래 — https://time.com/12933/what-you-think-you-know-about-the-web-is-wrong/
- [5] Contentsquare 2023 Digital Experience Benchmark(블로그): 스크롤 50%, 전환 세션 PV 5배 — https://contentsquare.com/blog/average-time-spent-on-websites-is-dropping/
- [6] Contentsquare 2025 Benchmark 보도자료(2024 데이터): 좌절 40%, 단일 페이지 이탈 53% — https://contentsquare.com/press/2025-digital-experience-benchmarks/
- [6b] Contentsquare 2026 Benchmark, Frustration: 35.2% — https://contentsquare.com/guides/digital-experience-benchmark/frustration/
- [7] Contentsquare Benchmark Explorer(9개 산업, 뷰티 세부 없음) — https://csquad.contentsquare.com/benchmarks-explorer
- [8] Contentsquare Help, Exposure Rate(150ms) — https://support.contentsquare.com/hc/en-us/articles/37271856122001-Exposure-Rate
- [9] Contentsquare Help, Attractiveness Rate — https://support.contentsquare.com/hc/en-us/articles/37271697676945-Attractiveness-Rate
- [10] Contentsquare Help, Conversion Rate per Click — https://support.contentsquare.com/hc/en-us/articles/37271852104849-Conversion-Rate-per-Click
- [11] Contentsquare Help, Revenue per Click — https://support.contentsquare.com/hc/en-us/articles/37271900079249-Revenue-per-Click
  (※ [8]~[11]은 Help Center 직접 접근 403, 검색 원문 스니펫으로 확인)

**PDP·읽기 행동 연구**
- [12] Baymard, 95% rely on reviews — https://baymard.com/blog/user-ratings-distribution-summary
- [12b] Baymard, DTC users' informational needs(재료·성분·제조) — https://baymard.com/blog/dtc-users-informational-needs
- [12c] Baymard 2021, Product descriptions(1~3분 탐색 후 포기) — https://baymard.com/blog/product-descriptions
- [13] PowerReviews 2022 (n=11,165): 리뷰 필터 유용 77% — https://www.powerreviews.com/information-shoppers-want-product-reviews/
- [14] PowerReviews Health & Beauty 2023 (n=26,340): 99.5% 리뷰, 77% 피부타입, 73% 톤, 97% 사진 — https://www.powerreviews.com/research/health-beauty-shopping-trends-2023/dependence-on-ugc/
- [15] Baymard, Cart abandonment 70.22% (2025-09) — https://baymard.com/lists/cart-abandonment-rate
- [16] NN/g 2018, Wishlist or cart — https://www.nngroup.com/articles/wishlist-or-cart/
- [17] Baymard 2022, Quick views — https://baymard.com/blog/mobile-desktop-quick-views
- [18] Sephora Ratings & Reviews(리뷰어 피부톤·타입 공개) — https://www.sephora.com/beauty/ratings-reviews (스니펫 확인)
- [63] eMarketer/Salsify 2019: 상품당 약 6장 이미지 기대 — https://www.emarketer.com/content/online-shoppers-expectations-for-visual-merchandising-rises-dramatically
- [64] Bazaarvoice 2024: 47% 사진+텍스트 리뷰 — https://www.bazaarvoice.com/blog/reviews-that-influence-purchases/
- [74] Salsify(벤더): 61% 이미지·영상 최대 결정 요인 — https://www.salsify.com/blog/images-and-videos-most-important-product-page-elements

**뷰티 소비자 조사**
- [19] 화해글로벌 2026-03-09: 누적 리뷰 1,000만, 작성 387만 명 — https://v.daum.net/v/2oYZy8jJg9
- [19b] 화해 뉴스룸 설문: 최우선 = 피부 타입·고민 — https://blog.hwahae.co.kr/all/newsroom/news/2769
- [20] Provoke Insights/Statista 2022 (n=657): 특정 성분 찾는 구매자 밀레니얼 61%, Gen Z 46% — https://www.statista.com/statistics/1334331/skincare-consumers-looking-for-specific-ingredients-us/ ; 오픈서베이 2020 (n=1,500): 성분 중요 70%, 구매 시 확인 43% — https://www.cosmorning.com/mobile/article.html?no=35737
- [21] CJ올리브영 뉴스룸: 9월 올영세일 PDRN +695%, 펩타이드 +72%, 나이아신아마이드·징크 +65% — https://corp.oliveyoung.com/ko/news/88
- [21b] CJ 뉴스룸 2025.09: 환절기 고보습 수요 — https://cjnews.cj.net/ (2차)
- [22] YouGov 2024 (n=1,148): 미국 피부 고민 — https://yougov.com/en-us/articles/49300-americans-top-skin-concerns-and-how-much-theyd-spend-to-treat-them
- [23] GCI Magazine(Circana 관련 설문 인용): 피부타입 적합 93% 등 — https://www.gcimagazine.com/ingredients/skin-care/news/22932586/ (2차 인용, 원문 403)
- [24] Provenance "Skin Deep Beauty" 2022 (n=1,500+): 79% 클레임 신뢰 어려움 — https://britishbeautycouncil.com/news/79-of-consumers-have-difficulty-trusting-beauty-brands-according-to-new-provenance-report/
- [24b] CleanHub Clean Beauty Survey 2023 (n=523) — https://www.cleanhub.com/clean-beauty-survey
- [24c] Circana 2025-05, What it means to be clean — https://www.circana.com/post/what-it-means-to-be-clean
- [25] Mintel 2023-09-28: 74% 저가 효과 동일, 18~34세 1/3 듑 — https://www.mintel.com/press-centre/74-of-beauty-consumers-agree-that-makeup-products-from-affordable-brands-work-just-as-well-as-products-from-premium-brands/
- [26] Mintel GNPD: 한국 민감 피부용 클레임 26%→35% — https://www.mintel.com/press-centre/more-apac-beauty-trends-are-sensitive-skin-focused/
- [26b] Mintel(GCI 재인용): 22% 무첨가 추구 — https://www.gcimagazine.com/brands-products/skin-care/news/21858431/
- [75] CJ올리브영 2026 트렌드(코스모닝 2025-12-19): 진정·장벽 검색 +150%, 소용량 프리미엄 — https://www.cosmorning.com/mobile/article.html?no=51865
- [76] McKinsey Next in Personalization 2021: 71%/76% — https://www.mckinsey.com/capabilities/growth-marketing-and-sales/our-insights/the-value-of-getting-personalization-right-or-wrong-is-multiplying
- [108] J. Retailing and Consumer Services 2025, 스킨케어 리뷰 토픽(텍스처 1위) — https://www.sciencedirect.com/science/article/pii/S0969698925004692
- [109] Street Teams Co, Sephora 샘플링 31% (벤더 자사 사례) — https://streetteamsco.com/case-studies/beauty-sephora-launch
- [110] Rivo 등 벤더 블로그, 뷰티 재구매율 30~45% (방법론 불명) — https://www.rivo.io/blog/repeat-purchase-rate-complete-guide

**계절·재구매**
- [35] Yang, Man et al. 2020, Skin Res Technol (72명 4계절) — https://pubmed.ncbi.nlm.nih.gov/32196767/
- [36] Uchegbulam et al. 2022 (여름 전환 TEWL -22.15%) — https://pubmed.ncbi.nlm.nih.gov/35051810/
- [37] Circana 2026-06-22: 선케어 47% 여름, 연 3회 — https://www.circana.com/post/skin-health-and-wellness-trends-drive-global-growth-in-year-round-spf-use-says-circana
- [39] CJ올리브영 뉴스룸 2026-04-24: 선케어 매출 +281% — https://corp.oliveyoung.com/ko/news/129
- [39b] 한국경제 2026-06-10(올리브영 데이터): 선스틱 +115%, 선스프레이 +196% — https://www.hankyung.com/article/202606094875i
- [40] Swiss Toniq FAQ: 30ml 4~5주 — https://faq.swisstoniq.com/product-info/how-long-do-the-face-serums-last
- [41] Augustinus Bader FAQ: 30ml 약 6주 — https://support.augustinusbader.com/en/articles/9638958-how-long-will-the-serum-last
- [42] Vintner's Daughter FAQ: 30ml 8~10주 — https://vintnersdaughter.com/pages/faq
- [43] EU Regulation 1223/2009 Art.19(1)(c) PAO — https://www.legislation.gov.uk/eur/2009/1223/article/19
- [65] Spate, PDRN YoY +609.8% — https://www.spate.nyc/blog/pdrn-in-skincare-what-the-consumer-data-tells-beauty-brands-about-the-next-big-active
- [65b] Spate × NYSCC 2026 Ingredient Trends — https://www.spate.nyc/reports/2026-ingredient-trends-report

**B2B 대시보드·벤치마크·VoC**
- [45] Amazon Seller Blog, Brand Analytics(리포트 구성, Demographics 100명 기준) — https://sell.amazon.com/blog/brand-analytics
- [46] Walmart Data Ventures, Scintilla Shopper Behavior — https://www.walmartdataventures.com/shopper-behavior
- [47] Shopify Help, Benchmarks(중앙값·25·75, 유사 스토어) — https://help.shopify.com/en/manual/reports-and-analytics/shopify-reports/report-types/custom-reports/benchmarks ; Changelog 2023-04-27 — https://changelog.shopify.com/posts/use-benchmarks-to-compare-performance-against-shops-like-yours
- [49] Few, "Dashboard Confusion", Intelligent Enterprise 2004 — https://www.perceptualedge.com/articles/ie/dashboard_confusion.pdf
- [50] NN/g 2017, Dashboards: Making Charts and Graphs Easier to Understand (지표 개수 권고 없음) — https://www.nngroup.com/articles/dashboards-preattentive/
- [51] "8~12 metrics"는 ClearPoint 등 벤더 블로그만 — https://www.clearpointstrategy.com/blog/kpi-dashboard-best-practices
- [52] Smashing Magazine 2023-12, Five-second testing(anecdotal) — https://www.smashingmagazine.com/2023/12/five-second-testing-case-study/
- [53] Morwitz, Steckel, Gupta 2007, Int J Forecasting 23(3) — https://www.sciencedirect.com/science/article/pii/S0169207007000799
- [54] 하오선·신혜원 2024, 한국화장품미용학회지 14(3): 아마존 화장품 리뷰 LDA 6주제 — https://www.kci.go.kr/kciportal/ci/sereArticleSearch/ciSereArtiView.kci?sereArticleSearchBean.artiId=ART003159756
- [54b] Salsabila & Sibaroni 2021, Jurnal RESTI: 가격·패키징·향 ABSA — https://doi.org/10.29207/resti.v5i3.3078
- [54c] Yutika et al. 2021: Female Daily ABSA — https://ejurnal.stmik-budidarma.ac.id/index.php/mib/article/view/2845 ; 정희원·정영섭 2024 한국어 화장품 리뷰 ABSA — https://www.dbpia.co.kr/journal/articleDetail?nodeId=NODE11711635
- [55] Revuze × L'Oréal 사례 — https://www.revuze.it/case_studies/loreal/
- [55b] Revuze 화장품 산업 차원 — https://www.revuze.it/industries/cosmetics-fragrances/
- [56] Into the Gloss 2016-01, Milky Jelly Cleanser — https://intothegloss.com/2016/01/milky-jelly-cleanser
- [57] Digiday 2016-01-15, Glossier — https://digiday.com/marketing/glossier-instagram-born-beauty-brand-launches-new-products/
- [58] 디마프: flex 인터뷰 2025-04-10 — https://flex.team/blog/2025/04/10/demaf/ ; 비즈워치 2026-04-24 — https://news.bizwatch.co.kr/article/consumer/2026/04/24/0021
- [66] Yotpo × PSA Skincare / Green People — https://www.yotpo.com/case-studies/psa-skincare-case-study/ ; https://www.yotpo.com/case-studies/green-people-case-study/
- [67] Fairing, 평균 응답률 50% — https://fairing.co/blog/the-most-powerful-question-in-ecommerce-how-did-you-hear-about-us-(hdyhau)
- [68] KnoCommerce, 응답률 벤치마크 — https://knocommerce.com/blog/survey-response-rate/
- [69] Medallia × Benefit — https://www.medallia.com/customers/benefit-cosmetics/
- [70] CJ올리브영 2025-10-14, 트렌드 리포트 정례화 — https://corp.oliveyoung.com/ko/news/93

**추천 시스템**
- [59] McKinsey 2013, How retailers can keep up with consumers(35% 추정) — https://www.mckinsey.com/industries/retail/our-insights/how-retailers-can-keep-up-with-consumers
- [59b] Gomez-Uribe & Hunt 2015, ACM TMIS — https://dl.acm.org/doi/10.1145/2843948
- [59c] Zielnicki, Aridor et al. (Netflix) arXiv 2511.07280 — https://arxiv.org/pdf/2511.07280
- [60] Amazon Ads, New-to-Brand — https://advertising.amazon.com/resources/whats-new/long-term-sales
- [61] Lee & Hosanagar, ISR 2021 — https://pubsonline.informs.org/doi/10.1287/isre.2021.1074
- [62] Salsify 2025 Consumer Research (n=1,910) — https://www.salsify.com/hubfs/2025/Salsify%202025%20Consumer%20Research%20Report.pdf
- [71] Schein et al. SIGIR 2002 — https://dl.acm.org/doi/10.1145/564376.564421
- [72] USPTO 8914496, Tracking user behavior relative to a network page — https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/8914496
- [73] VentureBeat 2012, 33Across buys Tynt — https://venturebeat.com/2012/01/25/33across-buys-tynt/
- [111] Hu, Koren, Volinsky ICDM 2008 — http://yifanhu.net/PUB/cf.pdf
- [112] Joachims et al. SIGIR 2005 — https://www.cs.cornell.edu/people/tj/publications/joachims_etal_05a.pdf
- [113] Yi et al. RecSys 2014 — https://www.hongliangjie.com/publications/recsys2014.pdf
- [114] YouTube Official Blog 2012-10-12 — https://blog.youtube/news-and-events/youtube-search-now-optimized-for-time/
- [115] Ziegler et al. WWW 2005 — https://dl.acm.org/doi/10.1145/1060745.1060754
- [116] Steck RecSys 2018 — https://dl.acm.org/doi/10.1145/3240323.3240372
- [117] Herlocker, Konstan, Riedl CSCW 2000 — https://grouplens.org/site-content/uploads/explain-CSCW-20001.pdf
- [118] Google × Behavioural Architects 2020, Decoding Decisions (n=31,000) — https://www.thinkwithgoogle.com/_qs/documents/9998/Decoding_Decisions_The_Messy_Middle_of_Purchase_Behavior.pdf

**성분 과학·규제**
- [27] 나이아신아마이드+비타민C 병용: Bissett 2005 리뷰 — https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1524-4725.2005.31732 ; 병용 연구 2022 — https://pmc.ncbi.nlm.nih.gov/articles/PMC9370691/
- [28] AAD, Pregnancy skin care(레티노이드 금지, 살리실산 2% 초과 회피, 물리 차단) — https://www.aad.org/public/everyday-care/skin-care-secrets/routine/pregnancy-skin-care
- [29] FDA, Alpha Hydroxy Acids(UV 민감 18% 증가) — https://www.fda.gov/cosmetics/cosmetic-ingredients/alpha-hydroxy-acids
- [30] 「기능성화장품 심사에 관한 규정」 별표4(식약처 고시 2023-61호) — https://www.law.go.kr/LSW//admRulInfoP.do?admRulSeq=2100000229666&chrClsCd=010201 ; 함량표 KCIA 전재 PDF — https://kcia.or.kr/inc/down.php?dir=BOARD&file_name=202011_160628808829718_1.pdf ; 2025-89호 개정 — https://www.mfds.go.kr/brd/m_207/view.do?seq=15120
- [31] Skin Therapy Letter, Cosmetics ACD(향료 30~45%) — https://www.skintherapyletter.com/allergic-contact-dermatitis/cosmetics/
- [31b] DermNet, Fragrance mix allergy(ACDS 2007) — https://dermnetnz.org/topics/fragrance-mix-allergy
- [32] DeKoven et al., NACDG 2019-2020, Dermatitis 2023
- [33] JAAD Reviews 2025, 코메도제닉 등급 한계 — https://www.jaadreviews.org/article/S2950-1989(25)00088-1/fulltext
- [34] Kligman 1996, J Soc Cosmet Chem 47:41-48 — https://library.scconline.org/v073n03/75
- [77] Harvard Health, Hyaluronic acid — https://www.health.harvard.edu/medications-and-treatments/hyaluronic-acid-for-skin-benefits-how-to-use-it-and-side-effects
- [78] Jegasothy 2014 — https://pubmed.ncbi.nlm.nih.gov/24688623/
- [79] Man, Feingold, Elias 1996, J Invest Dermatol (PMID 8618046); Zettersten 1997 JAAD — https://pubmed.ncbi.nlm.nih.gov/9308554/
- [80] Cleveland Clinic, Ceramides — https://health.clevelandclinic.org/ceramides
- [81] Proksch 2017 — https://pubmed.ncbi.nlm.nih.gov/28503966/
- [82] Pazyar 2013 호호바 — https://pubmed.ncbi.nlm.nih.gov/24442052/
- [83] Cosmetics & Toiletries, Shea butter — https://www.cosmeticsandtoiletries.com/research/literature-data/article/21835355/shea-butter-extract-for-bioactive-skin-care
- [84] 센텔라 상처치유 SR 2022 — https://pubmed.ncbi.nlm.nih.gov/35328954/
- [85] 센텔라 접촉피부염 2024 — https://pubmed.ncbi.nlm.nih.gov/38567908/
- [86] FDA Skin Protectant Monograph 21 CFR 347 — https://www.federalregister.gov/documents/2003/06/04/03-13751/skin-protectant-drug-products-for-over-the-counter-human-use-final-monograph
- [87] 알로에 화상 메타분석 2022 — https://pubmed.ncbi.nlm.nih.gov/36264753/
- [88] Kim 2021 녹차 메타분석 — https://pubmed.ncbi.nlm.nih.gov/32812270/
- [89] JDD 2020 동아시아 식물추출물 리뷰 — https://jddonline.com/articles/the-use-of-botanical-extracts-in-east-asia-for-treatment-of-hyperpigmentation-an-evidenced-based-rev-S1545961620P0758X/
- [90] Smith 1996 락틱산 — https://pubmed.ncbi.nlm.nih.gov/8784274/
- [91] Rawlings 1996 — https://pubmed.ncbi.nlm.nih.gov/8818186/
- [92] Gopaul 2010 윌로우바크 — https://pubmed.ncbi.nlm.nih.gov/20883292/
- [93] Gupta 2014 아연 — https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4120804/
- [94] Hakozaki 2002 BJD — https://pubmed.ncbi.nlm.nih.gov/12100180/
- [95] Draelos 2006 — https://pubmed.ncbi.nlm.nih.gov/16766489/
- [96] Pullar 2017 Nutrients — https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5579659/
- [97] AAD, Retinoid/retinol — https://www.aad.org/public/everyday-care/skin-care-secrets/anti-aging/retinoid-retinol
- [98] Martin 1998 BJD, tretinoin+BPO — https://onlinelibrary.wiley.com/doi/10.1046/j.1365-2133.1998.1390s2008.x
- [99] Abella 2006 아데노신 — https://pubmed.ncbi.nlm.nih.gov/18489289/
- [100] Robinson 2005 펩타이드 — https://pubmed.ncbi.nlm.nih.gov/18492182/
- [101] 국소 프로바이오틱 리뷰 2020 — https://pubmed.ncbi.nlm.nih.gov/33340341/
- [102] 로즈힙 리뷰 2024 — https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11043540/
- [103] CIR 2022 Rosa damascena — https://www.cir-safety.org/sites/default/files/FR_RosaDamascena_032022.pdf
- [104] Piquero-Casals 2021 우레아 리뷰
- [105] AAD, How to select sunscreen — https://www.aad.org/public/everyday-care/sun-protection/shade-clothing-sunscreen/how-to-select-sunscreen
- [106] Rawlings 2012 미네랄오일 — https://onlinelibrary.wiley.com/doi/full/10.1111/j.1468-2494.2012.00752.x
- [107] Lachenmeier 2008 에탄올 — https://pmc.ncbi.nlm.nih.gov/articles/PMC2596158/

**한국 규제·시장**
- [119] 화장품법 제13조 — https://www.easylaw.go.kr/CSP/CnpClsMain.laf?popMenu=ov&csmSeq=1301&ccfNo=4&cciNo=2&cnpClsNo=1
- [120] 화장품법 제14조, 「화장품 표시·광고 실증에 관한 규정」 — https://www.easylaw.go.kr/CSP/CnpClsMainBtr.laf?popMenu=ov&csmSeq=1301&ccfNo=4&cciNo=2&cnpClsNo=2
- [121] 식약처 「화장품 표시·광고 관리 지침(민원인 안내서)」 2025-08-14 — https://kcia.or.kr/inc/down.php?dir=BOARD&file_name=202508_175547601592435_2.pdf
- [122] 코스인코리아 2025-01, 지침 개정(엑소좀·피부과 전용 등) — https://www.cosinkorea.com/news/article.html?no=54081
- 오픈서베이 뷰티 트렌드 2025 (n=1,000): 구매 기준 성분→후기·가격·효과 — https://blog.opensurvey.co.kr/trendreport/beauty-2025/
- CJ올리브영: 100억 클럽 100개, 상위 10 전부 국내 중소·중견 — https://corp.oliveyoung.com/ko/news/37 ; 올영세일 브랜드 80% 중소 — https://corp.oliveyoung.com/ko/news/16
- 식약처 2025-05-27: 2024 화장품 수출 $102억, 세계 3위 — https://eiec.kdi.re.kr/policy/materialView.do?num=267032 ; 2025 $114억 세계 2위 — https://www.cosmorning.com/news/article.html?no=52844 ; 중소기업 비중 68% — https://www.cncnews.co.kr/news/article.html?no=9736

## 조사 한계

- Contentsquare Help Center 전체가 403이라 존 지표 정의는 검색 원문 스니펫으로 확인했다. 문구는 일치하나 인용 시 "Help Center 기준"으로 표기한다.
- 뷰티 카테고리 전용 전환율·PDP 체류 벤치마크는 공개 자료로 뒷받침할 수 없다.
- 식약처 고시 별표4 함량은 KCIA 2020 전재 자료로 확인했고 2023-61호 원문(hwp)은 렌더링하지 못했다. 이후 별표4 수치 변경 공고는 확인되지 않았다.
- 텍스트 복사와 전환의 상관, 좌절 신호와 전환의 상관계수, "왜 추천" 라벨의 커머스 A/B, 겨울 보습·환절기 매출 정량, 크림·클렌저 재구매 주기, 피부타입 특징의 추천 정확도 향상 %는 모두 **확인 불가**다. 해당 항목은 `[추정]`이거나 실측 대기로 남겼다.
- 벤더 사례(Bazaarvoice·Yotpo·Revuze·Medallia·Perfect Corp·Spate)는 자사 발표라 방향만 참고한다.
