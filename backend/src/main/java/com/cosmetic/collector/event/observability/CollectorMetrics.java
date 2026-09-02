package com.cosmetic.collector.event.observability;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.time.Duration;
import org.springframework.stereotype.Component;

@Component
public class CollectorMetrics {

    private final MeterRegistry registry;
    private final Counter received;
    private final Counter published;
    private final Counter publishFailures;
    private final Counter publishRejections;
    private final Timer publishQueueWait;

    public CollectorMetrics(MeterRegistry registry) {
        this.registry = registry;
        this.received = registry.counter("collector.events.received");
        this.published = registry.counter("collector.events.published");
        this.publishFailures = registry.counter("collector.events.publish.failures");
        this.publishRejections = registry.counter("collector.events.publish.rejected");
        this.publishQueueWait = registry.timer("collector.events.publish.queue.wait");
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

    public void recordPublishRejected(int count) {
        publishRejections.increment(count);
    }

    public void recordPublishQueueWait(Duration duration) {
        publishQueueWait.record(duration);
    }

    public void recordValidationFailure(String reason) {
        registry.counter("collector.events.validation.failures", "reason", reason).increment();
    }
}
