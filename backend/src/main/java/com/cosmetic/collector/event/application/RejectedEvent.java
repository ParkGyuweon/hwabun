package com.cosmetic.collector.event.application;

import com.cosmetic.collector.event.api.ActivityEvent;

import java.util.List;

/** Kafka 정상 topic에는 넣지 않지만 원인 분석을 위해 보존할 이벤트다. */
public record RejectedEvent(
        ActivityEvent event,
        int eventIndex,
        List<ValidationViolation> violations
) {
}
