# Log Connector

프론트엔드의 활동 로그를 배치로 받아 검증하고 Kafka로 비동기 발행하는 Spring Boot 애플리케이션입니다.

프론트엔드의 `LogEnvelope` 공통 필드를 검증하고, 구매 계열 이벤트의 `properties`만 동기 검증합니다. 전체 수집 정책은 [BACKEND_INGESTION_POLICY.md](./BACKEND_INGESTION_POLICY.md)에 고정합니다.

## IntelliJ에서 실행

1. IntelliJ에서 이 폴더의 `build.gradle`을 엽니다.
2. Gradle 프로젝트로 불러옵니다.
3. Project SDK와 Gradle JVM을 IntelliJ가 관리하는 JDK 21로 선택합니다.
4. `LogConnectorApplication`의 `main()`을 실행합니다.

별도의 JDK를 추가 설치할 필요는 없습니다. 실제 이벤트 발행에는 로컬 또는 팀 개발 Kafka 주소가 필요하며, 기본 주소는 `localhost:9092`입니다.

터미널에서 실행하려면 다음 명령을 사용할 수도 있습니다.

```powershell
$env:JAVA_HOME='C:\Users\SSAFY\.jdks\ms-21.0.11'
./gradlew.bat bootRun
```

Kafka 주소나 Topic을 변경하려면 환경변수를 사용합니다.

```powershell
$env:KAFKA_BOOTSTRAP_SERVERS='localhost:9092'
$env:ACTIVITY_EVENTS_TOPIC='activity-events'
$env:ACTIVITY_EVENTS_PARTITIONS='3'
$env:KAFKA_TOPIC_REPLICATION_FACTOR='1'
$env:KAFKA_TOPIC_RETENTION_MS='86400000'
$env:KAFKA_PUBLISHER_CORE_POOL_SIZE='4'
$env:KAFKA_PUBLISHER_MAX_POOL_SIZE='16'
$env:KAFKA_PUBLISHER_QUEUE_CAPACITY='0'
./gradlew.bat bootRun
```

Topic은 기본적으로 인프라에서 미리 생성한다고 가정합니다. 로컬 개발 중 애플리케이션이 Topic을 생성하게 하려면 Kafka를 먼저 실행한 뒤 `CREATE_ACTIVITY_EVENTS_TOPIC=true`를 설정합니다.

Kafka가 실행되지 않아도 애플리케이션은 시작되지만, 이벤트 발행 요청은 `503 Service Unavailable`로 실패합니다.

`KafkaTemplate.send()` 호출은 Tomcat 요청 스레드가 아니라 `kafka-publisher-*` 전용 스레드에서 실행합니다. 기본 전용 풀은 core 4개, 최대 16개이며 대기열을 사용하지 않습니다. Kafka 장애로 전용 풀이 모두 막히면 새 발행 요청을 쌓아두지 않고 `503 Service Unavailable`로 빠르게 거절합니다. HTTP 응답은 요청 스레드를 점유하지 않은 상태로 Kafka ACK 또는 실패 결과를 기다립니다.

HTTP batch는 Kafka에서 Event 1건당 메시지 1개로 펼쳐집니다. Kafka key는 필수값인 `session_id`를 사용하며, Collector는 각 메시지에 `received_at`, `source`, `request_id`, `event_index`를 추가합니다. `source`는 `actor_type=user`이면 `web`, `actor_type=synthetic`이면 `simulator`로 기록합니다. Raw Event의 중복은 허용하고 Spark Processed 단계에서 `event_id` 기준으로 제거합니다.

## Swagger

애플리케이션 실행 후 다음 주소에서 API 명세와 테스트 화면을 확인할 수 있습니다.

```text
Swagger UI: http://localhost:8080/swagger-ui.html
OpenAPI JSON: http://localhost:8080/v3/api-docs
```

Swagger UI는 Spring 서버가 직접 제공하므로 별도의 CORS 설정이 필요하지 않습니다.

## 이벤트 전송

```powershell
$body = @{
  schema_version = '0.2.0-draft'
  events = @(
    @{
      schema_version = '0.2.0-draft'
      event_id = 'evt-001'
      event_name = 'product_click'
      intent = 'comparison'
      occurred_at = '2026-08-27T14:30:00Z'
      persona_id = $null
      session_id = 'session-001'
      page_view_id = 'page-view-001'
      sequence_no = 1
      page_type = 'product_list'
      product_id = 'product-001'
      actor_type = 'user'
      environment = 'local'
      properties = @{ position = 1 }
    }
  )
} | ConvertTo-Json -Depth 5

Invoke-RestMethod `
  -Method Post `
  -Uri 'http://localhost:8080/api/events' `
  -ContentType 'application/json' `
  -Body $body
```

정상 이벤트의 Kafka ACK를 모두 확인한 뒤 `202 Accepted`를 반환합니다. 배치 안의 영구 검증 오류는 정상 이벤트를 막지 않으며, `rejections`에 표시된 이벤트는 프론트가 재전송하지 않습니다.

```json
{
  "request_id": "생성된 UUID",
  "accepted": 1,
  "rejected": 1,
  "rejections": [
    {
      "event_index": 1,
      "event_id": "evt-invalid",
      "code": "invalid_property_enum"
    }
  ]
}
```

## 상태 및 Metric

```text
GET http://localhost:8080/actuator/health
GET http://localhost:8080/actuator/metrics/collector.events.received
GET http://localhost:8080/actuator/metrics/collector.events.accepted
GET http://localhost:8080/actuator/metrics/collector.events.rejected
GET http://localhost:8080/actuator/metrics/collector.events.validation.rejected
GET http://localhost:8080/actuator/metrics/collector.kafka.publish.failures
GET http://localhost:8080/actuator/metrics/collector.kafka.publish.overloaded
```

## 테스트

```powershell
$env:JAVA_HOME='C:\Users\SSAFY\.jdks\ms-21.0.11'
./gradlew.bat test
```

단위 테스트에서는 실제 Kafka가 필요하지 않습니다.

현재 테스트는 다음 동작을 검증합니다.

```text
EventControllerTest       HTTP 202/400/503와 잘못된 JSON
EventValidationTest       필수 필드, 빈 배열, 최대 100개 제한
EventJsonContractTest     snake_case JSON 계약
KafkaEventPublisherTest   session_id Kafka Key, 배치 성공, 전송 실패, 전용 스레드 격리와 포화 거절
KafkaEventMessageTest     Kafka 메시지 변환과 서버 메타 필드
CollectorMetricsTest      수신/성공/실패 Counter
KafkaTopicConfigTest      Topic 이름과 Partition 설정
OpenApiConfigTest         Swagger 기본 정보
```

## 아직 확정하지 않은 부분

- 최종 Event Taxonomy
- Persona와 Session 생성 정책
- 운영 Kafka의 Partition/Replication 설정

이벤트별 `properties`의 Collector 검증 확대가 필요하면 먼저 `BACKEND_INGESTION_POLICY.md`를 갱신합니다.
