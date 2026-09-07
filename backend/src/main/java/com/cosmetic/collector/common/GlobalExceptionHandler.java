package com.cosmetic.collector.common;

import com.cosmetic.collector.event.application.EventPublishException;
import com.cosmetic.collector.event.application.EventPublishOverloadedException;
import com.cosmetic.collector.event.api.validation.InvalidEventBatchException;
import com.cosmetic.collector.event.api.validation.EventBatchTooLargeException;
import com.cosmetic.collector.event.observability.CollectorMetrics;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.List;

@RestControllerAdvice
public class GlobalExceptionHandler {

    private final CollectorMetrics metrics;

    public GlobalExceptionHandler(CollectorMetrics metrics) {
        this.metrics = metrics;
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ErrorResponse> handleValidation(MethodArgumentNotValidException exception) {
        List<ErrorResponse.FieldErrorDetail> details = exception.getBindingResult()
                .getFieldErrors()
                .stream()
                .map(error -> new ErrorResponse.FieldErrorDetail(
                        error.getField(),
                        error.getDefaultMessage()
                ))
                .toList();

        if (details.stream().anyMatch(detail -> detail.field().equals("events")
                && exception.getBindingResult().getFieldErrors().stream()
                .anyMatch(error -> error.getField().equals("events") && error.getCode().equals("Size")))) {
            metrics.recordValidationRejected("event_batch_too_large");
            return ResponseEntity.status(HttpStatus.PAYLOAD_TOO_LARGE).body(new ErrorResponse(
                    "EVENT_BATCH_TOO_LARGE",
                    "한 요청에는 이벤트를 최대 100건까지 담을 수 있습니다.",
                    details
            ));
        }

        metrics.recordValidationRejected("invalid_event_batch");
        return ResponseEntity.badRequest().body(new ErrorResponse(
                "INVALID_EVENT_BATCH",
                "이벤트 요청 형식이 올바르지 않습니다.",
                details
        ));
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ErrorResponse> handleUnreadable(HttpMessageNotReadableException exception) {
        metrics.recordValidationRejected("malformed_json");
        return ResponseEntity.badRequest().body(new ErrorResponse(
                "MALFORMED_JSON",
                "JSON 형식 또는 시간 값이 올바르지 않습니다.",
                List.of()
        ));
    }

    @ExceptionHandler(InvalidEventBatchException.class)
    public ResponseEntity<ErrorResponse> handleInvalidBatch(InvalidEventBatchException exception) {
        return ResponseEntity.badRequest().body(new ErrorResponse(
                "INVALID_EVENT_BATCH",
                "이벤트 배치 형식이 올바르지 않습니다.",
                List.of()
        ));
    }

    @ExceptionHandler(EventBatchTooLargeException.class)
    public ResponseEntity<ErrorResponse> handleBatchTooLarge(EventBatchTooLargeException exception) {
        return ResponseEntity.status(HttpStatus.PAYLOAD_TOO_LARGE).body(new ErrorResponse(
                "EVENT_BATCH_TOO_LARGE",
                "한 요청에는 이벤트를 최대 100건까지 담을 수 있습니다.",
                List.of()
        ));
    }

    @ExceptionHandler(EventPublishException.class)
    public ResponseEntity<ErrorResponse> handlePublishFailure(EventPublishException exception) {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body(new ErrorResponse(
                "KAFKA_UNAVAILABLE",
                "이벤트 수집 시스템을 일시적으로 사용할 수 없습니다.",
                List.of()
        ));
    }

    @ExceptionHandler(EventPublishOverloadedException.class)
    public ResponseEntity<ErrorResponse> handlePublishOverloaded(EventPublishOverloadedException exception) {
        return ResponseEntity.status(HttpStatus.TOO_MANY_REQUESTS)
                .header("Retry-After", "1")
                .body(new ErrorResponse(
                        "INGESTION_OVERLOADED",
                        "이벤트 수집 요청이 많습니다. 잠시 후 재시도해 주세요.",
                        List.of()
                ));
    }
}
