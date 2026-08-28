package com.cosmetic.collector.event.api;

import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

import static org.assertj.core.api.Assertions.assertThat;

class EventJsonContractTest {

    private final ObjectMapper objectMapper = new ObjectMapper();

    @Test
    void deserializesSnakeCaseJsonIntoTheJavaRequest() throws Exception {
        String json = """
                {
                  "schema_version": "0.2.0-draft",
                  "events": [{
                    "schema_version": "0.2.0-draft",
                    "event_id": "evt-001",
                    "event_name": "product_click",
                    "intent": "comparison",
                    "occurred_at": "2026-08-27T14:30:00Z",
                    "persona_id": null,
                    "session_id": "session-001",
                    "page_view_id": "page-view-001",
                    "sequence_no": 45,
                    "page_type": "product_list",
                    "product_id": "product-001",
                    "actor_type": "user",
                    "environment": "local",
                    "properties": {"position": 1}
                  }]
                }
                """;

        EventBatchRequest request = objectMapper.readValue(json, EventBatchRequest.class);

        assertThat(request.schemaVersion()).isEqualTo("0.2.0-draft");
        assertThat(request.events()).hasSize(1);
        ActivityEvent event = request.events().getFirst();
        assertThat(event.schemaVersion()).isEqualTo("0.2.0-draft");
        assertThat(event.eventId()).isEqualTo("evt-001");
        assertThat(event.eventName()).isEqualTo("product_click");
        assertThat(event.intent()).isEqualTo("comparison");
        assertThat(event.occurredAt()).isEqualTo(java.time.Instant.parse("2026-08-27T14:30:00Z"));
        assertThat(event.personaId()).isNull();
        assertThat(event.pageViewId()).isEqualTo("page-view-001");
        assertThat(event.sequenceNo()).isEqualTo(45);
        assertThat(event.pageType()).isEqualTo("product_list");
        assertThat(event.actorType()).isEqualTo("user");
        assertThat(event.environment()).isEqualTo("local");
    }

    @Test
    void serializesTheResponseUsingSnakeCaseNames() throws Exception {
        EventAcceptedResponse response = new EventAcceptedResponse("request-001", 50, 0);

        String json = objectMapper.writeValueAsString(response);

        assertThat(json)
                .contains("\"request_id\":\"request-001\"")
                .doesNotContain("requestId");
    }
}
