package com.cosmetic.collector.event.api.validation;

import com.cosmetic.collector.event.api.ActivityEvent;
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import tools.jackson.databind.JsonNode;

import java.util.Map;
import java.util.Set;

/** Collector가 소유한 공통 envelope 및 구매 이벤트의 위험 속성만 검사한다. */
public class EventContractValidator implements ConstraintValidator<ValidEventContract, ActivityEvent> {

    private static final Map<String, String> INTENTS = Map.ofEntries(
            Map.entry("session_start", "session"),
            Map.entry("page_view", "session"),
            Map.entry("navigation_click", "session"),
            Map.entry("exit_summary", "session"),
            Map.entry("product_impression", "exposure"),
            Map.entry("recommendation_impression", "exposure"),
            Map.entry("scroll_depth", "exposure"),
            Map.entry("impression_dwell", "exposure"),
            Map.entry("recommendation_snapshot", "exposure"),
            Map.entry("product_view", "interest"),
            Map.entry("section_view", "interest"),
            Map.entry("section_dwell", "interest"),
            Map.entry("scroll_pause", "interest"),
            Map.entry("media_view", "interest"),
            Map.entry("quick_look", "interest"),
            Map.entry("quick_look_close", "interest"),
            Map.entry("scroll_backtrack", "comparison"),
            Map.entry("variant_select", "comparison"),
            Map.entry("product_click", "comparison"),
            Map.entry("recommendation_click", "comparison"),
            Map.entry("filter_change", "comparison"),
            Map.entry("sort_change", "comparison"),
            Map.entry("accordion_toggle", "validation"),
            Map.entry("ingredient_view_mode_change", "validation"),
            Map.entry("review_expand", "validation"),
            Map.entry("review_filter_apply", "validation"),
            Map.entry("text_selection", "validation"),
            Map.entry("text_copy", "validation"),
            Map.entry("hover_dwell", "hesitation"),
            Map.entry("remove_from_cart", "hesitation"),
            Map.entry("wishlist_toggle", "conversion"),
            Map.entry("quantity_change", "conversion"),
            Map.entry("add_to_cart", "conversion"),
            Map.entry("view_cart", "conversion"),
            Map.entry("begin_checkout", "conversion"),
            Map.entry("purchase", "conversion"),
            Map.entry("purchase_reason_select", "validation"),
            Map.entry("rage_click", "friction"),
            Map.entry("dead_click", "friction")
    );
    private static final Set<String> PURCHASE_EVENTS = Set.of(
            "begin_checkout", "purchase", "purchase_reason_select"
    );
    private static final Set<String> PURCHASE_REASONS = Set.of(
            "ingredient", "skin_fit", "reviews", "review_same_skin", "price",
            "brand_trust", "texture_finish", "clean_claim", "recommendation", "restock"
    );

    @Override
    public boolean isValid(ActivityEvent event, ConstraintValidatorContext context) {
        if (event == null) {
            return true;
        }

        context.disableDefaultConstraintViolation();
        JsonNode properties = event.properties();
        boolean valid = validateEnvelope(event, context);
        if (properties == null || !properties.isObject()) {
            add(context, "invalid_property_type", "properties", "properties는 JSON object여야 합니다.");
            return false;
        }

        if (event.eventName() != null && PURCHASE_EVENTS.contains(event.eventName())) {
            valid &= validatePurchaseProperties(event, properties, context);
        }
        return valid;
    }

    private boolean validateEnvelope(ActivityEvent event, ConstraintValidatorContext context) {
        boolean valid = true;
        String eventName = event.eventName();
        if (blank(eventName)) {
            add(context, "missing_required_property", "eventName", "event_name이 필요합니다.");
            valid = false;
        } else {
            String expectedIntent = INTENTS.get(eventName);
            if (expectedIntent == null) {
                add(context, "unregistered_event", "eventName", "등록되지 않은 event_name입니다.");
                valid = false;
            } else if (!expectedIntent.equals(event.intent())) {
                add(context, "event_intent_mismatch", "intent", "event_name과 intent 조합이 올바르지 않습니다.");
                valid = false;
            }
        }
        if ("0.3.0-draft".equals(event.schemaVersion()) && blank(event.tenantId())) {
            add(context, "missing_required_property", "tenantId", "0.3.0-draft에는 tenant_id가 필요합니다.");
            valid = false;
        }
        return valid;
    }

