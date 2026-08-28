package com.cosmetic.collector.event.observability;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
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

        assertThat(counter(registry, "collector.events.received")).isEqualTo(50);
        assertThat(counter(registry, "collector.events.published")).isEqualTo(45);
        assertThat(counter(registry, "collector.events.publish.failures")).isEqualTo(5);
    }

    @Test
    void accumulatesValuesAcrossMultipleBatches() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        CollectorMetrics metrics = new CollectorMetrics(registry);

        metrics.recordReceived(20);
        metrics.recordReceived(30);

        assertThat(counter(registry, "collector.events.received")).isEqualTo(50);
    }

    private double counter(SimpleMeterRegistry registry, String name) {
        return registry.get(name).counter().count();
    }
}
