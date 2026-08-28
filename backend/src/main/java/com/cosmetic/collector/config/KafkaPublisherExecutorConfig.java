package com.cosmetic.collector.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

import java.util.concurrent.ThreadPoolExecutor;

@Configuration
public class KafkaPublisherExecutorConfig {

    @Bean(name = "kafkaPublisherExecutor")
    public ThreadPoolTaskExecutor kafkaPublisherExecutor(
            @Value("${collector.kafka.publisher-executor.core-pool-size}") int corePoolSize,
            @Value("${collector.kafka.publisher-executor.max-pool-size}") int maxPoolSize,
            @Value("${collector.kafka.publisher-executor.queue-capacity}") int queueCapacity
    ) {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(corePoolSize);
        executor.setMaxPoolSize(maxPoolSize);
        executor.setQueueCapacity(queueCapacity);
        executor.setThreadNamePrefix("kafka-publisher-");
        executor.setRejectedExecutionHandler(new ThreadPoolExecutor.AbortPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);
        executor.initialize();
        return executor;
    }
}
