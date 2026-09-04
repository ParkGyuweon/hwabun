package com.cosmetic.collector.event.infrastructure;

import com.cosmetic.collector.event.api.ActivityEvent;
import com.cosmetic.collector.event.api.EventBatchRequest;
import com.cosmetic.collector.event.application.EventPublishException;
import com.cosmetic.collector.event.application.EventPublishOverloadedException;
import com.cosmetic.collector.event.application.IndexedActivityEvent;
import com.cosmetic.collector.event.application.PublishSummary;
import com.cosmetic.collector.event.observability.CollectorMetrics;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import tools.jackson.databind.ObjectMapper;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicReference;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class KafkaEventPublisherTest {

    @Test
    void publishesEachEventUsingSessionIdAsTheKafkaKey() {
        @SuppressWarnings("unchecked")
        KafkaTemplate<String, String> kafkaTemplate = mock(KafkaTemplate.class);
        CollectorMetrics metrics = mock(CollectorMetrics.class);
        ObjectMapper objectMapper = new ObjectMapper();
        Clock clock = Clock.fixed(Instant.parse("2026-08-27T15:00:00Z"), ZoneOffset.UTC);

        when(kafkaTemplate.send(eq("activity-events"), eq("session-001"), anyString()))
                .thenReturn(CompletableFuture.completedFuture(null));

        KafkaEventPublisher publisher = new KafkaEventPublisher(
                kafkaTemplate,
                objectMapper,
                metrics,
                clock,
                "activity-events",
                Runnable::run
        );

        EventBatchRequest request = new EventBatchRequest(
                "draft",
                List.of(new ActivityEvent(
                        "0.2.0-draft",
                        "evt-001",
                        "product_click",
                        "comparison",
                        Instant.parse("2026-08-27T14:30:00Z"),
                        "persona-001",
                        "session-001",
                        "page-view-001",
                        1,
                        "product_list",
                        "product-001",
                        "user",
                        "local",
                        objectMapper.createObjectNode().put("position", 1)
                ))
        );

        PublishSummary result = publisher.publish("request-001", request).join();

        assertThat(result.publishedCount()).isEqualTo(1);
        verify(kafkaTemplate).send(eq("activity-events"), eq("session-001"), anyString());
        verify(metrics).recordAccepted(1);
        verify(metrics, never()).recordKafkaPublishFailure(any(Integer.class));
    }

    @Test
    void publishesDifferentSessionsUsingDifferentKafkaKeys() {
        @SuppressWarnings("unchecked")
        KafkaTemplate<String, String> kafkaTemplate = mock(KafkaTemplate.class);
        CollectorMetrics metrics = mock(CollectorMetrics.class);
        ObjectMapper objectMapper = new ObjectMapper();
        Clock clock = Clock.fixed(Instant.parse("2026-08-27T15:00:00Z"), ZoneOffset.UTC);

        when(kafkaTemplate.send(anyString(), anyString(), anyString()))
                .thenReturn(CompletableFuture.completedFuture(null));

        KafkaEventPublisher publisher = new KafkaEventPublisher(
                kafkaTemplate,
                objectMapper,
                metrics,
                clock,
                "activity-events",
                Runnable::run
        );

        EventBatchRequest request = new EventBatchRequest("draft", List.of(
                event("evt-001", "persona-001", "session-001"),
                event("evt-002", "persona-002", "session-002")
        ));

        PublishSummary result = publisher.publish("request-001", request).join();

        assertThat(result.publishedCount()).isEqualTo(2);
        verify(kafkaTemplate).send(eq("activity-events"), eq("session-001"), anyString());
        verify(kafkaTemplate).send(eq("activity-events"), eq("session-002"), anyString());
        verify(metrics).recordAccepted(2);
    }

    @Test
    void addsTheSameRequestMetadataAndSequentialEventIndexesToTheBatch() throws Exception {
        @SuppressWarnings("unchecked")
        KafkaTemplate<String, String> kafkaTemplate = mock(KafkaTemplate.class);
        CollectorMetrics metrics = mock(CollectorMetrics.class);
        ObjectMapper objectMapper = new ObjectMapper();
        Clock clock = Clock.fixed(Instant.parse("2026-08-27T15:00:00Z"), ZoneOffset.UTC);

        when(kafkaTemplate.send(anyString(), anyString(), anyString()))
                .thenReturn(CompletableFuture.completedFuture(null));

        KafkaEventPublisher publisher = new KafkaEventPublisher(
                kafkaTemplate,
                objectMapper,
                metrics,
                clock,
                "activity-events",
                Runnable::run
        );

        publisher.publish("request-001", List.of(
                new IndexedActivityEvent(event("evt-001", null), 0),
                new IndexedActivityEvent(event("evt-002", null), 2)
        )).join();

        ArgumentCaptor<String> payloadCaptor = ArgumentCaptor.forClass(String.class);
        verify(kafkaTemplate, times(2)).send(
                eq("activity-events"),
                eq("session-001"),
                payloadCaptor.capture()
        );

        KafkaEventMessage first = objectMapper.readValue(
                payloadCaptor.getAllValues().get(0),
                KafkaEventMessage.class
        );
        KafkaEventMessage second = objectMapper.readValue(
                payloadCaptor.getAllValues().get(1),
                KafkaEventMessage.class
        );

        assertThat(first.requestId()).isEqualTo("request-001");
        assertThat(second.requestId()).isEqualTo("request-001");
        assertThat(first.receivedAt()).isEqualTo(Instant.parse("2026-08-27T15:00:00Z"));
        assertThat(second.receivedAt()).isEqualTo(Instant.parse("2026-08-27T15:00:00Z"));
        assertThat(first.eventIndex()).isZero();
        assertThat(second.eventIndex()).isEqualTo(2);
        assertThat(first.source()).isEqualTo("web");
        assertThat(second.source()).isEqualTo("web");
    }

    @Test
    void publishesAnEventWithANullPersonaId() {
        @SuppressWarnings("unchecked")
        KafkaTemplate<String, String> kafkaTemplate = mock(KafkaTemplate.class);
        CollectorMetrics metrics = mock(CollectorMetrics.class);
        ObjectMapper objectMapper = new ObjectMapper();
        Clock clock = Clock.fixed(Instant.parse("2026-08-27T15:00:00Z"), ZoneOffset.UTC);

        when(kafkaTemplate.send(eq("activity-events"), eq("session-001"), anyString()))
                .thenReturn(CompletableFuture.completedFuture(null));

        KafkaEventPublisher publisher = new KafkaEventPublisher(
                kafkaTemplate,
                objectMapper,
                metrics,
                clock,
                "activity-events",
                Runnable::run
        );

        PublishSummary result = publisher.publish("request-001", new EventBatchRequest(
                "0.2.0-draft",
                List.of(event("evt-001", null))
        )).join();

        assertThat(result.publishedCount()).isEqualTo(1);
        verify(kafkaTemplate).send(eq("activity-events"), eq("session-001"), anyString());
    }

    @Test
    void recordsTheWholeBatchAsFailedWhenKafkaSendFails() {
        @SuppressWarnings("unchecked")
        KafkaTemplate<String, String> kafkaTemplate = mock(KafkaTemplate.class);
        CollectorMetrics metrics = mock(CollectorMetrics.class);
        ObjectMapper objectMapper = new ObjectMapper();
        Clock clock = Clock.fixed(Instant.parse("2026-08-27T15:00:00Z"), ZoneOffset.UTC);

        when(kafkaTemplate.send(anyString(), anyString(), anyString()))
                .thenReturn(CompletableFuture.failedFuture(new RuntimeException("Kafka unavailable")));

        KafkaEventPublisher publisher = new KafkaEventPublisher(
                kafkaTemplate,
                objectMapper,
                metrics,
                clock,
                "activity-events",
                Runnable::run
        );
        EventBatchRequest request = new EventBatchRequest("draft", List.of(
                event("evt-001", "persona-001"),
                event("evt-002", "persona-002")
        ));

        assertThatThrownBy(() -> publisher.publish("request-001", request).join())
                .hasCauseInstanceOf(EventPublishException.class);

        verify(metrics).recordKafkaPublishFailure(2);
        verify(metrics, never()).recordAccepted(any(Integer.class));
    }

    @Test
    void convertsASynchronousKafkaSendFailureIntoAFailedFuture() {
        @SuppressWarnings("unchecked")
        KafkaTemplate<String, String> kafkaTemplate = mock(KafkaTemplate.class);
        CollectorMetrics metrics = mock(CollectorMetrics.class);
        ObjectMapper objectMapper = new ObjectMapper();
        Clock clock = Clock.fixed(Instant.parse("2026-08-27T15:00:00Z"), ZoneOffset.UTC);

        when(kafkaTemplate.send(anyString(), anyString(), anyString()))
                .thenThrow(new RuntimeException("Kafka metadata unavailable"));

        KafkaEventPublisher publisher = new KafkaEventPublisher(
                kafkaTemplate,
                objectMapper,
                metrics,
                clock,
                "activity-events",
                Runnable::run
        );
        EventBatchRequest request = new EventBatchRequest(
                "draft",
                List.of(event("evt-001", "persona-001"))
        );

        CompletableFuture<PublishSummary> result = publisher.publish("request-001", request);

        assertThatThrownBy(result::join)
                .hasCauseInstanceOf(EventPublishException.class);
        verify(metrics).recordKafkaPublishFailure(1);
        verify(metrics, never()).recordAccepted(any(Integer.class));
    }

    @Test
    void initiatesKafkaSendOnTheDedicatedExecutorThread() {
        @SuppressWarnings("unchecked")
        KafkaTemplate<String, String> kafkaTemplate = mock(KafkaTemplate.class);
        CollectorMetrics metrics = mock(CollectorMetrics.class);
        ObjectMapper objectMapper = new ObjectMapper();
        Clock clock = Clock.fixed(Instant.parse("2026-08-27T15:00:00Z"), ZoneOffset.UTC);
        AtomicReference<String> sendThreadName = new AtomicReference<>();
        ExecutorService executor = Executors.newSingleThreadExecutor(runnable ->
                new Thread(runnable, "test-kafka-publisher")
        );

        when(kafkaTemplate.send(anyString(), anyString(), anyString())).thenAnswer(invocation -> {
            sendThreadName.set(Thread.currentThread().getName());
            return CompletableFuture.completedFuture(null);
        });

        KafkaEventPublisher publisher = new KafkaEventPublisher(
                kafkaTemplate,
                objectMapper,
                metrics,
                clock,
                "activity-events",
                executor
        );

        try {
            publisher.publish("request-001", new EventBatchRequest(
                    "draft",
                    List.of(event("evt-001", "persona-001"))
            )).join();
        } finally {
            executor.shutdownNow();
        }

        assertThat(sendThreadName.get()).isEqualTo("test-kafka-publisher");
    }

    @Test
    void failsFastWhenTheDedicatedExecutorRejectsTheBatch() {
        @SuppressWarnings("unchecked")
        KafkaTemplate<String, String> kafkaTemplate = mock(KafkaTemplate.class);
        CollectorMetrics metrics = mock(CollectorMetrics.class);
        ObjectMapper objectMapper = new ObjectMapper();
        Clock clock = Clock.fixed(Instant.parse("2026-08-27T15:00:00Z"), ZoneOffset.UTC);

        KafkaEventPublisher publisher = new KafkaEventPublisher(
                kafkaTemplate,
                objectMapper,
                metrics,
                clock,
                "activity-events",
                command -> {
                    throw new RejectedExecutionException("executor saturated");
                }
        );

        CompletableFuture<PublishSummary> result = publisher.publish("request-001", new EventBatchRequest(
                "draft",
                List.of(event("evt-001", "persona-001"))
        ));

        assertThatThrownBy(result::join)
                .hasCauseInstanceOf(EventPublishOverloadedException.class);
        verify(metrics).recordKafkaPublishOverloaded(1);
        verify(metrics, never()).recordKafkaPublishFailure(any(Integer.class));
        verify(metrics, never()).recordAccepted(any(Integer.class));
        verify(kafkaTemplate, never()).send(anyString(), anyString(), anyString());
    }

    @Test
    void rejectsAnotherBatchWhileThePreviousBatchIsWaitingForKafkaAck() {
        @SuppressWarnings("unchecked")
        KafkaTemplate<String, String> kafkaTemplate = mock(KafkaTemplate.class);
        CollectorMetrics metrics = mock(CollectorMetrics.class);
        ObjectMapper objectMapper = new ObjectMapper();
        CompletableFuture<SendResult<String, String>> kafkaAck = new CompletableFuture<>();

        when(kafkaTemplate.send(anyString(), anyString(), anyString())).thenReturn(kafkaAck);

        KafkaEventPublisher publisher = new KafkaEventPublisher(
                kafkaTemplate,
                objectMapper,
                metrics,
                Clock.systemUTC(),
                "activity-events",
                Runnable::run,
                new Semaphore(1)
        );
        EventBatchRequest request = new EventBatchRequest("draft", List.of(event("evt-001", "persona-001")));

        CompletableFuture<PublishSummary> first = publisher.publish("request-001", request);
        CompletableFuture<PublishSummary> second = publisher.publish("request-002", request);

        assertThat(first).isNotDone();
        assertThatThrownBy(second::join)
                .hasCauseInstanceOf(EventPublishOverloadedException.class);
        verify(metrics).recordKafkaPublishOverloaded(1);

        kafkaAck.complete(null);
        first.join();
    }

    @Test
    void releasesTheInFlightSlotAfterKafkaAckCompletes() {
        @SuppressWarnings("unchecked")
        KafkaTemplate<String, String> kafkaTemplate = mock(KafkaTemplate.class);
        CollectorMetrics metrics = mock(CollectorMetrics.class);
        ObjectMapper objectMapper = new ObjectMapper();
        CompletableFuture<SendResult<String, String>> kafkaAck = new CompletableFuture<>();

        when(kafkaTemplate.send(anyString(), anyString(), anyString()))
                .thenReturn(kafkaAck, CompletableFuture.<SendResult<String, String>>completedFuture(null));

        KafkaEventPublisher publisher = new KafkaEventPublisher(
                kafkaTemplate,
                objectMapper,
                metrics,
                Clock.systemUTC(),
                "activity-events",
                Runnable::run,
                new Semaphore(1)
        );
        EventBatchRequest request = new EventBatchRequest("draft", List.of(event("evt-001", "persona-001")));

        CompletableFuture<PublishSummary> first = publisher.publish("request-001", request);
        kafkaAck.complete(null);
        first.join();

        PublishSummary second = publisher.publish("request-002", request).join();

        assertThat(second.publishedCount()).isEqualTo(1);
        verify(kafkaTemplate, times(2)).send(anyString(), anyString(), anyString());
    }

    private ActivityEvent event(String eventId, String personaId) {
        return event(eventId, personaId, "session-001");
    }

    private ActivityEvent event(String eventId, String personaId, String sessionId) {
        return new ActivityEvent(
                "0.2.0-draft",
                eventId,
                "product_click",
                "comparison",
                Instant.parse("2026-08-27T14:30:00Z"),
                personaId,
                sessionId,
                "page-view-001",
                1,
                "product_list",
                "product-001",
                "user",
                "local",
                null
        );
    }
}
