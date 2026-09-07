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
    private final Counter accepted;
    private final Counter eventRejected;
    private final Counter publishFailures;
    private final Counter publishOverloaded;
    private final Timer publishQueueWait;

    public CollectorMetrics(MeterRegistry registry) {
        this.registry = registry;
        this.received = registry.counter("collector.events.received");
        this.accepted = registry.counter("collector.events.accepted");
        this.eventRejected = registry.counter("collector.events.rejected");
        this.publishFailures = registry.counter("collector.kafka.publish.failures");
        this.publishOverloaded = registry.counter("collector.kafka.publish.overloaded");
        this.publishQueueWait = registry.timer("collector.kafka.publish.queue.wait");
    }

    public void recordReceived(int count) {
        received.increment(count);
    }

    public void recordAccepted(int count) {
        accepted.increment(count);
    }

    public void recordEventRejected(int count) {
        eventRejected.increment(count);
    }

    public void recordKafkaPublishFailure(int count) {
        publishFailures.increment(count);
    }

    public void recordKafkaPublishOverloaded(int count) {
        publishOverloaded.increment(count);
    }

    public void recordPublishQueueWait(Duration duration) {
        publishQueueWait.record(duration);
    }

    public void recordValidationRejected(String code) {
        registry.counter("collector.events.validation.rejected", "code", code).increment();
    }
}
