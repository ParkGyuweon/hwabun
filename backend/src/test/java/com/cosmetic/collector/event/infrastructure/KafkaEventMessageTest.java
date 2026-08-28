package com.cosmetic.collector.event.infrastructure;

import com.cosmetic.collector.event.api.ActivityEvent;
import org.junit.jupiter.api.Test;

import java.time.Instant;

import static org.assertj.core.api.Assertions.assertThat;

class KafkaEventMessageTest {

    @Test
    void copiesTheClientEventAndAddsTheBackendReceivedTime() {
        ActivityEvent event = new ActivityEvent(
                "evt-001",
                "product.click",
                Instant.parse("2026-08-27T14:30:00Z"),
                "persona-001",
                "session-001",
                "product-001",
                null
        );
        Instant receivedAt = Instant.parse("2026-08-27T14:30:01Z");

        KafkaEventMessage message = KafkaEventMessage.from("draft", event, receivedAt);

        assertThat(message.schemaVersion()).isEqualTo("draft");
        assertThat(message.eventId()).isEqualTo("evt-001");
        assertThat(message.personaId()).isEqualTo("persona-001");
        assertThat(message.eventTime()).isEqualTo(Instant.parse("2026-08-27T14:30:00Z"));
        assertThat(message.receivedAt()).isEqualTo(receivedAt);
    }
}
