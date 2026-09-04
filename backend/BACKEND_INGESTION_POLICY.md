# Backend Event Ingestion Policy

## 1. 목적과 범위

이 문서는 `POST /api/events` Collector가 어떤 이벤트를 Kafka에 발행하고, 어떤 오류를
클라이언트에 반환하는지 정의한다. 이 정책은 Backend의 실행 기준이며, 이벤트 요구가
바뀌면 구현보다 먼저 이 문서를 수정한다.

Collector는 **정상 이벤트의 Kafka 발행**과 **요청·이벤트 검증**만 책임진다. Spark 적재,
분석용 속성 품질, 별도 DLQ 또는 rejected Kafka topic은 이 정책의 보장 범위가 아니다.

## 2. 처리 단위와 HTTP 응답

| 상황 | 처리 | HTTP | 프론트 재전송 |
| --- | --- | --- | --- |
| JSON 파싱 실패, 빈 배치, 알 수 없는 배치 버전 | 배치 전체 거절, Kafka 미발행 | `400` | 하지 않음 |
| 본문 크기 또는 이벤트 수 상한 초과 | 배치 전체 거절, Kafka 미발행 | `413` | 하지 않음 |
| 이벤트별 영구 계약 위반 | 해당 이벤트만 제외 | `202` | 해당 이벤트는 하지 않음 |
| 정상 이벤트 Kafka ACK 완료 | 정상 topic 발행 | `202` | 하지 않음 |
| Kafka 발행 대기열 포화 | 발행하지 못한 배치 실패 | `429` + `Retry-After` | 이후 재시도 |
| Kafka 발행 실패 | 발행 요청 실패 | `503` | 재시도 |

`202`의 `accepted`는 Kafka ACK를 받은 이벤트 수, `rejected`는 Collector가 영구 오류로
제외한 이벤트 수다. `rejections`는 원래 배열의 `event_index`, 가능한 경우 `event_id`,
그리고 안정적인 오류 `code`를 제공한다. 프론트는 `202`의 rejected 이벤트를 재전송하지
않는다.

Kafka 발행은 at-least-once다. `429` 또는 `503` 이후 전체 배치를 재시도할 수 있으므로,
소비 단계는 `event_id` 기반 중복 제거를 유지해야 한다.

## 3. Collector가 검증하는 계약

### 3.1 배치 전체

- `schema_version`은 지원 버전이어야 한다.
- `events`는 비어 있지 않고 최대 100건이어야 한다.
- HTTP 본문은 설정된 최대 크기를 넘지 않아야 한다.

### 3.2 이벤트별 공통 envelope

- 배치와 이벤트의 `schema_version`은 같아야 한다.
- 필수 top-level 필드, 타입, enum, `sequence_no > 0`을 검사한다.
- `event_name`은 등록된 이벤트여야 하고 정해진 `intent`와 일치해야 한다.
- `0.3.0-draft`는 유효한 slug 형식의 `tenant_id`가 필요하다.
- `properties`는 JSON object여야 한다.

### 3.3 구매 이벤트의 properties

Collector는 데이터 품질·금액 해석에 직접 영향을 주는 아래 세 이벤트만 동기 검증한다.

- `begin_checkout.items`: 비어 있지 않은 배열, 각 원소의 `product_id`, 양수 `quantity`,
  양수 `unit_price`
- `purchase.order_id`, `purchase.items`: 위 item 규칙 적용
- `purchase_reason_select.order_id`, `reasons`: 허용 reason, 1~2개 제한. `skipped=true`면
  빈 배열만 허용하고 `primary_reason`은 reasons 중 하나여야 한다.

그 밖의 이벤트별 `properties` 의미 검증은 Collector의 책임이 아니다. 수집은 차단하지
않되, 분석 단계에서 별도로 품질을 검증한다.

## 4. 거부 이벤트 보관 정책

Collector는 검증 거부 이벤트를 Kafka의 별도 topic에 발행하지 않는다. 별도 저장소가
실패했는데도 `202`를 반환하는 모호한 보장 상태를 만들지 않기 위해서다.

거부 사실은 HTTP 응답의 `rejections`, 구조화 로그, 그리고 아래 메트릭으로 관측한다.
거부 원문 전체는 로그에 남기지 않는다.

원문 단위의 감사 보관이 필요해지면, normal/rejected 두 topic의 원자성을 보장하는 Kafka
transaction과 소비자 정책을 별도 설계한 뒤 이 정책에 추가한다.

## 5. 메트릭 분리

| 메트릭 | 의미 |
| --- | --- |
| `collector.events.received` | 요청으로 받은 이벤트 수 |
| `collector.events.accepted` | Kafka ACK를 받은 정상 이벤트 수 |
| `collector.events.rejected` | Collector 계약으로 제외한 이벤트 수 |
| `collector.events.validation.rejected{code=...}` | 검증 오류 코드별 발생 수 |
| `collector.kafka.publish.failures` | Kafka 발행 실패 이벤트 수 |
| `collector.kafka.publish.overloaded` | Kafka 발행 대기열/동시 처리 한도로 거절한 이벤트 수 |
| `collector.kafka.publish.queue.wait` | Kafka 발행 전용 executor 대기 시간 |

Kafka 장애는 validation 메트릭으로 기록하지 않는다. 반대로 계약 위반은 Kafka publish
failure 메트릭으로 기록하지 않는다.

## 6. 변경 절차

1. 새 이벤트 또는 속성 규칙은 이 문서와 계약 문서에 먼저 추가한다.
2. Collector가 검증할지 분석 단계가 검증할지 책임을 명시한다.
3. valid, event-rejected, request-rejected, Kafka-failure 테스트를 함께 추가한다.
4. 메트릭 이름·태그 변경은 대시보드와 알람을 같이 갱신한다.
