package com.cosmetic.collector.event.infrastructure;

import com.cosmetic.collector.event.api.ActivityEvent;
import com.cosmetic.collector.event.api.EventBatchRequest;
import com.cosmetic.collector.event.application.EventPublishException;
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
import java.time.Instant;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.Executor;
import java.util.concurrent.RejectedExecutionException;

@Component
@Slf4j
public class KafkaEventPublisher implements EventPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;
    private final ObjectMapper objectMapper;
    private final CollectorMetrics metrics;
    private final Clock clock;
    private final String topic;
    private final Executor kafkaPublisherExecutor;

    @Autowired
    public KafkaEventPublisher(
            KafkaTemplate<String, String> kafkaTemplate,
            ObjectMapper objectMapper,
            CollectorMetrics metrics,
            @Qualifier("kafkaPublisherExecutor") Executor kafkaPublisherExecutor,
            @Value("${collector.kafka.topic}") String topic
    ) {
        this(kafkaTemplate, objectMapper, metrics, Clock.systemUTC(), topic, kafkaPublisherExecutor);
    }

    KafkaEventPublisher(
            KafkaTemplate<String, String> kafkaTemplate,
            ObjectMapper objectMapper,
            CollectorMetrics metrics,
            Clock clock,
            String topic,
            Executor kafkaPublisherExecutor
    ) {
        this.kafkaTemplate = kafkaTemplate;
        this.objectMapper = objectMapper;
        this.metrics = metrics;
        this.clock = clock;
        this.topic = topic;
        this.kafkaPublisherExecutor = kafkaPublisherExecutor;
    }

    @Override
    public CompletableFuture<PublishSummary> publish(EventBatchRequest request) {
        Instant receivedAt = clock.instant();
        CompletableFuture<CompletableFuture<?>[]> dispatch;

        try {
            dispatch = CompletableFuture.supplyAsync(
                    () -> initiateSends(request, receivedAt),
                    kafkaPublisherExecutor
            );
        } catch (RejectedExecutionException exception) {
            dispatch = CompletableFuture.failedFuture(exception);
        }

        return dispatch
                .thenCompose(sends -> CompletableFuture.allOf(sends))
                .thenApply(ignored -> {
                    metrics.recordPublished(request.events().size());
                    return new PublishSummary(request.events().size());
                })
                .exceptionally(cause -> {
                    Throwable failure = unwrap(cause);
                    metrics.recordPublishFailure(request.events().size());
                    log.error(
                            "Kafka 이벤트 배치 발행에 실패했습니다. topic={}, batchSize={}",
                            topic,
                            request.events().size(),
                            failure
                    );
                    throw new CompletionException(
                            new EventPublishException("Kafka에 이벤트를 전송하지 못했습니다.", failure)
                    );
                });
    }

    private CompletableFuture<?>[] initiateSends(EventBatchRequest request, Instant receivedAt) {
        return request.events().stream()
                .map(event -> send(request.schemaVersion(), event, receivedAt))
                .toArray(CompletableFuture[]::new);
    }

    private CompletableFuture<?> send(String schemaVersion, ActivityEvent event, Instant receivedAt) {
        try {
            KafkaEventMessage message = KafkaEventMessage.from(schemaVersion, event, receivedAt);
            String payload = objectMapper.writeValueAsString(message);
            return kafkaTemplate.send(topic, event.personaId(), payload);
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
