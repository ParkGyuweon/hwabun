package com.cosmetic.shopbackend.common;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

class ApiExceptionHandlerTest {
  private final ApiExceptionHandler handler = new ApiExceptionHandler();

  @Test
  void sentenceReasonBecomesMessageAndStatusBecomesCode() {
    ResponseEntity<Map<String, Object>> response = handler.handleResponseStatus(
      new ResponseStatusException(HttpStatus.CONFLICT, "inactive or unavailable product")
    );

    assertEquals(HttpStatus.CONFLICT, response.getStatusCode());
    assertEquals("conflict", response.getBody().get("error"));
    assertEquals("inactive or unavailable product", response.getBody().get("message"));
  }

  @Test
  void codeLikeReasonIsUsedAsErrorCode() {
    ResponseEntity<Map<String, Object>> response = handler.handleResponseStatus(
      new ResponseStatusException(HttpStatus.BAD_REQUEST, "bad_range")
    );

    assertEquals(HttpStatus.BAD_REQUEST, response.getStatusCode());
    assertEquals("bad_range", response.getBody().get("error"));
    assertEquals("bad_range", response.getBody().get("message"));
  }

  @Test
  void missingReasonFallsBackToStatusPhrase() {
    ResponseEntity<Map<String, Object>> response = handler.handleResponseStatus(
      new ResponseStatusException(HttpStatus.NOT_FOUND)
    );

    assertEquals(HttpStatus.NOT_FOUND, response.getStatusCode());
    assertEquals("not_found", response.getBody().get("error"));
    assertEquals("Not Found", response.getBody().get("message"));
  }

  @Test
  void controllerExceptionIsWrittenDirectlyWithReason() throws Exception {
    MockMvc mvc = MockMvcBuilders
      .standaloneSetup(new ThrowingController())
      .setControllerAdvice(handler)
      .build();

    mvc
      .perform(get("/throw"))
      .andExpect(status().isForbidden())
      .andExpect(jsonPath("$.error").value("forbidden"))
      .andExpect(jsonPath("$.message").value("paid purchase required"));
  }

  @RestController
  static class ThrowingController {
    @GetMapping("/throw")
    String fail() {
      throw new ResponseStatusException(HttpStatus.FORBIDDEN, "paid purchase required");
    }
  }
}