    private boolean validatePurchaseProperties(
            ActivityEvent event,
            JsonNode properties,
            ConstraintValidatorContext context
    ) {
        return switch (event.eventName()) {
            case "begin_checkout" -> validateItems(properties, context);
            case "purchase" -> requireText(properties, "order_id", context)
                    & validateItems(properties, context);
            case "purchase_reason_select" -> requireText(properties, "order_id", context)
                    & validateReasons(properties, context);
            default -> true;
        };
    }

    private boolean validateItems(JsonNode properties, ConstraintValidatorContext context) {
        JsonNode items = properties.get("items");
        if (items == null || !items.isArray() || items.isEmpty()) {
            add(context, "missing_required_property", "properties", "items는 비어 있지 않은 배열이어야 합니다.");
            return false;
        }
        for (JsonNode item : items) {
            if (!item.isObject()
                    || !isText(item.get("product_id"))
                    || !isPositiveInteger(item.get("quantity"))
                    || !isPositiveNumber(item.get("unit_price"))) {
                add(context, "invalid_property_type", "properties", "items 원소 형식이 올바르지 않습니다.");
                return false;
            }
        }
        return true;
    }

    private boolean validateReasons(JsonNode properties, ConstraintValidatorContext context) {
        JsonNode skipped = properties.get("skipped");
        if (skipped != null && !skipped.isBoolean()) {
            add(context, "invalid_property_type", "properties", "skipped는 boolean이어야 합니다.");
            return false;
        }

        JsonNode reasons = properties.get("reasons");
        boolean isSkipped = skipped != null && skipped.booleanValue();
        if (reasons == null || !reasons.isArray()
                || (isSkipped ? !reasons.isEmpty() : reasons.isEmpty() || reasons.size() > 2)) {
            add(context, "invalid_property_type", "properties", "reasons 길이가 올바르지 않습니다.");
            return false;
        }
        for (JsonNode reason : reasons) {
            if (!reason.isTextual() || !PURCHASE_REASONS.contains(reason.textValue())) {
                add(context, "invalid_property_enum", "properties", "reasons 값이 계약 enum에 없습니다.");
                return false;
            }
        }

        JsonNode primaryReason = properties.get("primary_reason");
        if (primaryReason != null && (!primaryReason.isTextual() || !contains(reasons, primaryReason.textValue()))) {
            add(context, "invalid_property_enum", "properties", "primary_reason은 reasons 중 하나여야 합니다.");
            return false;
        }
        return true;
    }

    private boolean requireText(JsonNode properties, String field, ConstraintValidatorContext context) {
        if (isText(properties.get(field))) {
            return true;
        }
        add(context, "missing_required_property", "properties", field + "이 필요합니다.");
        return false;
    }

    private static boolean contains(JsonNode values, String value) {
        for (JsonNode candidate : values) {
            if (candidate.isTextual() && value.equals(candidate.textValue())) {
                return true;
            }
        }
        return false;
    }

    private static boolean isText(JsonNode value) {
        return value != null && value.isTextual() && !value.textValue().isBlank();
    }

    private static boolean isPositiveInteger(JsonNode value) {
        return value != null && value.isIntegralNumber() && value.longValue() > 0;
    }

    private static boolean isPositiveNumber(JsonNode value) {
        return value != null && value.isNumber() && value.decimalValue().signum() > 0;
    }

    private static boolean blank(String value) {
        return value == null || value.isBlank();
    }

    private static void add(
            ConstraintValidatorContext context,
            String code,
            String field,
            String message
    ) {
        context.buildConstraintViolationWithTemplate(code + "|" + message)
                .addPropertyNode(field)
                .addConstraintViolation();
    }
}
