package com.cosmetic.collector.event.api;

import com.cosmetic.collector.event.api.validation.ValidEventContract;
import com.cosmetic.collector.event.api.serialization.LenientInstantDeserializer;
import com.cosmetic.collector.event.api.serialization.LenientIntegerDeserializer;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Positive;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.PropertyNamingStrategies;
import tools.jackson.databind.annotation.JsonNaming;
import tools.jackson.databind.annotation.JsonDeserialize;

import java.time.Instant;

@Schema(description = "사용자 행동 로그 한 건")
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
@ValidEventContract
public record ActivityEvent(
        @Schema(description = "이벤트 계약 버전", example = "0.3.0-draft")
        @NotBlank @Pattern(regexp = "^0\\.(2|3)\\.0-draft$") String schemaVersion,

        @Schema(description = "중복 제거에 사용하는 이벤트 고유 ID", example = "evt-001")
        @NotBlank String eventId,

        @Schema(description = "행동 이벤트 이름", example = "product_click")
        @NotBlank
        @Pattern(regexp = "^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
        String eventName,

        @Schema(description = "이벤트의 분석 의미", example = "comparison")
        @NotBlank
        @Pattern(regexp = "^(exposure|interest|comparison|validation|hesitation|conversion|friction|session)$")
        String intent,

        @Schema(description = "클라이언트에서 행동이 발생한 UTC 시각", example = "2026-08-27T14:30:00Z")
        @JsonDeserialize(using = LenientInstantDeserializer.class)
        @NotNull Instant occurredAt,

        @Schema(description = "가상 소비자 식별자", example = "persona-001", nullable = true)
        String personaId,

        @Schema(description = "한 번의 방문을 구분하는 분석용 세션 ID", example = "session-001")
        @NotBlank String sessionId,

        @Schema(description = "한 페이지 조회 단위를 구분하는 ID", example = "page-view-001")
        @NotBlank String pageViewId,

        @Schema(description = "세션 내 이벤트 발생 순번", example = "45")
        @JsonDeserialize(using = LenientIntegerDeserializer.class)
        @NotNull @Positive Integer sequenceNo,

        @Schema(description = "이벤트가 발생한 페이지 유형", example = "product_list")
        @NotBlank
        @Pattern(regexp = "^(product_list|product_detail|cart)$")
        String pageType,

        @Schema(description = "행동과 관련된 상품 ID", example = "product-001", nullable = true)
        String productId,

        @Schema(description = "행위자 유형", example = "user")
        @NotBlank
        @Pattern(regexp = "^(user|synthetic)$")
        String actorType,

        @Schema(description = "이벤트 발생 환경", example = "local")
        @NotBlank String environment,

        @Schema(description = "이벤트 종류별 추가 속성", example = "{\"position\": 1}")
        @NotNull JsonNode properties,

        @Schema(description = "0.3.0-draft부터 필수인 Storefront tenant 식별자", example = "estee-lauder", nullable = true)
        @Pattern(regexp = "^[a-z0-9]+(-[a-z0-9]+)*$") String tenantId
) {
    /** 0.2.0 호출부와 호환되는 생성자다. */
    public ActivityEvent(
            String schemaVersion, String eventId, String eventName, String intent, Instant occurredAt,
            String personaId, String sessionId, String pageViewId, Integer sequenceNo, String pageType,
            String productId, String actorType, String environment, JsonNode properties
    ) {
        this(schemaVersion, eventId, eventName, intent, occurredAt, personaId, sessionId, pageViewId,
                sequenceNo, pageType, productId, actorType, environment, properties, null);
    }
}
