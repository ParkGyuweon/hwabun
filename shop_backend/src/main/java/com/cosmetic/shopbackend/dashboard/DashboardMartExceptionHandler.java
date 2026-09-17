package com.cosmetic.shopbackend.dashboard;

import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class DashboardMartExceptionHandler {
  @ExceptionHandler(DashboardMartUnavailableException.class)
  @ResponseStatus(HttpStatus.SERVICE_UNAVAILABLE)
  public Map<String, String> unavailable(DashboardMartUnavailableException exception) {
    return Map.of("error", "mart_unavailable", "mart", exception.mart());
  }
}
