package com.cosmetic.shopbackend.common;

import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import java.util.regex.Pattern;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ResponseStatusException;

@RestControllerAdvice
public class ApiExceptionHandler {

  /** "bad_range" 처럼 이미 코드 모양인 reason 은 그대로 error 코드로 쓴다. */
  private static final Pattern CODE_LIKE = Pattern.compile("[a-z][a-z0-9_]*");

  @ExceptionHandler(DataIntegrityViolationException.class)
  @ResponseStatus(HttpStatus.CONFLICT)
  public Map<String, Object> handleConstraint(
    DataIntegrityViolationException exception
  ) {
    return Map.of(
      "error",
      "conflict",
      "message",
      "요청이 현재 데이터 상태와 충돌했습니다."
    );
  }

  /**
   * ResponseStatusException 의 reason 을 본문에 싣는다. 기본 설정(server.error.include-message=never)
   * 에서는 /error 로 넘어가며 reason 이 사라져, 프론트가 어떤 거절인지 가를 수 없었다.
   */
  @ExceptionHandler(ResponseStatusException.class)
  public ResponseEntity<Map<String, Object>> handleResponseStatus(
    ResponseStatusException exception
  ) {
    HttpStatusCode status = exception.getStatusCode();
    String reason = exception.getReason();
    Map<String, Object> body = new LinkedHashMap<>();
    body.put("error", errorCode(status, reason));
    body.put("message", reason != null ? reason : defaultMessage(status));
    return ResponseEntity
      .status(status)
      .headers(exception.getHeaders())
      .body(body);
  }

  static String errorCode(HttpStatusCode status, String reason) {
    if (reason != null && CODE_LIKE.matcher(reason).matches()) {
      return reason;
    }
    HttpStatus resolved = HttpStatus.resolve(status.value());
    return resolved != null
      ? resolved.name().toLowerCase(Locale.ROOT)
      : "http_" + status.value();
  }

  private static String defaultMessage(HttpStatusCode status) {
    HttpStatus resolved = HttpStatus.resolve(status.value());
    return resolved != null ? resolved.getReasonPhrase() : "HTTP " + status.value();
  }
}
