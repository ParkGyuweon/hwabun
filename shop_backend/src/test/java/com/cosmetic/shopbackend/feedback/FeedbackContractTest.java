package com.cosmetic.shopbackend.feedback;

import org.junit.jupiter.api.Test;
import org.springframework.web.server.ResponseStatusException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class FeedbackContractTest {
    @Test
    void acceptsOnlyTheFiveContractAxesAndNormalizesCase() {
        assertEquals("efficacy", FeedbackController.normalizeAxisValue(" EFFICACY "));
        assertEquals("texture", FeedbackController.normalizeAxisValue("texture"));
        assertEquals("scent", FeedbackController.normalizeAxisValue("scent"));
        assertEquals("packaging", FeedbackController.normalizeAxisValue("packaging"));
        assertEquals("value", FeedbackController.normalizeAxisValue("value"));
    }

    @Test
    void rejectsOtherAndUnknownAxes() {
        assertThrows(ResponseStatusException.class, () -> FeedbackController.normalizeAxisValue("other"));
        assertThrows(ResponseStatusException.class, () -> FeedbackController.normalizeAxisValue(""));
    }
}
