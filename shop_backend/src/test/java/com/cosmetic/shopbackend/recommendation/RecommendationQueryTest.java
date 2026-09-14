package com.cosmetic.shopbackend.recommendation;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.web.server.ResponseStatusException;

class RecommendationQueryTest {

  @Test
  void acceptsContractRangeAndAxes() {
    assertDoesNotThrow(() -> new RecommendationQuery(10, 2, 6, "concern,segment", "new_brand", "dry", "fair", null, null));
  }

  @Test
  void defaultsBlankAxesLikeTheRecommendationService() {
    assertEquals("concern,segment", new RecommendationQuery(10, 2, 0, "", null, null, null, null, null).axes());
    assertEquals("concern,segment", new RecommendationQuery(10, 2, 0, " , ", null, null, null, null, null).axes());
    assertEquals("top", new RecommendationQuery(10, 2, 0, "concern", "", null, null, null, null).hero());
  }

  @Test
  void rejectsOutOfRangeOrUnsupportedInputs() {
    assertThrows(ResponseStatusException.class, () -> new RecommendationQuery(51, 2, 0, "concern", "top", null, null, null, null));
    assertThrows(ResponseStatusException.class, () -> new RecommendationQuery(10, 2, 0, "not-an-axis", "top", null, null, null, null));
  }
}
