package com.cosmetic.collector.event.application;

import com.cosmetic.collector.event.api.EventBatchRequest;

import java.util.List;
import java.util.concurrent.CompletableFuture;

public interface EventPublisher {

    CompletableFuture<PublishSummary> publish(String requestId, List<IndexedActivityEvent> events);

    /** 기존 호출부와 직접 Publisher 테스트를 위한 편의 메서드다. */
    default CompletableFuture<PublishSummary> publish(String requestId, EventBatchRequest request) {
        return publish(requestId, java.util.stream.IntStream.range(0, request.events().size())
                .mapToObj(index -> new IndexedActivityEvent(request.events().get(index), index))
                .toList());
    }
}
