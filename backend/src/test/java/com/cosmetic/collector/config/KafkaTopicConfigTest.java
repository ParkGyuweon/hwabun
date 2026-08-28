package com.cosmetic.collector.config;

import org.apache.kafka.clients.admin.NewTopic;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class KafkaTopicConfigTest {

    @Test
    void createsTheConfiguredTopicWithThreePartitionsForLocalDevelopment() {
        NewTopic topic = new KafkaTopicConfig().activityEventsTopic("activity-events", 3);

        assertThat(topic.name()).isEqualTo("activity-events");
        assertThat(topic.numPartitions()).isEqualTo(3);
        assertThat(topic.replicationFactor()).isEqualTo((short) 1);
    }
}
