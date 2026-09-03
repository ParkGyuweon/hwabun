package com.cosmetic.collector.event.observability;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.time.Duration;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class CollectorMetricsTest {

    @Test
    void countsReceivedPublishedAndFailedEventsSeparately() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        CollectorMetrics metrics = new CollectorMetrics(registry);

        metrics.recordReceived(50);
        metrics.recordPublished(45);
        metrics.recordPublishFailure(5);
        metrics.recordPublishRejected(2);
        metrics.recordValidationFailure("invalid_event_batch");
        metrics.recordPublishQueueWait(Duration.ofMillis(25));

        assertThat(counter(registry, "collector.events.received")).isEqualTo(50);
        assertThat(counter(registry, "collector.events.published")).isEqualTo(45);
        assertThat(counter(registry, "collector.events.publish.failures")).isEqualTo(5);
        assertThat(counter(registry, "collector.events.publish.rejected")).isEqualTo(2);
        assertThat(registry.get("collector.events.validation.failures")
                .tag("reason", "invalid_event_batch").counter().count()).isEqualTo(1);
        assertThat(registry.get("collector.events.publish.queue.wait").timer().count()).isEqualTo(1);
        assertThat(registry.get("collector.events.publish.queue.wait").timer()
                .totalTime(TimeUnit.MILLISECONDS)).isEqualTo(25);
    }

    @Test
    void accumulatesValuesAcrossMultipleBatches() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        CollectorMetrics metrics = new CollectorMetrics(registry);

        metrics.recordReceived(20);
        metrics.recordReceived(30);

        assertThat(counter(registry, "collector.events.received")).isEqualTo(50);
    }

    @Test
    void countsEachRejectedEventInsteadOfOnlyTheContainingBatch() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        CollectorMetrics metrics = new CollectorMetrics(registry);

        metrics.recordValidationFailure("invalid_event_contract", 3);

        assertThat(registry.get("collector.events.validation.failures")
                .tag("reason", "invalid_event_contract").counter().count()).isEqualTo(3);
    }

    private double counter(SimpleMeterRegistry registry, String name) {
        return registry.get(name).counter().count();
    }
}
