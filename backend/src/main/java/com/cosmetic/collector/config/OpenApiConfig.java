package com.cosmetic.collector.config;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OpenApiConfig {

    @Bean
    OpenAPI logConnectorOpenApi() {
        return new OpenAPI().info(new Info()
                .title("Cosmetic Activity Log Connector API")
                .description("프론트엔드 활동 로그를 검증하고 Kafka에 발행하는 API")
                .version("draft")
                .contact(new Contact().name("Backend Team")));
    }
}
