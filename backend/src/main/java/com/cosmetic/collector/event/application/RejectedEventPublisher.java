package com.cosmetic.collector.event.application;

import java.util.List;
import java.util.concurrent.CompletableFuture;

public interface RejectedEventPublisher {

    CompletableFuture<Void> publish(String requestId, List<RejectedEvent> rejectedEvents);
}
