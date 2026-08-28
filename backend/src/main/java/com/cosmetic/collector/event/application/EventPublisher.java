package com.cosmetic.collector.event.application;

import com.cosmetic.collector.event.api.EventBatchRequest;

import java.util.concurrent.CompletableFuture;

public interface EventPublisher {

    CompletableFuture<PublishSummary> publish(String requestId, EventBatchRequest request);
}
