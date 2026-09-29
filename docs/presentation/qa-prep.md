# 발표 예상 질문 36 — 답변 준비

작성: 2026-09-29 · 발표자: 박규원 (데이터 파트)
읽는 법: **답**은 30초 안에 말할 분량. **근거**는 추가 질문이 오면 펼칠 파일.
"(확인 필요)"는 레포에서 숫자·구현을 확인하지 못한 곳이다. 발표 전에 채우거나 말하지 않는다.

> **MR 머지 전에는 '반영 상태'가 dev 가 아닌 항목을 '구현 예정'으로 말할 것.**

관련 문서: [`business-model.md`](./business-model.md) · [`data-sources.md`](./data-sources.md) · [`brand-data-consent-roadmap.md`](./brand-data-consent-roadmap.md)

---

## 기획·도메인

**Q1. 진짜 데이터는 얼마나 되나?**
답: 행동 로그 대부분은 시뮬레이션입니다. 페르소나 9,900명 합성 로그 약 1,049만 건과 LLM 에이전트 100명이 있고, 실제 사용자 기록은 소량입니다. 셋은 같은 스키마로 흐르고 `actor_type`(`user`/`synthetic`)으로 언제든 갈라 봅니다. 실사용 비율은 (확인 필요).
근거: `README.md` 상단 표·§1, `contracts/raw-event-schema.md` ~76, `contracts/persona-schema.md` §2.3
반영 상태: 실사용자 필터 MR !493 머지 후 · 데이터 구성 표시 MR !501 머지 후

**Q2. 우리가 만든 페르소나로 우리 모델을 검증하면 순환 논리 아닌가?**
답: 맞는 지적입니다. 그래서 "잘 맞췄다"가 아니라 "일부러 심은 신호를 파이프라인이 되찾는가"로 검증합니다. 생성기가 심은 규칙 20개(타깃 상품 끝까지 스크롤·담기, 이탈 깊이, 신규 브랜드 담기율 0.12 등)를 로그에서 다시 재는 검사를 만들었습니다. 생성기는 "어떻게 둘러보는가"를 심고, "무엇을 사는가"는 실제 리뷰에서 옵니다. 그래서 합성 로그 위의 대시보드 숫자는 인사이트 발견이 아니라 파이프라인이 정확하다는 증거로 말합니다. 실제 성능 주장은 리뷰 이력 기반 오프라인 평가(홀드아웃)로 따로 합니다.
근거: `batch/jobs/check_planted_signals.py`, `docs/analytics/planted-signal-recovery.md`
반영 상태: MR !505 머지 후 · 생성기 원본 3,000명 기준 20개 모두 일치, 파이프라인 거친 값은 EC2-2 에서 실행 필요

**Q3. 소규모 브랜드 플랫폼이라면서 왜 디올·라메르가 있나?**
답: 공개된 다중 브랜드 몰 데이터가 Sephora 뿐이라 그 카탈로그를 빌렸습니다. 이 몰에서는 대형 브랜드도 상품이 1~2개라 "브랜드당 상품이 적은 몰" 구조는 우리 대상과 닮았습니다. 진짜 소규모 브랜드는 시연 브랜드 SSAFY Beauty 8개로 보여 드립니다.
근거: `batch/ingest/data/products_200.json` (브랜드 55 · Dior 2 · La Mer 1), `docs/dashboard/collective-insight-data-boundary.md` §4-2 (56개 중 55개가 상품 15개 이하)
반영 상태: dev 반영

**Q4. 돈은 어떻게 버나?**
답: 현재 범위는 수수료 0%, 배너도 광고가 아닙니다. 수익 지점은 브랜드 대시보드로 봅니다. 제안은 "데이터를 나누면 벤치마크 무료(give-to-get) + 시장 심화 리포트 유료 등급"이고, 팀 결정이 남아 있습니다.
근거: `docs/presentation/business-model.md`, `docs/planning/service-plan.md` ~205·~589-601·~696-705
반영 상태: dev 반영 (기획 문서. BM 은 팀 결정 필요)

