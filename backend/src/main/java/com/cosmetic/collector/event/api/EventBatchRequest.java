package com.cosmetic.collector.event.api;

import io.swagger.v3.oas.annotations.media.ArraySchema;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Size;
import tools.jackson.databind.PropertyNamingStrategies;
import tools.jackson.databind.annotation.JsonNaming;

import java.util.List;

@Schema(description = "활동 이벤트 배치 요청")
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record EventBatchRequest(
        @Schema(description = "이벤트 계약 버전", example = "draft")
        @NotBlank String schemaVersion,

        @ArraySchema(
                arraySchema = @Schema(description = "한 요청에 담긴 이벤트 목록", maxLength = 100),
                schema = @Schema(implementation = ActivityEvent.class)
        )
        @NotEmpty @Size(max = 100) List<@Valid ActivityEvent> events
) {
}
