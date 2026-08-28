package com.cosmetic.collector.event.api;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.Collections;
import java.util.List;
import java.util.Set;

import static org.assertj.core.api.Assertions.assertThat;

class EventValidationTest {

    private static Validator validator;

    @BeforeAll
    static void createValidator() {
        validator = Validation.buildDefaultValidatorFactory().getValidator();
    }

    @Test
    void acceptsAValidEventBatch() {
        EventBatchRequest request = new EventBatchRequest("draft", List.of(validEvent()));

        Set<ConstraintViolation<EventBatchRequest>> violations = validator.validate(request);

        assertThat(violations).isEmpty();
    }

    @Test
    void rejectsMoreThanOneHundredEvents() {
        EventBatchRequest request = new EventBatchRequest(
                "draft",
                Collections.nCopies(101, validEvent())
        );

        Set<ConstraintViolation<EventBatchRequest>> violations = validator.validate(request);

        assertThat(violations)
                .extracting(violation -> violation.getPropertyPath().toString())
                .contains("events");
    }

    @Test
    void validatesRequiredFieldsInsideEachEvent() {
        ActivityEvent invalidEvent = new ActivityEvent(
                "",
                "product.click",
                Instant.parse("2026-08-27T14:30:00Z"),
                "persona-001",
                "",
                null,
                null
        );
        EventBatchRequest request = new EventBatchRequest("draft", List.of(invalidEvent));

        Set<ConstraintViolation<EventBatchRequest>> violations = validator.validate(request);

        assertThat(violations)
                .extracting(violation -> violation.getPropertyPath().toString())
                .contains("events[0].eventId", "events[0].sessionId");
    }

    @Test
    void rejectsAnEmptySchemaVersionAndEmptyEventList() {
        EventBatchRequest request = new EventBatchRequest("", List.of());

        Set<ConstraintViolation<EventBatchRequest>> violations = validator.validate(request);

        assertThat(violations)
                .extracting(violation -> violation.getPropertyPath().toString())
                .containsExactlyInAnyOrder("schemaVersion", "events");
    }

    private ActivityEvent validEvent() {
        return new ActivityEvent(
                "evt-001",
                "product.click",
                Instant.parse("2026-08-27T14:30:00Z"),
                "persona-001",
                "session-001",
                "product-001",
                null
        );
    }
}
