package com.cosmetic.collector.event.application;

public class EventPublishOverloadedException extends RuntimeException {

    public EventPublishOverloadedException(String message, Throwable cause) {
        super(message, cause);
    }
}
