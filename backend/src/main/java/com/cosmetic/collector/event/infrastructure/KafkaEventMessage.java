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
        String eventName,
        String intent,
        Instant occurredAt,
        String personaId,
        String sessionId,
        String pageViewId,
        Integer sequenceNo,
        String pageType,
        String productId,
        String actorType,
        String environment,
        JsonNode properties,
        Instant receivedAt
) {
    static KafkaEventMessage from(ActivityEvent event, Instant receivedAt) {
        return new KafkaEventMessage(
                event.schemaVersion(),
                event.eventId(),
                event.eventName(),
                event.intent(),
                event.occurredAt(),
                event.personaId(),
                event.sessionId(),
                event.pageViewId(),
                event.sequenceNo(),
                event.pageType(),
                event.productId(),
                event.actorType(),
                event.environment(),
                event.properties(),
                receivedAt
        );
    }
}
