package com.cosmetic.collector.event.application;

import com.cosmetic.collector.event.api.ActivityEvent;

/** 원본 HTTP events 배열에서의 위치를 보존하는 검증 완료 이벤트다. */
public record IndexedActivityEvent(ActivityEvent event, int eventIndex) {
}
