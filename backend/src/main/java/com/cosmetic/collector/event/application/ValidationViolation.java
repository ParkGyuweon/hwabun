package com.cosmetic.collector.event.application;

/** Collector가 거부한 이벤트의 검증 상세다. */
public record ValidationViolation(String code, String field, String message) {
}
