package com.cosmetic.collector.event.infrastructure;

import com.cosmetic.collector.event.api.ActivityEvent;
import com.cosmetic.collector.event.application.ValidationViolation;
import tools.jackson.databind.PropertyNamingStrategies;
import tools.jackson.databind.annotation.JsonNaming;

import java.time.Instant;
import java.util.List;

/** Spark bad_events 입력으로 사용하는 Collector 거부 이벤트 메시지다. */
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record KafkaRejectedEventMessage(
        String requestId,
        int eventIndex,
        Instant receivedAt,
        ActivityEvent event,
        List<ValidationViolation> violations
) {
}
