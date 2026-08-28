package com.cosmetic.collector.config;

import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.TopicBuilder;

@Configuration
@ConditionalOnProperty(name = "collector.kafka.create-topic", havingValue = "true")
public class KafkaTopicConfig {

    @Bean
    NewTopic activityEventsTopic(
            @Value("${collector.kafka.topic}") String topic,
            @Value("${collector.kafka.partitions}") int partitions
    ) {
        return TopicBuilder.name(topic)
                .partitions(partitions)
                .replicas(1)
                .build();
    }
}
