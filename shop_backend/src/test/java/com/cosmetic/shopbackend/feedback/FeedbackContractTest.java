package com.cosmetic.shopbackend.feedback;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.web.server.ResponseStatusException;

class FeedbackContractTest {

  @Test
  void acceptsOnlyTheFiveContractAxesAndNormalizesCase() {
    assertEquals(
      "efficacy",
      FeedbackController.normalizeAxisValue(" EFFICACY ")
    );
    assertEquals("texture", FeedbackController.normalizeAxisValue("texture"));
    assertEquals("scent", FeedbackController.normalizeAxisValue("scent"));
    assertEquals(
      "packaging",
      FeedbackController.normalizeAxisValue("packaging")
    );
    assertEquals("value", FeedbackController.normalizeAxisValue("value"));
  }

  @Test
  void rejectsOtherAndUnknownAxes() {
    assertThrows(ResponseStatusException.class, () ->
      FeedbackController.normalizeAxisValue("other")
    );
    assertThrows(ResponseStatusException.class, () ->
      FeedbackController.normalizeAxisValue("")
    );
  }
}
