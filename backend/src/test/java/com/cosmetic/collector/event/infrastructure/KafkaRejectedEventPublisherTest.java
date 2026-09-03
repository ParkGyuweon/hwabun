package com.cosmetic.collector.event.infrastructure;

import com.cosmetic.collector.event.api.ActivityEvent;
import com.cosmetic.collector.event.application.RejectedEvent;
import com.cosmetic.collector.event.application.ValidationViolation;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.kafka.core.KafkaTemplate;
import tools.jackson.databind.ObjectMapper;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.concurrent.CompletableFuture;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class KafkaRejectedEventPublisherTest {

    @Test
    void publishesOriginalEventIndexAndViolationsToTheRejectedTopic() throws Exception {
        @SuppressWarnings("unchecked")
        KafkaTemplate<String, String> kafkaTemplate = mock(KafkaTemplate.class);
        ObjectMapper objectMapper = new ObjectMapper();
        when(kafkaTemplate.send(eq("activity-events-rejected"), eq("request-001"), anyString()))
                .thenReturn(CompletableFuture.completedFuture(null));

        KafkaRejectedEventPublisher publisher = new KafkaRejectedEventPublisher(
                kafkaTemplate,
                objectMapper,
                Clock.fixed(Instant.parse("2026-09-03T00:00:00Z"), ZoneOffset.UTC),
                "activity-events-rejected"
        );
        ActivityEvent event = new ActivityEvent(
                "0.2.0-draft", "evt-invalid", "purchase_reason_select", "validation",
                Instant.parse("2026-09-03T00:00:00Z"), null, "session-001", "page-001", 3,
                "cart", null, "user", "local", objectMapper.createObjectNode()
        );

        publisher.publish("request-001", List.of(new RejectedEvent(
                event,
                2,
                List.of(new ValidationViolation("collector_validation_failure", "properties", "invalid reason"))
        ))).join();

        ArgumentCaptor<String> payload = ArgumentCaptor.forClass(String.class);
        verify(kafkaTemplate).send(eq("activity-events-rejected"), eq("request-001"), payload.capture());
        KafkaRejectedEventMessage message = objectMapper.readValue(payload.getValue(), KafkaRejectedEventMessage.class);
        assertThat(message.eventIndex()).isEqualTo(2);
        assertThat(message.event().eventId()).isEqualTo("evt-invalid");
        assertThat(message.violations()).singleElement()
                .extracting(ValidationViolation::field)
                .isEqualTo("properties");
    }
}
