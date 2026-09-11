# docs/ai — AI 파트 문서 색인 (2026-09-11)

| 문서 | 무엇 | 먼저 볼 곳 |
|---|---|---|
| [`recommendation-design.md`](recommendation-design.md) | 추천 설계 정본 — 상품 벡터·사용자 벡터·속성 친화도·CF·LTR·MMR·전용 칸 | §1 요약, §8 LTR |
| [`evaluation-framework.md`](evaluation-framework.md) | 평가 체계와 모든 측정 기록(부록 A~W). **대표 지표 부록 W: holdout_a 42.15 / holdout_b 43.15%** | 맨 위 "현재 상태" |
| [`exposure-role.md`](exposure-role.md) | 노출(진열) 정책이 정확도에 미치는 영향 — 담기는 늘고 정확도는 안 오른다 | §5 실제 화면 |
| [`cbf-technical-review.md`](cbf-technical-review.md) | CBF 기술 검토(어휘집 0.4 시점의 기록) | — |
| [`persona-feature-port.md`](persona-feature-port.md) | 속성 친화도를 레포로 이관한 기록 (완료) | — |
| [`product-feature-sample.md`](product-feature-sample.md) | 상품 벡터 인코딩 샘플 (생성물, 어휘집 0.5) | — |
| [`ingredient-domain-guide.md`](ingredient-domain-guide.md) | 성분 도메인 가이드 | — |

계약(다른 파트와 공유하는 인터페이스)은 `contracts/` — 추천 API `recommendation-io-spec.md`, 상품 등록 `product-registration-spec.md`,
처방 `prescription-api-spec.md`, 피드백 분류 `feedback-classification.md`, 한국어화 `localization/README.md`.

숫자를 인용할 때는 **집합(holdout_a/b · test)과 시점**을 같이 적는다. 43.95(09-07)·43.30(09-10 오전)·23.39(09-03 CBF) 는 이력이다.
