package com.cosmetic.collector.config;

import org.apache.kafka.clients.admin.NewTopic;
import org.apache.kafka.common.config.TopicConfig;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class KafkaTopicConfigTest {

    @Test
    void createsTheConfiguredTopicWithLocalDevelopmentSettings() {
        NewTopic topic = new KafkaTopicConfig()
                .activityEventsTopic("activity-events", 3, 1, 86_400_000L);

        assertThat(topic.name()).isEqualTo("activity-events");
        assertThat(topic.numPartitions()).isEqualTo(3);
        assertThat(topic.replicationFactor()).isEqualTo((short) 1);
        assertThat(topic.configs())
                .containsEntry(TopicConfig.CLEANUP_POLICY_CONFIG, "delete")
                .containsEntry(TopicConfig.RETENTION_MS_CONFIG, "86400000");
    }
}
