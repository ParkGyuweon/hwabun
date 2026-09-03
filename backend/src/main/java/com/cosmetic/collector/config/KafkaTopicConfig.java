package com.cosmetic.collector.config;

import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.TopicBuilder;
import org.apache.kafka.common.config.TopicConfig;

import java.util.Map;

@Configuration
@ConditionalOnProperty(name = "collector.kafka.create-topic", havingValue = "true")
public class KafkaTopicConfig {

    @Bean
    NewTopic activityEventsTopic(
            @Value("${collector.kafka.topic}") String topic,
            @Value("${collector.kafka.partitions}") int partitions,
            @Value("${collector.kafka.replication-factor}") int replicationFactor,
            @Value("${collector.kafka.retention-ms}") long retentionMs
    ) {
        return TopicBuilder.name(topic)
                .partitions(partitions)
                .replicas(replicationFactor)
                .configs(Map.of(
                        TopicConfig.CLEANUP_POLICY_CONFIG, "delete",
                        TopicConfig.RETENTION_MS_CONFIG, Long.toString(retentionMs)
                ))
                .build();
    }

    @Bean
    NewTopic activityEventsRejectedTopic(
            @Value("${collector.kafka.rejected-topic}") String topic,
            @Value("${collector.kafka.partitions}") int partitions,
            @Value("${collector.kafka.replication-factor}") int replicationFactor,
            @Value("${collector.kafka.retention-ms}") long retentionMs
    ) {
        return TopicBuilder.name(topic)
                .partitions(partitions)
                .replicas(replicationFactor)
                .configs(Map.of(
                        TopicConfig.CLEANUP_POLICY_CONFIG, "delete",
                        TopicConfig.RETENTION_MS_CONFIG, Long.toString(retentionMs)
                ))
                .build();
    }
}