**Q5. 경쟁 브랜드 데이터를 서로 보나? 동의는?**
답: 비율의 분위만, 브랜드 5개 이상 모였을 때만 보여주고, 한 브랜드가 표본 절반을 넘으면 가립니다. 절대치·상품별 숫자는 밖으로 안 나갑니다. 브랜드 동의 기능은 아직 없고, 실제 입점 전에 붙일 첫 과제입니다.
근거: `docs/presentation/brand-data-consent-roadmap.md`, `collective-insight-data-boundary.md` §3 (R1~R3, R7·R8)
반영 상태: dev 반영 (R1~R3). 동의 R7·R8 은 미구현

**Q6. 눈동자 색·머리색은 왜 있고, 민감성 피부는 왜 없나?**
답: 원천(Sephora) 분류가 미국식이라 그렇습니다. 원천 피부 타입은 4종뿐이라 민감성이 없습니다. 한국형으로 호수·웜쿨·민감성을 가입 설문에 추가하고 머리색·눈동자색은 추천 축에서 빼는 계획입니다.
근거: `contracts/persona-schema.md` §3.1, `docs/presentation/data-sources.md` §5
반영 상태: dev 반영 (원천 분류). 한국형 분류는 계획 단계

**Q7. AI 문장이 화장품법 금지 표현을 쓰면?**
답: 화장품법 제13조와 식약처 지침 별표1 금지 표현을 사전으로 두고, AI 처방 문장에 그 낱말이 나오면 거부합니다. 브랜드가 쓰는 상품 문구·등록 화면에도 같은 사전으로 경고를 붙이는 작업을 추가하고 있습니다.
근거: `contracts/cosmetic-claim-banned-terms.json`, `contracts/prescription-api-spec.md` §4, `docs/dashboard/action-prescription-prompt.md` ~241
반영 상태: MR !496 머지 후 (상품 문구·등록 경고). AI 처방 금지어는 dev 반영

**Q8. 전성분은 함량 순서인데 순서를 반영하나?**
답: 네. 앞에 적힌 성분일수록 가중치가 큽니다(`max(1 − 위치/전체 수, 0.1)`). 다만 고시 기능성 원료는 소량으로도 효과가 있어 뒤에 있어도 위치와 무관하게 인정하는 규칙을 보완하고 있습니다.
근거: `docs/ai/ingredient-domain-guide.md` ~206, `contracts/product-feature-vocab.json` `position_formula`
반영 상태: MR !503 머지 후(추천은 스위치 꺼짐, 성분 화면만 적용). 위치 가중치 자체는 dev 반영

## 데이터·통계

**Q9. "이 글을 읽으면 담기가 N배"는 인과인가?**
답: 아닙니다. 관찰된 연관입니다. 원래 사려던 사람이 더 읽었을 수 있습니다. 인과를 보려면 진열 축(`storefront_*`)으로 A/B 를 나눠 비교해야 하고, 그 축은 로그에 이미 있습니다.
근거: `frontend/src/dashboard/screens/ContentScreen.tsx` ~64-79, `collective-insight-data-boundary.md` §2-3 (진열 효과)
반영 상태: MR !501 머지 후

**Q10. 50건·200건 기준은 왜 그 값이고, 최댓값을 고르면 작은 표본이 이기지 않나?**
답: 50건 미만은 그림에서 빼고, 비율 분모 200 미만은 흐립니다(200은 우리가 정한 값). 비율 최댓값을 고르면 표본 작은 쪽이 튀는 편향이 있어, 순위는 Wilson 하한(신뢰구간 아래쪽)으로 매기도록 바꿉니다.
근거: `ContentScreen.tsx` ~54·~271 (`THIN_VIEWS=500`, 50건 제외), `collective-insight-data-boundary.md` §3 R2 `[추정]`
반영 상태: MR !501 머지 후

