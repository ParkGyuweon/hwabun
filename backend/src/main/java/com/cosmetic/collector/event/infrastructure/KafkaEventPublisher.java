package com.cosmetic.collector.event.infrastructure;

import com.cosmetic.collector.event.api.ActivityEvent;
import com.cosmetic.collector.event.api.EventBatchRequest;
import com.cosmetic.collector.event.application.EventPublishException;
import com.cosmetic.collector.event.application.EventPublishOverloadedException;
import com.cosmetic.collector.event.application.EventPublisher;
import com.cosmetic.collector.event.application.PublishSummary;
import com.cosmetic.collector.event.observability.CollectorMetrics;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;
import tools.jackson.databind.ObjectMapper;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.Executor;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.Semaphore;
import java.util.stream.IntStream;

@Component
@Slf4j
public class KafkaEventPublisher implements EventPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;
    private final ObjectMapper objectMapper;
    private final CollectorMetrics metrics;
    private final Clock clock;
    private final String topic;
    private final Executor kafkaPublisherExecutor;
    private final Semaphore inFlightBatches;

    @Autowired
    public KafkaEventPublisher(
            KafkaTemplate<String, String> kafkaTemplate,
            ObjectMapper objectMapper,
            CollectorMetrics metrics,
            @Qualifier("kafkaPublisherExecutor") Executor kafkaPublisherExecutor,
            @Value("${collector.kafka.topic}") String topic,
            @Value("${collector.kafka.publisher-executor.max-in-flight-batches}") int maxInFlightBatches
    ) {
        this(
                kafkaTemplate,
                objectMapper,
                metrics,
                Clock.systemUTC(),
                topic,
                kafkaPublisherExecutor,
                new Semaphore(maxInFlightBatches, true)
        );
    }

    KafkaEventPublisher(
            KafkaTemplate<String, String> kafkaTemplate,
            ObjectMapper objectMapper,
            CollectorMetrics metrics,
            Clock clock,
            String topic,
            Executor kafkaPublisherExecutor
    ) {
        this(
                kafkaTemplate,
                objectMapper,
                metrics,
                clock,
                topic,
                kafkaPublisherExecutor,
                new Semaphore(Integer.MAX_VALUE)
        );
    }

    KafkaEventPublisher(
            KafkaTemplate<String, String> kafkaTemplate,
            ObjectMapper objectMapper,
            CollectorMetrics metrics,
            Clock clock,
            String topic,
            Executor kafkaPublisherExecutor,
            Semaphore inFlightBatches
    ) {
        this.kafkaTemplate = kafkaTemplate;
        this.objectMapper = objectMapper;
        this.metrics = metrics;
        this.clock = clock;
        this.topic = topic;
        this.kafkaPublisherExecutor = kafkaPublisherExecutor;
        this.inFlightBatches = inFlightBatches;
    }

    @Override
    public CompletableFuture<PublishSummary> publish(String requestId, EventBatchRequest request) {
        if (!inFlightBatches.tryAcquire()) {
            metrics.recordPublishRejected(request.events().size());
            log.warn(
                    "Kafka 이벤트 배치 발행 작업이 포화되었습니다. topic={}, requestId={}, batchSize={}",
                    topic,
                    requestId,
                    request.events().size()
            );
            return CompletableFuture.failedFuture(new EventPublishOverloadedException(
                    "Kafka 발행 중인 이벤트 배치 수가 한도를 초과했습니다.",
                    null
            ));
        }

        Instant receivedAt = clock.instant();
        long queuedAtNanos = System.nanoTime();
        CompletableFuture<CompletableFuture<?>[]> dispatch;

        try {
            dispatch = CompletableFuture.supplyAsync(
                    () -> {
                        metrics.recordPublishQueueWait(
                                Duration.ofNanos(System.nanoTime() - queuedAtNanos));
                        return initiateSends(requestId, request, receivedAt);
                    },
                    kafkaPublisherExecutor
            );
        } catch (RejectedExecutionException exception) {
            metrics.recordPublishRejected(request.events().size());
            dispatch = CompletableFuture.failedFuture(new EventPublishOverloadedException(
                    "Kafka 발행 작업 대기열이 가득 찼습니다.",
                    exception
            ));
        }

        CompletableFuture<PublishSummary> result = dispatch
                .thenCompose(sends -> CompletableFuture.allOf(sends))
                .thenApply(ignored -> {
                    metrics.recordPublished(request.events().size());
                    return new PublishSummary(request.events().size());
                })
                .exceptionally(cause -> {
                    Throwable failure = unwrap(cause);
                    if (failure instanceof EventPublishOverloadedException) {
                        log.warn(
                                "Kafka 이벤트 배치 발행 작업이 포화되었습니다. topic={}, requestId={}, batchSize={}",
                                topic,
                                requestId,
                                request.events().size()
                        );
                        throw new CompletionException(failure);
                    }
                    metrics.recordPublishFailure(request.events().size());
                    log.error(
                            "Kafka 이벤트 배치 발행에 실패했습니다. topic={}, requestId={}, batchSize={}",
                            topic,
                            requestId,
                            request.events().size(),
                            failure
                    );
                    throw new CompletionException(
                            new EventPublishException("Kafka에 이벤트를 전송하지 못했습니다.", failure)
                    );
                });

        return result.whenComplete((ignored, exception) -> inFlightBatches.release());
    }

    private CompletableFuture<?>[] initiateSends(
            String requestId,
            EventBatchRequest request,
            Instant receivedAt
    ) {
        return IntStream.range(0, request.events().size())
                .mapToObj(eventIndex -> send(
                        request.events().get(eventIndex),
                        receivedAt,
                        requestId,
                        eventIndex
                ))
                .toArray(CompletableFuture[]::new);
    }

    private CompletableFuture<?> send(
            ActivityEvent event,
            Instant receivedAt,
            String requestId,
            int eventIndex
    ) {
        try {
            KafkaEventMessage message = KafkaEventMessage.from(event, receivedAt, requestId, eventIndex);
            String payload = objectMapper.writeValueAsString(message);
            return kafkaTemplate.send(topic, event.sessionId(), payload);
        } catch (Exception exception) {
            return CompletableFuture.failedFuture(exception);
        }
    }

    private Throwable unwrap(Throwable cause) {
        if (cause instanceof CompletionException && cause.getCause() != null) {
            return cause.getCause();
        }
        return cause;
    }
}
