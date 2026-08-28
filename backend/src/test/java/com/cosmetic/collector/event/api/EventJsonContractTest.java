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
                  "schema_version": "draft",
                  "events": [{
                    "event_id": "evt-001",
                    "event_type": "product.click",
                    "event_time": "2026-08-27T14:30:00Z",
                    "persona_id": "persona-001",
                    "session_id": "session-001"
                  }]
                }
                """;

        EventBatchRequest request = objectMapper.readValue(json, EventBatchRequest.class);

        assertThat(request.schemaVersion()).isEqualTo("draft");
        assertThat(request.events()).hasSize(1);
        assertThat(request.events().getFirst().eventId()).isEqualTo("evt-001");
        assertThat(request.events().getFirst().personaId()).isEqualTo("persona-001");
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
