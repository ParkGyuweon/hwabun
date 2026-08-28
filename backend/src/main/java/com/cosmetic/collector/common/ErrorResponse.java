package com.cosmetic.collector.common;

import io.swagger.v3.oas.annotations.media.Schema;
import tools.jackson.databind.PropertyNamingStrategies;
import tools.jackson.databind.annotation.JsonNaming;

import java.util.List;

@Schema(description = "공통 API 오류 응답")
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record ErrorResponse(
        @Schema(description = "애플리케이션 오류 코드", example = "INVALID_EVENT_BATCH")
        String code,

        @Schema(description = "사용자에게 보여줄 오류 설명", example = "이벤트 요청 형식이 올바르지 않습니다.")
        String message,

        @Schema(description = "필드별 검증 오류")
        List<FieldErrorDetail> details
) {
    @Schema(description = "필드 검증 오류 상세")
    public record FieldErrorDetail(
            @Schema(example = "events[0].event_id") String field,
            @Schema(example = "공백일 수 없습니다") String reason
    ) {
    }
}
