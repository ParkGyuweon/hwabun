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
import java.util.Map;
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
    void requiresProductIdForProductTargetEvents() {
        Map<String, String> productTargetEvents = Map.ofEntries(
                Map.entry("product_view", "interest"),
                Map.entry("product_impression", "exposure"),
                Map.entry("product_click", "comparison"),
                Map.entry("accordion_toggle", "validation"),
                Map.entry("recommendation_impression", "exposure"),
                Map.entry("recommendation_click", "comparison"),
                Map.entry("wishlist_toggle", "conversion"),
                Map.entry("add_to_cart", "conversion"),
                Map.entry("scroll_depth", "exposure"),
                Map.entry("impression_dwell", "exposure"),
                Map.entry("media_view", "interest"),
                Map.entry("quick_look", "interest"),
                Map.entry("quick_look_close", "interest"),
                Map.entry("remove_from_cart", "hesitation"),
                Map.entry("variant_select", "comparison"),
                Map.entry("quantity_change", "conversion"),
                Map.entry("review_filter_apply", "validation"),
                Map.entry("review_expand", "validation"),
                Map.entry("ingredient_view_mode_change", "validation"),
                Map.entry("scroll_pause", "interest"),
                Map.entry("scroll_backtrack", "comparison"),
                Map.entry("text_selection", "validation"),
                Map.entry("text_copy", "validation"),
                Map.entry("hover_dwell", "hesitation")
        );

        for (Map.Entry<String, String> productTargetEvent : productTargetEvents.entrySet()) {
            ActivityEvent event = eventWithProductId(
                    productTargetEvent.getKey(), productTargetEvent.getValue(), "product_list", null
            );

            assertThat(validator.validate(event))
                    .as("%s should require product_id", productTargetEvent.getKey())
                    .extracting(violation -> violation.getPropertyPath().toString())
                    .contains("productId");
        }
    }

    @Test
    void requiresProductIdForProductDetailPageEvents() {
        List<ActivityEvent> events = List.of(
                eventWithProductId("page_view", "session", "product_detail", null),
                eventWithProductId("section_view", "interest", "product_detail", null),
                eventWithProductId("section_dwell", "interest", "product_detail", null)
        );

        for (ActivityEvent event : events) {
            assertThat(validator.validate(event))
                    .as("%s on product_detail should require product_id", event.eventName())
                    .extracting(violation -> violation.getPropertyPath().toString())
                    .contains("productId");
        }
    }

    @Test
    void allowsNullProductIdForPlatformAndProductListEvents() {
        List<ActivityEvent> events = List.of(
                eventWithProductId("page_view", "session", "product_list", null),
                eventWithProductId("section_view", "interest", "product_list", null),
                eventWithProductId("section_dwell", "interest", "product_list", null),
                eventWithProductId("page_view", "session", "cart", null)
        );

        for (ActivityEvent event : events) {
            assertThat(validator.validate(event))
                    .as("%s on %s should allow JSON null product_id", event.eventName(), event.pageType())
                    .isEmpty();
        }
    }

    @Test
    void rejectsBlankProductIdEvenWhenNullIsAllowed() {
        List<ActivityEvent> events = List.of(
                eventWithProductId("page_view", "session", "product_list", ""),
                eventWithProductId("section_view", "interest", "product_list", " "),
                eventWithProductId("section_dwell", "interest", "product_list", "")
        );

        for (ActivityEvent event : events) {
            assertThat(validator.validate(event))
                    .as("%s must use JSON null instead of a blank product_id", event.eventName())
                    .extracting(violation -> violation.getPropertyPath().toString())
                    .contains("productId");
        }
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
    void defersSyntheticRuntimeMetadataToTheDownstreamValidator() {
        ActivityEvent invalidEvent = new ActivityEvent(
                "0.2.0-draft", "evt-001", "product_click", "comparison",
                Instant.parse("2026-08-27T14:30:00Z"), "persona-001", "session-001", "page-view-001", 1,
                "product_list", "product-001", "synthetic", "simulation", objectMapper.createObjectNode()
        );

        Set<ConstraintViolation<ActivityEvent>> violations = validator.validate(invalidEvent);

        assertThat(violations).isEmpty();
    }

    @Test
    void rejectsInvalidPurchasePropertySemantics() throws Exception {
        ActivityEvent invalidPurchase = new ActivityEvent(
                "0.2.0-draft", "evt-purchase", "purchase", "conversion",
                Instant.parse("2026-08-27T14:30:00Z"), null, "session-001", "page-view-001", 1,
                "cart", null, "user", "local", objectMapper.readTree("""
                        {"order_id":"order-001","items":[{"product_id":"product-001","quantity":0,"unit_price":10}]}
                        """)
        );
        ActivityEvent invalidReasons = new ActivityEvent(
                "0.2.0-draft", "evt-reason", "purchase_reason_select", "validation",
                Instant.parse("2026-08-27T14:30:00Z"), null, "session-001", "page-view-001", 2,
                "cart", null, "user", "local", objectMapper.readTree("""
                        {"order_id":"order-001","reasons":["not_a_reason"]}
                        """)
        );

        assertThat(validator.validate(invalidPurchase))
                .extracting(violation -> violation.getPropertyPath().toString())
                .contains("properties");
        assertThat(validator.validate(invalidReasons))
                .extracting(violation -> violation.getPropertyPath().toString())
                .contains("properties");
    }

    @Test
    void permitsNewlyActivatedEventsWhenPurchasePropertiesMeetTheCollectorPolicy() {
        List<ActivityEvent> events = List.of(
                event("navigation_click", "session"),
                event("login", "session"),
                event("begin_checkout", "conversion"),
                event("purchase", "conversion"),
                event("purchase_reason_select", "validation")
        );

        for (ActivityEvent event : events) {
            assertThat(validator.validate(event))
                    .as("%s should be accepted by the Collector allow-list", event.eventName())
                    .isEmpty();
        }
    }

    @Test
    void validatesBannerPropertiesAndNewBrandNullValue() throws Exception {
        ActivityEvent newBrand = new ActivityEvent(
                "0.2.0-draft", "evt-banner", "banner_impression", "session",
                Instant.parse("2026-08-27T14:30:00Z"), null, "session-001", "page-view-001", 1,
                "product_list", "SB000004", "user", "local", objectMapper.readTree("""
                        {"banner_type":"new_brand","banner_value":null,"banner_slot":5,"trait_source":"session"}
                        """)
        );
        ActivityEvent invalidSlot = new ActivityEvent(
                "0.2.0-draft", "evt-banner-invalid", "banner_click", "interest",
                Instant.parse("2026-08-27T14:30:00Z"), null, "session-001", "page-view-001", 2,
                "product_list", "P001", "user", "local", objectMapper.readTree("""
                        {"banner_type":"concern","banner_value":"Anti-Aging","slot":1,"trait_source":"session"}
                        """)
        );

        assertThat(validator.validate(newBrand)).isEmpty();
        assertThat(validator.validate(invalidSlot))
                .extracting(violation -> violation.getPropertyPath().toString())
                .contains("properties");
    }

    private ActivityEvent event(String eventName, String intent) {
        var properties = objectMapper.createObjectNode();
        if ("begin_checkout".equals(eventName) || "purchase".equals(eventName)) {
            var item = properties.putArray("items").addObject();
            item.put("product_id", "product-001");
            item.put("quantity", 1);
            item.put("unit_price", 10);
        }
        if ("purchase".equals(eventName) || "purchase_reason_select".equals(eventName)) {
            properties.put("order_id", "order-001");
        }
        if ("purchase_reason_select".equals(eventName)) {
            properties.putArray("reasons").add("ingredient");
        }
        return new ActivityEvent(
                "0.2.0-draft", "evt-" + eventName, eventName, intent,
                Instant.parse("2026-08-27T14:30:00Z"), null, "session-001", "page-view-001", 1,
                "cart", null, "user", "local", properties
        );
    }

    private ActivityEvent eventWithProductId(
            String eventName,
            String intent,
            String pageType,
            String productId
    ) {
        return new ActivityEvent(
                "0.2.0-draft", "evt-" + eventName + "-" + pageType, eventName, intent,
                Instant.parse("2026-08-27T14:30:00Z"), null, "session-001", "page-view-001", 1,
                pageType, productId, "user", "local", objectMapper.createObjectNode()
        );
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
