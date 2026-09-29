package com.cosmetic.shopbackend.settlement;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.time.LocalDate;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

class SettlementControllerTest {

  @Test
  void monthIsParsedToItsFirstDay() {
    assertEquals(LocalDate.of(2026, 9, 1), SettlementController.firstDayOf("2026-09"));
  }

  @Test
  void malformedMonthIsBadRequest() {
    for (String bad : new String[] { "2026-13", "2026/09", "september", "2026-09-01" }) {
      ResponseStatusException exception = assertThrows(
        ResponseStatusException.class,
        () -> SettlementController.firstDayOf(bad)
      );
      assertEquals(HttpStatus.BAD_REQUEST, exception.getStatusCode());
    }
  }
}
