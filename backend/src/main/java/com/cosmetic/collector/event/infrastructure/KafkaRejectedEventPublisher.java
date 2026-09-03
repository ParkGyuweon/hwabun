package com.cosmetic.collector.event.infrastructure;

import com.cosmetic.collector.event.application.RejectedEvent;
import com.cosmetic.collector.event.application.RejectedEventPublisher;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;
import tools.jackson.databind.ObjectMapper;

import java.time.Clock;
import java.time.Instant;
import java.util.List;
import java.util.concurrent.CompletableFuture;

/** 거부 이벤트는 정상 수집 경로와 분리된 topic에 보존한다. */
@Component
@Slf4j
public class KafkaRejectedEventPublisher implements RejectedEventPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;
    private final ObjectMapper objectMapper;
    private final Clock clock;
    private final String topic;

    public KafkaRejectedEventPublisher(
            KafkaTemplate<String, String> kafkaTemplate,
            ObjectMapper objectMapper,
            @Value("${collector.kafka.rejected-topic}") String topic
    ) {
        this(kafkaTemplate, objectMapper, Clock.systemUTC(), topic);
    }

    KafkaRejectedEventPublisher(
            KafkaTemplate<String, String> kafkaTemplate,
            ObjectMapper objectMapper,
            Clock clock,
            String topic
    ) {
        this.kafkaTemplate = kafkaTemplate;
        this.objectMapper = objectMapper;
        this.clock = clock;
        this.topic = topic;
    }

    @Override
    public CompletableFuture<Void> publish(String requestId, List<RejectedEvent> rejectedEvents) {
        Instant receivedAt = clock.instant();
        CompletableFuture<?>[] sends = rejectedEvents.stream()
                .map(rejectedEvent -> send(requestId, receivedAt, rejectedEvent))
                .toArray(CompletableFuture[]::new);
        return CompletableFuture.allOf(sends);
    }

    private CompletableFuture<?> send(String requestId, Instant receivedAt, RejectedEvent rejectedEvent) {
        try {
            KafkaRejectedEventMessage message = new KafkaRejectedEventMessage(
                    requestId,
                    rejectedEvent.eventIndex(),
                    receivedAt,
                    rejectedEvent.event(),
                    rejectedEvent.violations()
            );
            return kafkaTemplate.send(topic, requestId, objectMapper.writeValueAsString(message));
        } catch (Exception exception) {
            log.error("거부 이벤트 직렬화에 실패했습니다. requestId={}, eventIndex={}",
                    requestId, rejectedEvent.eventIndex(), exception);
            return CompletableFuture.failedFuture(exception);
        }
    }
}
