package com.cosmetic.collector.event.api;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

import java.time.Instant;
import java.util.Collections;
import java.util.List;
import java.util.Set;

import static org.assertj.core.api.Assertions.assertThat;

class EventValidationTest {

    private static final ObjectMapper objectMapper = new ObjectMapper();
    private static Validator validator;

    @BeforeAll
    static void createValidator() {
        validator = Validation.buildDefaultValidatorFactory().getValidator();
    }

    @Test
    void acceptsAValidEventBatch() {
        EventBatchRequest request = new EventBatchRequest("0.2.0-draft", List.of(validEvent()));

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
                "",
                "product_click",
                "",
                Instant.parse("2026-08-27T14:30:00Z"),
                null,
                "",
                "",
                null,
                "",
                null,
                "",
                "",
                objectMapper.createObjectNode()
        );
        EventBatchRequest request = new EventBatchRequest("draft", List.of(invalidEvent));

        Set<ConstraintViolation<EventBatchRequest>> violations = validator.validate(request);

        assertThat(violations)
                .extracting(violation -> violation.getPropertyPath().toString())
                .contains(
                        "events[0].schemaVersion",
                        "events[0].eventId",
                        "events[0].intent",
                        "events[0].sessionId",
                        "events[0].pageViewId",
                        "events[0].sequenceNo",
                        "events[0].pageType",
                        "events[0].actorType",
                        "events[0].environment"
                );
    }

    @Test
    void rejectsAnEmptySchemaVersionAndEmptyEventList() {
        EventBatchRequest request = new EventBatchRequest("", List.of());

        Set<ConstraintViolation<EventBatchRequest>> violations = validator.validate(request);

        assertThat(violations)
                .extracting(violation -> violation.getPropertyPath().toString())
                .contains("schemaVersion", "events");
    }

    @Test
    void rejectsValuesOutsideTheFrontendContract() {
        ActivityEvent invalidEvent = new ActivityEvent(
                "0.2.0-draft",
                "evt-001",
                "product.click",
                "unknown",
                Instant.parse("2026-08-27T14:30:00Z"),
                null,
                "session-001",
                "page-view-001",
                0,
                "home",
                "product-001",
                "bot",
                "local",
                objectMapper.createObjectNode()
        );

        Set<ConstraintViolation<ActivityEvent>> violations = validator.validate(invalidEvent);

        assertThat(violations)
                .extracting(violation -> violation.getPropertyPath().toString())
                .contains("eventName", "intent", "sequenceNo", "pageType", "actorType");
    }

    @Test
    void rejectsPropertiesThatAreNotJsonObjects() {
        ActivityEvent invalidEvent = new ActivityEvent(
                "0.2.0-draft", "evt-001", "product_click", "comparison",
                Instant.parse("2026-08-27T14:30:00Z"), null, "session-001", "page-view-001", 1,
                "product_list", "product-001", "user", "local", objectMapper.createArrayNode()
        );

        Set<ConstraintViolation<ActivityEvent>> violations = validator.validate(invalidEvent);

        assertThat(violations)
                .extracting(violation -> violation.getPropertyPath().toString())
                .contains("properties");
    }

    @Test
    void rejectsAnEventWithADifferentSchemaVersion() {
        ActivityEvent mismatchedVersion = new ActivityEvent(
                "0.1.0-draft", "evt-001", "product_click", "comparison",
                Instant.parse("2026-08-27T14:30:00Z"), null, "session-001", "page-view-001", 1,
                "product_list", "product-001", "user", "local", objectMapper.createObjectNode()
        );
        EventBatchRequest request = new EventBatchRequest("0.2.0-draft", List.of(mismatchedVersion));

        Set<ConstraintViolation<EventBatchRequest>> violations = validator.validate(request);

        assertThat(violations)
                .extracting(violation -> violation.getPropertyPath().toString())
                .contains("events.schemaVersion");
    }

    @Test
    void allowsDuplicateEventIdsWithinABatch() {
        ActivityEvent duplicateId = new ActivityEvent(
                "0.2.0-draft", "evt-001", "product_click", "comparison",
                Instant.parse("2026-08-27T14:30:00Z"), null, "session-001", "page-view-001", 2,
                "product_list", "product-001", "user", "local", objectMapper.createObjectNode()
        );
        EventBatchRequest request = new EventBatchRequest("0.2.0-draft", List.of(validEvent(), duplicateId));

        Set<ConstraintViolation<EventBatchRequest>> violations = validator.validate(request);

        assertThat(violations).isEmpty();
    }

    @Test
    void requiresSyntheticRuntimeMetadata() {
        ActivityEvent invalidEvent = new ActivityEvent(
                "0.2.0-draft", "evt-001", "product_click", "comparison",
                Instant.parse("2026-08-27T14:30:00Z"), "persona-001", "session-001", "page-view-001", 1,
                "product_list", "product-001", "synthetic", "simulation", objectMapper.createObjectNode()
        );

        Set<ConstraintViolation<ActivityEvent>> violations = validator.validate(invalidEvent);

        assertThat(violations)
                .extracting(violation -> violation.getPropertyPath().toString())
                .contains("properties");
    }

    private ActivityEvent validEvent() {
        return new ActivityEvent(
                "0.2.0-draft",
                "evt-001",
                "product_click",
                "comparison",
                Instant.parse("2026-08-27T14:30:00Z"),
                null,
                "session-001",
                "page-view-001",
                1,
                "product_list",
                "product-001",
                "user",
                "local",
                objectMapper.createObjectNode()
        );
    }
}
