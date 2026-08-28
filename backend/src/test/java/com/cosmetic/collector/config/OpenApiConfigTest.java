package com.cosmetic.collector.config;

import io.swagger.v3.oas.models.OpenAPI;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class OpenApiConfigTest {

    @Test
    void describesTheLogConnectorApi() {
        OpenAPI openAPI = new OpenApiConfig().logConnectorOpenApi();

        assertThat(openAPI.getInfo().getTitle()).isEqualTo("Cosmetic Activity Log Connector API");
        assertThat(openAPI.getInfo().getVersion()).isEqualTo("draft");
        assertThat(openAPI.getInfo().getDescription()).contains("Kafka");
    }
}
