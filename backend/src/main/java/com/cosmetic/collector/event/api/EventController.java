package com.cosmetic.collector.event.api;

import com.cosmetic.collector.common.ErrorResponse;
import com.cosmetic.collector.event.application.EventPublisher;
import com.cosmetic.collector.event.application.PublishSummary;
import com.cosmetic.collector.event.application.RejectedEventPublisher;
import com.cosmetic.collector.event.api.validation.EventBatchSemanticValidator;
import com.cosmetic.collector.event.api.validation.InvalidEventBatchException;
import com.cosmetic.collector.event.api.validation.EventBatchTooLargeException;
import com.cosmetic.collector.event.observability.CollectorMetrics;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
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
@Slf4j
@Tag(name = "Activity Events", description = "프론트엔드 활동 로그 수집 API")
public class EventController {

    private final EventPublisher eventPublisher;
    private final RejectedEventPublisher rejectedEventPublisher;
    private final CollectorMetrics metrics;
    private final EventBatchSemanticValidator semanticValidator;

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
                    responseCode = "413",
                    description = "요청 본문 또는 이벤트 수가 서버 상한을 초과함",
                    content = @Content(schema = @Schema(implementation = ErrorResponse.class))
            ),
            @ApiResponse(
                    responseCode = "429",
                    description = "Kafka 발행 작업 대기열이 포화됨. Retry-After 이후 재시도 필요",
                    content = @Content(schema = @Schema(implementation = ErrorResponse.class))
            ),
            @ApiResponse(
                    responseCode = "503",
                    description = "Kafka에 이벤트를 발행하지 못함",
                    content = @Content(schema = @Schema(implementation = ErrorResponse.class))
            )
    })
    public CompletableFuture<ResponseEntity<EventAcceptedResponse>> collect(
            @RequestBody EventBatchRequest request
    ) {
        String requestId = UUID.randomUUID().toString();
        int receivedCount = request.events() == null ? 0 : request.events().size();
        metrics.recordReceived(receivedCount);
        if (request.events() != null && request.events().size() > 100) {
            metrics.recordValidationFailure("event_batch_too_large");
            throw new EventBatchTooLargeException();
        }

        EventBatchSemanticValidator.ValidationResult validation = semanticValidator.validate(request);
        if (validation.invalidBatch()) {
            metrics.recordValidationFailure("invalid_event_batch");
            throw new InvalidEventBatchException();
        }
        if (validation.rejectedCount() > 0) {
            metrics.recordValidationFailure("invalid_event_contract", validation.rejectedCount());
            publishRejectedEvents(requestId, validation.rejectedEvents());
        }
        if (validation.acceptedEvents().isEmpty()) {
            return CompletableFuture.supplyAsync(
                    () -> accepted(requestId, new PublishSummary(0), validation.rejectedCount())
            );
        }

        return eventPublisher.publish(requestId, validation.acceptedEvents())
                .thenApply(summary -> accepted(requestId, summary, validation.rejectedCount()));
    }

    private void publishRejectedEvents(String requestId, java.util.List<com.cosmetic.collector.event.application.RejectedEvent> rejectedEvents) {
        try {
            rejectedEventPublisher.publish(requestId, rejectedEvents)
                    .exceptionally(exception -> {
                        metrics.recordValidationFailure("rejected_event_publish_failure", rejectedEvents.size());
                        log.error("거부 이벤트 보존에 실패했습니다. requestId={}, rejectedCount={}",
                                requestId, rejectedEvents.size(), exception);
                        return null;
                    });
        } catch (RuntimeException exception) {
            metrics.recordValidationFailure("rejected_event_publish_failure", rejectedEvents.size());
            log.error("거부 이벤트 보존을 시작하지 못했습니다. requestId={}, rejectedCount={}",
                    requestId, rejectedEvents.size(), exception);
        }
    }

    private ResponseEntity<EventAcceptedResponse> accepted(String requestId, PublishSummary summary, int rejectedCount) {
        EventAcceptedResponse body = new EventAcceptedResponse(
                requestId,
                summary.publishedCount(),
                rejectedCount
        );

        return ResponseEntity.accepted()
                .header("X-Request-Id", requestId)
                .body(body);
    }
}
