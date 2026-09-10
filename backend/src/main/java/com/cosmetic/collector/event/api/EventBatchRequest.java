package com.cosmetic.collector.event.api;

import com.cosmetic.collector.event.api.validation.ValidEventBatchContract;
import io.swagger.v3.oas.annotations.media.ArraySchema;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import tools.jackson.databind.PropertyNamingStrategies;
import tools.jackson.databind.annotation.JsonNaming;

import java.util.List;

@Schema(description = "활동 이벤트 배치 요청")
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
@ValidEventBatchContract
public record EventBatchRequest(
        @Schema(description = "배치 전송 계약 버전", example = "0.2.0-draft")
        @NotBlank @Pattern(regexp = "^0\\.2\\.0-draft$") String schemaVersion,

        @ArraySchema(
                arraySchema = @Schema(description = "한 요청에 담긴 이벤트 목록", maxLength = 100),
                schema = @Schema(implementation = ActivityEvent.class)
        )
        @NotEmpty @Size(max = 100) List<@Valid ActivityEvent> events
) {
}
