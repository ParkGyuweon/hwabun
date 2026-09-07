package com.cosmetic.collector.event.api.validation;

/** 배치 envelope가 유효하지 않아 개별 이벤트 처리로 진행할 수 없을 때 발생한다. */
public class InvalidEventBatchException extends RuntimeException {
}
