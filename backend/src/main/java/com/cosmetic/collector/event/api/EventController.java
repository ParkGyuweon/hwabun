package com.cosmetic.collector.event.api;

import com.cosmetic.collector.common.ErrorResponse;
import com.cosmetic.collector.event.application.EventPublisher;
import com.cosmetic.collector.event.application.PublishSummary;
import com.cosmetic.collector.event.application.RejectedEvent;
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

import java.util.List;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;

@RestController
@RequestMapping("/api/events")
@RequiredArgsConstructor
@Slf4j
@Tag(name = "Activity Events", description = "프론트엔드 활동 로그 수집 API")
public class EventController {

    private final EventPublisher eventPublisher;
    private final CollectorMetrics metrics;
    private final EventBatchSemanticValidator semanticValidator;

    @PostMapping
    @Operation(
            summary = "활동 로그 배치 수집",
            description = "최대 100개의 활동 이벤트를 검증합니다. 영구 계약 위반 이벤트는 제외하고, 정상 이벤트의 Kafka ACK를 모두 확인한 후 202를 반환합니다."
    )
    @ApiResponses({
            @ApiResponse(
                    responseCode = "202",
                    description = "정상 이벤트를 Kafka에 발행함. 계약 위반 이벤트는 rejections에 표시됨",
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
            metrics.recordValidationRejected("event_batch_too_large");
            throw new EventBatchTooLargeException();
        }

        EventBatchSemanticValidator.ValidationResult validation = semanticValidator.validate(request);
        if (validation.invalidBatch()) {
            metrics.recordValidationRejected("invalid_event_batch");
            throw new InvalidEventBatchException();
        }
        if (validation.rejectedCount() > 0) {
            metrics.recordEventRejected(validation.rejectedCount());
            validation.rejectedEvents().forEach(rejectedEvent -> {
                String code = rejectedEvent.violations().getFirst().code();
                metrics.recordValidationRejected(code);
                log.info("이벤트를 계약 위반으로 제외했습니다. requestId={}, eventIndex={}, eventId={}, code={}",
                        requestId, rejectedEvent.eventIndex(), eventIdOf(rejectedEvent), code);
            });
        }
        if (validation.acceptedEvents().isEmpty()) {
            return CompletableFuture.completedFuture(
                    accepted(requestId, new PublishSummary(0), validation.rejectedEvents())
            );
        }

        return eventPublisher.publish(requestId, validation.acceptedEvents())
                .thenApply(summary -> accepted(requestId, summary, validation.rejectedEvents()));
    }

    private ResponseEntity<EventAcceptedResponse> accepted(
            String requestId,
            PublishSummary summary,
            List<RejectedEvent> rejectedEvents
    ) {
        EventAcceptedResponse body = new EventAcceptedResponse(
                requestId,
                summary.publishedCount(),
                rejectedEvents.size(),
                rejectedEvents.stream()
                        .map(rejectedEvent -> new EventRejectionResponse(
                                rejectedEvent.eventIndex(),
                                eventIdOf(rejectedEvent),
                                rejectedEvent.violations().getFirst().code()
                        ))
                        .toList()
        );

        return ResponseEntity.accepted()
                .header("X-Request-Id", requestId)
                .body(body);
    }

    private String eventIdOf(RejectedEvent rejectedEvent) {
        return rejectedEvent.event() == null ? null : rejectedEvent.event().eventId();
    }
}
