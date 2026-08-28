package com.cosmetic.collector.event.observability;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class CollectorMetrics {

    private final Counter received;
    private final Counter published;
    private final Counter publishFailures;

    public CollectorMetrics(MeterRegistry registry) {
        this.received = registry.counter("collector.events.received");
        this.published = registry.counter("collector.events.published");
        this.publishFailures = registry.counter("collector.events.publish.failures");
    }

    public void recordReceived(int count) {
        received.increment(count);
    }

    public void recordPublished(int count) {
        published.increment(count);
    }

    public void recordPublishFailure(int count) {
        publishFailures.increment(count);
    }
}
