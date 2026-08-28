package com.cosmetic.collector.event.api;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.PropertyNamingStrategies;
import tools.jackson.databind.annotation.JsonNaming;

import java.time.Instant;

@Schema(description = "사용자 행동 로그 한 건")
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record ActivityEvent(
        @Schema(description = "중복 제거에 사용하는 이벤트 고유 ID", example = "evt-001")
        @NotBlank String eventId,

        @Schema(description = "행동 유형", example = "product.click")
        @NotBlank String eventType,

        @Schema(description = "클라이언트에서 행동이 발생한 UTC 시각", example = "2026-08-27T14:30:00Z")
        @NotNull Instant eventTime,

        @Schema(description = "가상 소비자 식별자", example = "persona-001")
        @NotBlank String personaId,

        @Schema(description = "한 번의 방문을 구분하는 분석용 세션 ID", example = "session-001")
        @NotBlank String sessionId,

        @Schema(description = "행동과 관련된 상품 ID", example = "product-001", nullable = true)
        String productId,

        @Schema(description = "이벤트 종류별 추가 속성", example = "{\"position\": 1}", nullable = true)
        JsonNode properties
) {
}