**Q11. 일별 고유 방문자를 더하면 기간 고유 방문자가 되나?**
답: 안 됩니다. 같은 사람이 여러 날 오면 중복됩니다. 그래서 화면 문구를 "방문 수"로 고쳤고, 기간 고유 수가 필요하면 HyperLogLog 같은 근사 합산 구조로 바꾸는 개선안이 있습니다.
근거: 최근 커밋 `9b1355a` (넘어온 고객 화면을 방문 수로 읽히게). HLL 은 개선안(미구현)
반영 상태: MR !493 머지 후

**Q12. 적재 잡(Q1)이 죽으면 로그를 잃나?**
답: Kafka 에 원본이 남아 있는 동안은 체크포인트부터 다시 읽어 잃지 않습니다. 보관 기간을 72시간으로 늘려 주말 장애도 버티게 했고, 컨테이너 자동 재시작과 알림을 둡니다.
근거: `streaming/README.md` ~136-141 (dev 문서는 아직 24시간 — 72시간은 브랜치 머지·배포 후 바뀐다), Q1 체크포인트는 `README.md` §2 이은솔
반영 상태: MR !506 머지·EC2-2 배포 후 72시간 (그 전엔 24시간으로 답할 것)

**Q13. 1억 건이 되면 야간 배치가 버티나?**
답: 못 버팁니다. 지금은 매일 전체를 다시 처리하는데, 실측 3회로 맞춘 모델이 `18.4분 + 원천 100만 건당 11.9분`이라 약 1,360만 건(1,357만)이면 06:00 실패선에 닿습니다. 2026-09-21 기준 750만 건·107.7분입니다. 개선안은 새로 들어온 날짜만 처리하는 증분 처리입니다.
근거: `streaming/README.md` ~147-172 (경고 05:30 = 1,105만 건, 실패 06:00 = 1,357만 건)
반영 상태: dev 반영 (문서·실측). 증분 처리는 개선안

**Q14. 작은 파일(small files) 문제는?**
답: 상시 적재가 짧은 간격으로 Parquet 을 쓰면 파일이 잘게 쪼개집니다. 적재 간격을 10초에서 60초로 늘려 하루 파일 수를 약 26,000개에서 약 4,300개로 줄였습니다(3개 파티션 기준 계산값). 전날 파티션을 약 128MB 로 합치는 압축 단계도 만들었지만, 지금 읽기 방식(적재 잡의 파일 목록 로그)과 부딪혀 기본으로 꺼 두고 읽기 방식을 바꾼 뒤 켤 예정입니다.
근거: `docs/analytics/raw-event-storage-design.md`, `docs/analytics/spark-processing-design.md`
반영 상태: MR !506 머지·배포 후

**Q15. 유실·중복이 없다는 걸 어떻게 증명하나?**
답: 중복은 `event_id` 로 정본 하나만 남기고 나머지를 `duplicate_events` 에 감사 기록으로 둡니다. 형식이 틀린 건 `bad_events` 로 따로 남깁니다. Q5 검증 166개가 매 배치 확인하고, Kafka 오프셋이 끊김 없이 이어졌는지 보는 검사를 추가합니다.
근거: `streaming/README.md` ~26·~123-130·~187, `README.md` §2 Q2·Q5
반영 상태: 오프셋 연속성 경고 검사 MR !506 머지 후. 중복 제거·bad_events·Q5 는 dev 반영

**Q16. 세션은 어떻게 정의하나?**
답: 브라우저 탭 하나가 세션입니다. 새로고침해도 이어지고 탭을 닫으면 끝납니다. 여기에 30분 동안 아무 행동이 없으면 새 세션으로 끊습니다.
근거: `frontend/src/lib/logger.ts` ~214-264 (sessionStorage). 30분 비활성 규칙은 MR !499
반영 상태: MR !499 머지 후

