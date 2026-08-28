package com.cosmetic.collector.event.infrastructure;

import com.cosmetic.collector.event.api.ActivityEvent;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

import java.time.Instant;

import static org.assertj.core.api.Assertions.assertThat;

class KafkaEventMessageTest {

    @Test
    void copiesTheClientEventAndAddsTheBackendReceivedTime() {
        ActivityEvent event = new ActivityEvent(
                "0.2.0-draft",
                "evt-001",
                "product_click",
                "comparison",
                Instant.parse("2026-08-27T14:30:00Z"),
                null,
                "session-001",
                "page-view-001",
                45,
                "product_list",
                "product-001",
                "user",
                "local",
                null
        );
        Instant receivedAt = Instant.parse("2026-08-27T14:30:01Z");

        KafkaEventMessage message = KafkaEventMessage.from(event, receivedAt, "request-001", 3);

        assertThat(message.schemaVersion()).isEqualTo("0.2.0-draft");
        assertThat(message.eventId()).isEqualTo("evt-001");
        assertThat(message.eventName()).isEqualTo("product_click");
        assertThat(message.intent()).isEqualTo("comparison");
        assertThat(message.personaId()).isNull();
        assertThat(message.occurredAt()).isEqualTo(Instant.parse("2026-08-27T14:30:00Z"));
        assertThat(message.pageViewId()).isEqualTo("page-view-001");
        assertThat(message.sequenceNo()).isEqualTo(45);
        assertThat(message.pageType()).isEqualTo("product_list");
        assertThat(message.actorType()).isEqualTo("user");
        assertThat(message.environment()).isEqualTo("local");
        assertThat(message.receivedAt()).isEqualTo(receivedAt);
        assertThat(message.source()).isEqualTo("web");
        assertThat(message.requestId()).isEqualTo("request-001");
        assertThat(message.eventIndex()).isEqualTo(3);
    }

    @Test
    void serializesTheKafkaMessageUsingTheFrontendFieldNames() throws Exception {
        ActivityEvent event = new ActivityEvent(
                "0.2.0-draft",
                "evt-001",
                "section_view",
                "interest",
                Instant.parse("2026-08-28T04:08:57.156Z"),
                null,
                "session-001",
                "page-view-001",
                45,
                "product_list",
                null,
                "user",
                "local",
                new ObjectMapper().createObjectNode().put("section_id", "product_grid")
        );

        String json = new ObjectMapper().writeValueAsString(KafkaEventMessage.from(
                event,
                Instant.parse("2026-08-28T04:08:58Z"),
                "request-001",
                0
        ));

        assertThat(json)
                .contains("\"schema_version\":\"0.2.0-draft\"")
                .contains("\"event_name\":\"section_view\"")
                .contains("\"intent\":\"interest\"")
                .contains("\"occurred_at\":\"2026-08-28T04:08:57.156Z\"")
                .contains("\"page_view_id\":\"page-view-001\"")
                .contains("\"sequence_no\":45")
                .contains("\"page_type\":\"product_list\"")
                .contains("\"actor_type\":\"user\"")
                .contains("\"environment\":\"local\"")
                .contains("\"received_at\":\"2026-08-28T04:08:58Z\"")
                .contains("\"source\":\"web\"")
                .contains("\"request_id\":\"request-001\"")
                .contains("\"event_index\":0")
                .doesNotContain("event_type", "event_time");
    }

    @Test
    void marksSyntheticEventsAsSimulatorSource() {
        ActivityEvent event = new ActivityEvent(
                "0.2.0-draft",
                "evt-001",
                "section_view",
                "interest",
                Instant.parse("2026-08-28T04:08:57.156Z"),
                "persona-001",
                "session-001",
                "page-view-001",
                1,
                "product_list",
                null,
                "synthetic",
                "loadtest",
                null
        );

        KafkaEventMessage message = KafkaEventMessage.from(
                event,
                Instant.parse("2026-08-28T04:08:58Z"),
                "request-001",
                0
        );

        assertThat(message.source()).isEqualTo("simulator");
    }
}
