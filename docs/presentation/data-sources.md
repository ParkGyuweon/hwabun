# 데이터는 어디서 왔나 — 발표용 정리

작성: 2026-09-29 · 숫자는 모두 레포에서 확인한 값이고, 모르는 값은 (확인 필요)로 적었다.

---

## 1. 한눈에

| 갈래 | 무엇 | 규모 | 근거 |
|---|---|---|---|
| **공개 데이터** | Sephora 공개 상품 카탈로그·리뷰 | 상품 200개 · 브랜드 55개. 속성 4개가 다 채워진 리뷰 844,865건(전체의 77.2%) | `batch/ingest/data/products_200.json`, `README.md` §3 데이터셋 |
| **시연 브랜드** | SSAFY Beauty — 우리가 직접 등록한 소규모 브랜드 예시 | 상품 8개 (카탈로그 200 + 8 = 208) | `batch/ingest/data/serving/README.md` ~40, `contracts/product-registration-spec.md` ~227 |
| **합성 페르소나** | 리뷰어 속성 분포로 만든 가상 소비자. 생성기가 행동 로그를 채운다 | 9,900명 (+ 평가용 홀드아웃 2,000명 × 2). 합성 로그 약 1,049만 건 | `README.md` 상단 표, §3 |
| **LLM 에이전트(PA)** | Playwright 로 실제 브라우저를 띄워 쇼핑몰을 조작하는 에이전트 | 100명 (`PA00001`~`PA00100`) | `README.md` §2 박규원, `CommerceController.java` ~51-60 |
| **실제 트래픽** | 사람이 배포 서버에서 직접 쓴 기록 | 규모 (확인 필요) | `contracts/raw-event-schema.md` ~76 (`actor_type`) |

세 갈래(실제 소비자·페르소나·에이전트)가 같은 이벤트 스키마를 쓰고, 필요할 때
`actor_type`(`user` / `synthetic`)과 `generator_type`(`python_batch` / `agent_llm`)으로 가른다
(`README.md` §1, `contracts/persona-schema.md` §2.3).

> **정직하게 말할 것:** 행동 로그의 대부분은 시뮬레이션이다. 실제 사용자 비율은 (확인 필요).

## 2. 카탈로그 구성

브랜드 55개, 상품 200개 (`products_200.json` 집계).

- 상품 수가 많은 브랜드: Drunk Elephant 16 · Tatcha 14 · fresh 12 · The Ordinary 10 · Glow Recipe 10 · OLEHENRIKSEN 10
- 대형 브랜드도 섞여 있다: Dior 2 · La Mer 1 · Estée Lauder 4 · Lancôme 4 · SK-II 1 · GUERLAIN 1 등
- 한국 브랜드: belif 8 · LANEIGE 3 · Dr. Jart+ 3 · innisfree 2
- 2차 카테고리: 보습 63 · 트리트먼트 49 · 클렌저 35 · 아이케어 18 · 마스크 14 · 립 10 · 선케어 9 · 셀프 태닝 2

**Dior·La Mer 가 있는 이유.** 우리가 소규모 브랜드 플랫폼이라 해도, 공개된 다중 브랜드
데이터가 Sephora 뿐이어서 그 카탈로그를 빌렸다. 대형 브랜드도 이 몰 안에서는 상품이
1~2개라 "브랜드당 상품 수가 적은 몰" 구조는 오히려 우리 대상과 닮았다 — 브랜드 56개 중
55개가 상품 15개 이하, 최대 16개 (`collective-insight-data-boundary.md` §4-2).
진짜 소규모 브랜드의 모습은 SSAFY Beauty 8개로 보여 준다.

## 3. 왜 Sephora 인가

1. **여러 브랜드가 한 몰에 섞인 구조.** 우리 서비스(통합몰)와 가장 가깝다. 단일 브랜드 자사몰 데이터로는 추천 후보가 모자란다 (`README.md` §3 아래 문단).
2. **실제 리뷰 분포.** 리뷰마다 작성자의 피부 타입·피부 톤·머리색·눈동자색이 붙어 있어, 페르소나를 실제 분포에서 뽑을 수 있다 (`contracts/persona-schema.md` §3).
3. **성분 전성분 표기.** 상품 벡터의 성분 블록을 실제 전성분에서 만들 수 있다 (`contracts/product-feature-spec.md`).

## 4. 한계

| 한계 | 내용 | 근거 |
|---|---|---|
| **미국식 분류** | 사용자 속성이 `skin_type`(복합·건성·중성·지성 4종), `skin_tone`(fair~deep 5종), `hair_color`, `eye_color`. 머리색·눈동자색은 한국 뷰티에서 거의 안 쓰는 축이다 | `contracts/persona-schema.md` §3.1 |
| **민감성 피부 없음** | 원천 `skin_type` 에 민감성이 없다. 기획서는 민감성을 핵심 고객군으로 쓴다 | `service-plan.md` ~165, ~299, ~340 |
| **피부 타입 표기 결측** | 상품 200개 중 132개(66%)에 `suitable_skin_types` 가 비어 리뷰어 분포로 대신 표시 | `frontend/src/lib/skinTypes.ts` ~27 |
| **페르소나 균등 분포** | 페르소나가 4 × 5 균등이라 피부 타입 격자가 실제 시장보다 고르게 나온다 | `collective-insight-data-boundary.md` §4-3 |
| **합성 로그의 빈 신호** | `dead_click` 은 합성 로그에서 항상 0 | 같은 문서 §4-3 |
| **가격** | 원천은 달러. 고정 환율 1 USD = 1,340.86 KRW, 100원 반올림으로 원화(`price_krw`) 환산. 한국 실판매가와 다르다 | `batch/ingest/build_ko_catalog.py` ~12 |

## 5. 한국형 분류로 옮기는 계획 (미구현)

| 지금 (Sephora) | 한국형 | 옮기는 방법 |
|---|---|---|
| `skin_tone` 5종 (fair · light · medium · tan · deep) | **호수** (예: 13 · 21 · 23 …) | 톤 밝기 축은 대응된다. 경계값은 (확인 필요) |
| — | **웜 · 쿨 · 뉴트럴** | 원천에 없음. 가입 설문 항목으로 새로 받는다 |
| `skin_type` 4종 | 4종 + **민감성** | 민감성은 피부 타입과 겹칠 수 있어 "지성 + 민감" 처럼 별도 체크로 둔다. 페르소나 쪽은 리뷰 본문의 자극·트러블 언급으로 추정 가능 (방법 확인 필요) |
| `hair_color` · `eye_color` | 쓰지 않음 | 추천·집계 축에서 뺀다. 원천 호환을 위해 필드는 남긴다 |

순서: ① 회원 가입 설문에 호수·웜쿨·민감성 추가 → ② 페르소나 스키마 필드 추가
(`contracts/persona-schema.md`) → ③ 추천 속성 친화도·대시보드 고객군 축에 반영.
일정 (확인 필요).
