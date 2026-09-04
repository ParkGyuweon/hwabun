package com.cosmetic.collector.event.observability;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.time.Duration;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class CollectorMetricsTest {

    @Test
    void separatesAcceptedRejectedValidationAndKafkaMetrics() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        CollectorMetrics metrics = new CollectorMetrics(registry);

        metrics.recordReceived(50);
        metrics.recordAccepted(45);
        metrics.recordEventRejected(3);
        metrics.recordKafkaPublishFailure(5);
        metrics.recordKafkaPublishOverloaded(2);
        metrics.recordValidationRejected("invalid_event_batch");
        metrics.recordPublishQueueWait(Duration.ofMillis(25));

        assertThat(counter(registry, "collector.events.received")).isEqualTo(50);
        assertThat(counter(registry, "collector.events.accepted")).isEqualTo(45);
        assertThat(counter(registry, "collector.events.rejected")).isEqualTo(3);
        assertThat(counter(registry, "collector.kafka.publish.failures")).isEqualTo(5);
        assertThat(counter(registry, "collector.kafka.publish.overloaded")).isEqualTo(2);
        assertThat(registry.get("collector.events.validation.rejected")
                .tag("code", "invalid_event_batch").counter().count()).isEqualTo(1);
        assertThat(registry.get("collector.kafka.publish.queue.wait").timer().count()).isEqualTo(1);
        assertThat(registry.get("collector.kafka.publish.queue.wait").timer()
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
    void recordsValidationCodesIndependentlyFromRejectedEventCounts() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        CollectorMetrics metrics = new CollectorMetrics(registry);

        metrics.recordEventRejected(3);
        metrics.recordValidationRejected("missing_required_property");
        metrics.recordValidationRejected("invalid_property_enum");

        assertThat(counter(registry, "collector.events.rejected")).isEqualTo(3);
        assertThat(registry.get("collector.events.validation.rejected")
                .tag("code", "missing_required_property").counter().count()).isEqualTo(1);
        assertThat(registry.get("collector.events.validation.rejected")
                .tag("code", "invalid_property_enum").counter().count()).isEqualTo(1);
    }

    private double counter(SimpleMeterRegistry registry, String name) {
        return registry.get(name).counter().count();
    }
}
