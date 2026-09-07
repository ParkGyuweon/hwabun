# Backend Ingestion Backpressure 작업 정리

## 작업 목적

활동 이벤트 수집 API(`POST /api/events`)는 요청을 검증한 뒤 Kafka에 비동기로 발행한다. Kafka 응답이 느려지거나 장애가 발생한 상황에서 요청을 무제한으로 수락하면 다음 문제가 생긴다.

- 서버의 요청 처리 스레드, 메모리, Kafka producer 버퍼가 누적된다.
- 정상 요청도 지연되거나 실패한다.
- 클라이언트는 일시적인 과부하와 Kafka 장애를 구분할 수 없다.
- 너무 큰 이벤트 본문이 역직렬화 과정에서 서버 자원을 과도하게 사용한다.

따라서 이 작업은 수집 API의 입력 크기를 제한하고, Kafka 발행 작업의 포화 상태를 클라이언트에 명확히 알리며, 운영 중 포화 여부를 관측할 수 있게 하는 것을 목표로 한다.

## 적용한 방식

### 1. Kafka 발행 전용 실행 큐

`ThreadPoolTaskExecutor`를 `kafkaPublisherExecutor`라는 별도 executor로 두고, Kafka 발행 시작 작업을 이 executor에서 실행한다.

```yaml
collector:
  kafka:
    publisher-executor:
      core-pool-size: 16
      max-pool-size: 16
      queue-capacity: 200
```

기존에는 대기열 용량이 `0`이라 순간적인 부하에도 바로 거절될 수 있었다. 현재는 제한된 200개 대기열을 두어 짧은 버스트는 흡수하고, executor와 대기열이 모두 차면 `AbortPolicy`가 `RejectedExecutionException`을 발생시킨다.

전용 executor를 사용한 이유는 Kafka 발행 지연이 일반 웹 요청 처리나 다른 비동기 작업의 자원을 잠식하지 않게 하기 위해서다.

### 2. 포화 상태를 429로 구분

executor가 작업을 거절하면 `EventPublishOverloadedException`으로 변환하고, 전역 예외 처리기에서 다음 응답을 반환한다.

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 1

{
  "code": "INGESTION_OVERLOADED",
  "message": "이벤트 수집 요청이 많습니다. 잠시 후 재시도해 주세요.",
  "details": []
}
```

Kafka 전송 자체가 실패한 경우에는 기존처럼 `503 KAFKA_UNAVAILABLE`을 반환한다. 이 분리는 재시도 전략을 다르게 적용하기 위해 필요하다.

- `429`: 서버의 수집 처리 용량이 일시적으로 부족한 상태이므로, `Retry-After` 이후 재시도한다.
- `503`: Kafka 또는 발행 경로가 정상 동작하지 않는 상태이므로, 장애 대응 정책에 따라 재시도 또는 보류한다.

### 3. 요청 크기 및 이벤트 개수 제한

두 단계의 입력 제한을 적용했다.

- 이벤트 개수: Bean Validation의 `@Size(max = 100)`으로 한 배치의 이벤트 수를 100개로 제한한다. 초과 시 `413 EVENT_BATCH_TOO_LARGE`를 반환한다.
- 요청 본문 크기: `EventRequestSizeFilter`에서 기본 256 KiB를 초과하면 `413 EVENT_REQUEST_TOO_LARGE`를 반환한다.

`Content-Length`가 있는 요청은 헤더만으로 빠르게 차단한다. `Transfer-Encoding: chunked`처럼 `Content-Length`가 없는 요청은 최대 크기보다 1바이트 더 읽어 크기를 판정한다. 제한 이내의 본문은 래퍼에 캐시해 이후 Spring/Jackson이 동일한 요청 본문을 읽을 수 있도록 했다.

이 방식을 쓴 이유는 `Content-Length`만 검사하면 chunked 요청이 `-1`로 전달되어 제한을 우회할 수 있기 때문이다. 본문 전체를 무제한으로 읽지 않고, 상한을 넘는 첫 바이트에서 중단하므로 메모리 사용량도 제한된다.

### 4. 운영 지표 추가

Micrometer에 다음 지표를 추가했다.

| 지표 | 의미 |
| --- | --- |
| `collector.kafka.publish.overloaded` | executor 또는 in-flight 한도로 거절된 이벤트 수 |
| `collector.kafka.publish.queue.wait` | 발행 시작 작업이 executor 대기열에서 기다린 시간 |

기존의 수신, 발행 성공, 발행 실패 지표와 함께 보면 수집량 증가, 대기열 지연, 실제 거절 발생, Kafka 발행 실패를 구분해 관찰할 수 있다.

## 테스트

다음 동작을 테스트로 검증했다.

- `Content-Length`가 제한보다 큰 요청은 413을 반환한다.
- chunked 요청도 크기 초과 시 413을 반환한다.
- 제한 이내 chunked 요청은 본문을 보존한 채 다음 필터/컨트롤러로 전달한다.
- 이벤트가 100개를 초과하면 413을 반환한다.
- executor 거절은 429 및 `Retry-After: 1`을 반환한다.
- 거절 이벤트 수와 큐 대기 시간 지표가 기록된다.

검증 명령:

```bash
cd backend
./gradlew.bat test
```

## 추가 보완이 필요한 점

executor 대기열은 Kafka `send()` 호출을 시작하는 작업을 제한한다. 추가로 실제 발행 완료까지 엄격하게 백프레셔를 적용하기 위해 bounded semaphore를 도입했다.

1. `publish()` 시작 시 슬롯을 즉시 획득한다.
2. 슬롯이 없으면 바로 `EventPublishOverloadedException`을 반환한다.
3. Kafka 발행 완료 future의 `whenComplete`에서 슬롯을 반납한다.

기본 상한은 `232`개 배치이며 `KAFKA_PUBLISHER_MAX_IN_FLIGHT_BATCHES` 환경 변수로 조정할 수 있다. 이 값은 기본 executor의 최대 실행·대기 가능 작업 수(최대 32개 실행 + 200개 대기)와 맞췄다.

브라우저 호환성을 위해 CORS 처리는 MVC 단계가 아닌 최우선 servlet filter로 적용했다. 따라서 요청 크기 필터가 직접 반환하는 413에도 CORS 헤더가 포함되며, `Retry-After`도 `exposedHeaders`에 추가되어 프론트엔드가 읽을 수 있다.
