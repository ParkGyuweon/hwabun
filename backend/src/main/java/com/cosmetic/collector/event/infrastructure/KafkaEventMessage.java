package com.cosmetic.collector.event.infrastructure;

import com.cosmetic.collector.event.api.ActivityEvent;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.PropertyNamingStrategies;
import tools.jackson.databind.annotation.JsonNaming;

import java.time.Instant;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record KafkaEventMessage(
        String schemaVersion,
        String eventId,
        String eventType,
        Instant eventTime,
        String personaId,
        String sessionId,
        String productId,
        JsonNode properties,
        Instant receivedAt
) {
    static KafkaEventMessage from(String schemaVersion, ActivityEvent event, Instant receivedAt) {
        return new KafkaEventMessage(
                schemaVersion,
                event.eventId(),
                event.eventType(),
                event.eventTime(),
                event.personaId(),
                event.sessionId(),
                event.productId(),
                event.properties(),
                receivedAt
        );
    }
}