**Q17. 추천 Recall@10 43.8%, 인기순보다 나은가?**
답: 대표 지표는 홀드아웃 a 43.80%, 확인용 b 42.45% 입니다. 같은 사람·같은 정답·같은 후보 규칙으로 잰 기준선과 비교하면:
- 인기순(정답 시점 이전 리뷰 수): 10.80% / 10.05% → 모델이 약 4배 (+33.0%p, 95% CI +30.8~+35.3)
- 본 브랜드 먼저 + 인기순(손으로 짠 강한 규칙): 24.85% / 25.20% → 약 1.7배 (+19.0%p, CI +17.0~+21.1)
- 무작위: 5.09%
이 평가 틀에서 모델 43.80% 가 그대로 다시 나오는 것까지 확인했습니다.
근거: `batch/jobs/eval_baselines.py`, `docs/ai/evaluation-framework.md` 부록 X
반영 상태: MR !505 머지 후 (숫자는 레포 데이터로 실제 계산함)

**Q18. 실시간 반영이 정확도를 올리나?**
답: 실시간 반영의 목적은 정확도보다 다양성과 반응성입니다. 방금 누른 좋아요가 목록을 바로 바꾸는 경험이 목적이고, 정확도는 오프라인 평가로 따로 봅니다.
근거: `docs/ai/live-demo-runbook.md` 상단, `README.md` §2 박규원 (실시간 상태)
반영 상태: dev 반영

**Q19. 피드백 분류 F1 94.3 은 믿을 만한가?**
답: 사람이 정답을 단 50건 기준입니다(정밀도 93.7 · 재현율 94.9). 50건이라 ±10%p 는 잡음으로 봅니다. 분류기는 고객이 고른 축 안에서, 고정된 20개 카테고리 중에서만 고릅니다.
근거: `contracts/feedback-classification.md` ~201
반영 상태: dev 반영

## 기능

**Q20. 결제 버튼을 두 번 누르면?**
답: 주문 잠금과 멱등키로 같은 결제가 두 번 확정되지 않습니다. 이미 같은 결제 ID 로 확정된 주문이면 기존 결과를 돌려줍니다.
근거: `shop_backend/.../payment/PaymentConfirmationService.java` ~49·~85, `shop_backend/migrations/20260916_add_verified_payment.sql`
반영 상태: MR !491 머지 후

**Q21. 프론트에서 금액을 바꿔 보내면?** (강점)
답: 서버가 PortOne 에 결제를 직접 다시 조회해 결제 ID·상태·통화·금액이 주문과 모두 맞을 때만 확정합니다. 하나라도 다르면 거부합니다.
근거: `PaymentConfirmationService.java` ~100-109, `commerce/PortOnePaymentVerifier.java`
반영 상태: dev 반영

**Q22. 결제는 됐는데 확인 요청이 실패하면? 환불은?**
답: 다시 시도하면 서버가 PortOne 을 재조회해 확정합니다. 확인이 누락된 주문을 주기적으로 다시 확인하는 작업을 둡니다. 환불은 다음 단계 범위입니다.
근거: `PaymentConfirmationService.java`
반영 상태: 재시도 확정 MR !491 머지 후 · 자동 재확인 MR !500 머지 후 · 환불은 범위 밖

**Q23. 결제 없이 PAID 로 만드는 API 가 있던데?**
답: LLM 에이전트는 카카오페이 창을 넘을 수 없어 둔 전용 경로입니다. 서버가 에이전트 계정(`PA00001`~`PA00100`) 접두만 허용하고, 설정이 비어 있으면 전부 막습니다. 프론트 판정은 보호 장치로 치지 않습니다.
근거: `shop_backend/.../commerce/CommerceController.java` ~50-60
반영 상태: fail-closed(설정이 비면 차단) MR !487 머지 후

