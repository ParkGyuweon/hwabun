package com.cosmetic.collector.event.api;

import io.swagger.v3.oas.annotations.media.Schema;
import tools.jackson.databind.PropertyNamingStrategies;
import tools.jackson.databind.annotation.JsonNaming;

@Schema(description = "활동 로그 수집 성공 응답")
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record EventAcceptedResponse(
        @Schema(description = "요청 추적 ID", example = "f7fe6c0c-8b04-4b03-85bb-09a13fae0e11")
        String requestId,

        @Schema(description = "Kafka 발행에 성공한 이벤트 수", example = "2")
        int accepted,

        @Schema(description = "의미 계약 위반으로 폐기된 이벤트 수. 프론트 재전송 대상이 아니다", example = "1")
        int rejected
) {
}
