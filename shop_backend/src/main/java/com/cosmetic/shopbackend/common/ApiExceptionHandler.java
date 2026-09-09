package com.cosmetic.shopbackend.common;

import java.util.Map;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {

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
}