**Q24. 재고는?**
답: 재고 관리는 이번 범위 밖입니다. 대신 한 상품 수량을 99개로 제한합니다.
근거: 수량 제한은 MR !491 (`@Max(99)`)
반영 상태: MR !491 머지 후 (`@Max(99)`)

**Q25. 화면의 추천이 진짜 모델 결과인가?**
답: 추천 서버가 1.5초 안에 답하지 않으면 기본 목록을 보여주고 "기본 추천"이라고 표시합니다. 표시가 없으면 모델 결과입니다.
근거: `frontend/src/lib/recommendApi.ts`, MR !488·!492
반영 상태: "기본 추천" 표시 MR !488 머지 후 · 1.5초 대기 MR !492 머지 후

**Q26. 브랜드가 올린 상품은 검수하나?**
답: 데모에서는 자동 승인입니다. 관리자 승인 API(`PATCH /api/admin/products/{id}/approval?status=...`)가 따로 있어 검수 단계를 켤 수 있습니다.
근거: `shop_backend/src/main/java/com/cosmetic/shopbackend/admin/AdminOperationsController.java` ~21 (`@PatchMapping("/products/{id}/approval")`), `contracts/product-registration-spec.md`
반영 상태: dev 반영

## 보안·인프라

**Q27. 가짜 이벤트를 쏘면 대시보드가 오염되나?**
답: 매출·정산은 행동 로그가 아니라 주문 DB(결제 완료)로 계산해 이벤트로는 못 바꿉니다. 이벤트는 수집기가 스키마 검증을 하고, 요청 수 제한과 과부하 시 429/503 으로 막습니다.
근거: `docs/planning/service-plan.md` ~203, `README.md` §2 최열음 (백프레셔), `docs/backend-ingestion-backpressure.md`
반영 상태: dev 반영

**Q28. A 브랜드가 B 브랜드 대시보드를 볼 수 있나?** (강점)
답: 못 봅니다. 모든 판매자 API 가 로그인 계정의 브랜드 소유를 확인하고, 조회는 그 브랜드로 묶여 실행됩니다. 브랜드 간에 오가는 것은 가림 규칙을 거친 집계뿐입니다.
근거: `shop_backend/.../dashboard/DashboardController.java`, `collective-insight-data-boundary.md` §3
반영 상태: dev 반영

**Q29. AI API 를 마구 호출해 과금을 늘리면?**
답: 모델 이름·강제 재생성(force) 같은 값은 밖에서 못 바꾸게 막았고, IP 별 요청 제한을 두었습니다. 처방 문장은 런타임 스위치로 즉시 끌 수 있고, 꺼지면 규칙 문장으로 대체됩니다.
근거: `README.md` §2 박규원 LLM 표 (런타임 스위치), `batch/serving/`, MR !489
반영 상태: MR !489 머지 후

**Q30. 프롬프트 주입이나 개인정보가 LLM 으로 새지 않나?**
답: 분류기는 정해진 목록 안에서만 답하게 해 주입이 결과를 바꿀 여지를 줄였습니다. 보내기 전에 금지어를 가리고, 전화번호·이메일을 가린 뒤 보냅니다.
근거: `contracts/feedback-classification.md` (20종 고정 목록, 금지어), MR !489
반영 상태: MR !489 머지 후

**Q31. Kafka 브로커가 하나인데?**
답: 데모 규모의 한계입니다. 외부에서는 보안 그룹으로 접근을 막았습니다. 확장하면 브로커 3대에 복제 계수 3으로 갑니다.
근거: `README.md` §1 (EC2-2 Kafka KRaft), `deploy/ec2-2/docker-compose.yml`
반영 상태: dev 반영

