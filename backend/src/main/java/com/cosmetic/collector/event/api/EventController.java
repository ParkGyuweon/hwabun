package com.cosmetic.collector.event.api;

import com.cosmetic.collector.common.ErrorResponse;
import com.cosmetic.collector.event.application.EventPublisher;
import com.cosmetic.collector.event.application.PublishSummary;
import com.cosmetic.collector.event.observability.CollectorMetrics;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.UUID;
import java.util.concurrent.CompletableFuture;

@RestController
@RequestMapping("/api/events")
@RequiredArgsConstructor
@Tag(name = "Activity Events", description = "프론트엔드 활동 로그 수집 API")
public class EventController {

    private final EventPublisher eventPublisher;
    private final CollectorMetrics metrics;

    @PostMapping
    @Operation(
            summary = "활동 로그 배치 수집",
            description = "최대 100개의 활동 이벤트를 검증하고 Kafka에 비동기로 발행합니다. 모든 Kafka ACK를 확인한 후 202를 반환합니다."
    )
    @ApiResponses({
            @ApiResponse(
                    responseCode = "202",
                    description = "모든 이벤트를 Kafka에 발행함",
                    content = @Content(schema = @Schema(implementation = EventAcceptedResponse.class))
            ),
            @ApiResponse(
                    responseCode = "400",
                    description = "JSON 또는 이벤트 필수값이 올바르지 않음",
                    content = @Content(schema = @Schema(implementation = ErrorResponse.class))
            ),
            @ApiResponse(
                    responseCode = "503",
                    description = "Kafka에 이벤트를 발행하지 못함",
                    content = @Content(schema = @Schema(implementation = ErrorResponse.class))
            )
    })
    public CompletableFuture<ResponseEntity<EventAcceptedResponse>> collect(
            @Valid @RequestBody EventBatchRequest request
    ) {
        String requestId = UUID.randomUUID().toString();
        metrics.recordReceived(request.events().size());

        return eventPublisher.publish(requestId, request)
                .thenApply(summary -> accepted(requestId, summary));
    }

    private ResponseEntity<EventAcceptedResponse> accepted(String requestId, PublishSummary summary) {
        EventAcceptedResponse body = new EventAcceptedResponse(
                requestId,
                summary.publishedCount(),
                0
        );

        return ResponseEntity.accepted()
                .header("X-Request-Id", requestId)
                .body(body);
    }
}
