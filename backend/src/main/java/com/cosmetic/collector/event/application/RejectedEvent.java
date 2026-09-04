package com.cosmetic.collector.event.application;

import com.cosmetic.collector.event.api.ActivityEvent;

import java.util.List;

/** Kafka 정상 topic에서 제외하고 HTTP 응답 요약에 사용하는 이벤트다. */
public record RejectedEvent(
        ActivityEvent event,
        int eventIndex,
        List<ValidationViolation> violations
) {
}
