package com.cosmetic.collector.event.api;

import io.swagger.v3.oas.annotations.media.Schema;
import tools.jackson.databind.PropertyNamingStrategies;
import tools.jackson.databind.annotation.JsonNaming;

@Schema(description = "부분 수락 배치에서 제외된 이벤트의 요약")
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record EventRejectionResponse(
        @Schema(description = "원래 events 배열의 0부터 시작하는 위치", example = "3")
        int eventIndex,

        @Schema(description = "이벤트 식별자. 식별자 자체가 누락된 경우 null", example = "evt-003", nullable = true)
        String eventId,

        @Schema(description = "프론트가 재전송하지 않아야 하는 영구 검증 오류 코드", example = "missing_required_property")
        String code
) {
}
