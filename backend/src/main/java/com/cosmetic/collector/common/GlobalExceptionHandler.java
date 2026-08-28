package com.cosmetic.collector.common;

import com.cosmetic.collector.event.application.EventPublishException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.List;

@RestControllerAdvice
public class GlobalExceptionHandler {

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

        return ResponseEntity.badRequest().body(new ErrorResponse(
                "INVALID_EVENT_BATCH",
                "이벤트 요청 형식이 올바르지 않습니다.",
                details
        ));
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ErrorResponse> handleUnreadable(HttpMessageNotReadableException exception) {
        return ResponseEntity.badRequest().body(new ErrorResponse(
                "MALFORMED_JSON",
                "JSON 형식 또는 시간 값이 올바르지 않습니다.",
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
}