**Q32. EC2 를 두 대로 나눈 이유와 한 대가 죽으면?**
답: 서비스(EC2-1: 쇼핑몰·수집·추천·DB)와 데이터 처리(EC2-2: Kafka·Spark)를 나눠, 무거운 야간 배치가 쇼핑몰을 느리게 하지 않게 했습니다. EC2-2 가 죽어도 쇼핑몰과 주문은 돌고, 로그 적재와 대시보드 갱신만 멈춥니다. EC2-1 이 죽으면 서비스가 멈춥니다. 수집기는 Kafka 발행 대기열이 차면 `429 + Retry-After: 1` 로, Kafka 발행 자체가 실패하면 `503` 으로 답하고 프론트 로거가 백오프로 재시도합니다.
근거: `README.md` §1 운영 줄, `backend/src/main/java/com/cosmetic/collector/common/GlobalExceptionHandler.java` ~84-96 (`EventPublishException` → 503, `EventPublishOverloadedException` → 429 + `Retry-After`), `backend/.../event/infrastructure/KafkaEventPublisher.java` ~108·~129
반영 상태: dev 반영

**Q33. 백업·알림·롤백은?**
답: DW 발행은 스왑 전 테이블을 `__old` 로 남겨 바로 되돌릴 수 있습니다. Prometheus·Grafana 로 수집·백엔드를 봅니다. DB 정기 백업과 배치 실패 알림은 추가 중입니다.
근거: `README.md` §2 송민우 (원자적 스왑·`__old`), 최열음 (모니터링)
반영 상태: MR !504 머지 후. `__old` 스왑·모니터링은 dev 반영

**Q34. 로그인 무차별 대입, 토큰 탈취는?**
답: 로그인 시도 횟수를 제한하고, 탈퇴한 계정의 토큰은 바로 막습니다. 토큰 탈취를 줄이는 CSP 강화는 개선안입니다.
근거: `shop_backend/.../security/JwtAuthenticationFilter.java`, MR !487·!485
반영 상태: 로그인 제한 MR !487 머지 후 · 탈퇴 토큰 차단 MR !485 머지 후 · CSP 는 개선안

## 개인정보

**Q35. 행동을 동의 없이 수집하나?**
답: 첫 방문에 수집 안내를 띄우고, 가입 때 동의를 받습니다. 기록 연결에 동의하지 않은 사람의 행동은 회원과 잇지 않고 익명으로만 남깁니다.
근거: `docs/analytics/event-logging-design.md`, MR !481·!484
반영 상태: 첫 방문 안내·처리방침 MR !481 머지 후 · 가입 동의 MR !484 머지 후

**Q36. 탈퇴하면 데이터는?**
답: 회원 정보는 즉시 파기합니다. 거래 기록은 법에 따라 5년, 이용 기록은 1년 보관합니다. 작성한 리뷰는 남기되 작성자를 "탈퇴한 회원"으로 바꿉니다.
근거: MR !485 (탈퇴 처리), MR !481 (처리방침)
반영 상태: MR !485 머지 후 + 처리방침 MR !481 머지 후 (이용 기록 1년, 거래 5년)

---

## 발표 직전 체크리스트

- [ ] **마이그레이션 2개 먼저 적용** — `shop_backend/migrations/20260929_add_member_signup_consent.sql`, `shop_backend/migrations/20260929_add_member_withdrawal.sql` (MR !484·!485 에 포함, 머지 후 적용)
- [ ] 리허설이 끝나면 **`run-daily-batch.sh` 를 수동으로 한 번 실행**해 대시보드에 리허설 기록까지 반영
- [ ] EC2-2 `.env` 에 **`COMMONS_HASH_SALT`** 가 있는지 확인 — 비면 Q3 가 시작하자마자 실패 (`README.md` §4)
- [ ] **추천 서버 상태** 확인 (8300 응답, 처방 스위치 on)
- [ ] 정산 화면용 **`POST /api/settlements/generate`** 실행 (ADMIN, `docs/api-spec.md` ~181)
- [ ] 시연용 새 회원은 가입 때 **'전체 동의'** 로 — 기록 연결 미동의면 개인화가 안 보인다
