package com.cosmetic.collector.event.api.validation;

import com.cosmetic.collector.event.api.ActivityEvent;
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import tools.jackson.databind.JsonNode;

import java.util.Map;
import java.util.Set;

public class EventContractValidator implements ConstraintValidator<ValidEventContract, ActivityEvent> {

    private static final Map<String, String> EVENT_INTENTS = Map.ofEntries(
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
    private static final Set<String> GENERATOR_TYPES = Set.of("python_batch", "agent_llm");

    @Override
    public boolean isValid(ActivityEvent event, ConstraintValidatorContext context) {
        if (event == null) {
            return true;
        }

        boolean valid = true;
        context.disableDefaultConstraintViolation();

        JsonNode properties = event.properties();
        if (properties != null && !properties.isObject()) {
            valid = false;
            addViolation(context, "properties", "properties는 JSON object여야 합니다.");
        }

        String expectedIntent = EVENT_INTENTS.get(event.eventName());
        if (expectedIntent == null) {
            valid = false;
            addViolation(context, "eventName", "등록되지 않은 event_name입니다.");
        } else if (!expectedIntent.equals(event.intent())) {
            valid = false;
            addViolation(context, "intent", "event_name과 intent 조합이 올바르지 않습니다.");
        }

        if (properties != null && properties.isObject()) {
            valid &= validateEventProperties(context, event.eventName(), properties);
        }

        if ("synthetic".equals(event.actorType())) {
            if (isBlank(event.personaId())) {
                valid = false;
                addViolation(context, "personaId", "synthetic 이벤트에는 persona_id가 필요합니다.");
            }
            if (properties == null || !properties.isObject()) {
                return valid;
            }
            valid &= requireNonBlankProperty(context, properties, "scenario_id");
            valid &= requireNonBlankProperty(context, properties, "simulation_run_id");

            JsonNode generatorType = properties.get("generator_type");
            if (generatorType == null || !generatorType.isTextual()
                    || isBlank(generatorType.textValue())
                    || !GENERATOR_TYPES.contains(generatorType.textValue())) {
                valid = false;
                addViolation(context, "properties", "synthetic 이벤트의 generator_type이 올바르지 않습니다.");
            }
        }

        return valid;
    }

    private boolean validateEventProperties(
            ConstraintValidatorContext context,
            String eventName,
            JsonNode properties
    ) {
        return switch (eventName) {
            case "begin_checkout" -> requireItems(context, properties);
            case "purchase" -> requireNonBlankProperty(context, properties, "order_id")
                    & requireItems(context, properties);
            case "purchase_reason_select" -> requirePurchaseReasons(context, properties);
            default -> true;
        };
    }

    private boolean requireItems(ConstraintValidatorContext context, JsonNode properties) {
        JsonNode items = properties.get("items");
        if (items == null || !items.isArray() || items.isEmpty()) {
            addViolation(context, "properties", "items는 비어 있지 않은 배열이어야 합니다.");
            return false;
        }

        boolean valid = true;
        for (JsonNode item : items) {
            if (!item.isObject()
                    || !isNonBlankText(item.get("product_id"))
                    || !isPositiveInteger(item.get("quantity"))
                    || !isPositiveNumber(item.get("unit_price"))) {
                addViolation(context, "properties", "items 원소에는 product_id, 양수 quantity, 양수 unit_price가 필요합니다.");
                valid = false;
                break;
            }
        }
        return valid;
    }

    private boolean requirePurchaseReasons(ConstraintValidatorContext context, JsonNode properties) {
        if (!requireNonBlankProperty(context, properties, "order_id")) {
            return false;
        }

        JsonNode skipped = properties.get("skipped");
        if (skipped != null && !skipped.isBoolean()) {
            addViolation(context, "properties", "skipped는 boolean이어야 합니다.");
            return false;
        }

        JsonNode reasons = properties.get("reasons");
        boolean isSkipped = skipped != null && skipped.booleanValue();
        if (reasons == null || !reasons.isArray() || (!isSkipped && (reasons.isEmpty() || reasons.size() > 2))) {
            addViolation(context, "properties", "reasons는 건너뛰기가 아닐 때 1~2개의 배열이어야 합니다.");
            return false;
        }
        if (isSkipped && !reasons.isEmpty()) {
            addViolation(context, "properties", "건너뛴 설문에는 reasons가 비어 있어야 합니다.");
            return false;
        }

        for (JsonNode reason : reasons) {
            if (!reason.isTextual() || !PURCHASE_REASONS.contains(reason.textValue())) {
                addViolation(context, "properties", "reasons에 허용되지 않은 구매 이유가 있습니다.");
                return false;
            }
        }
        JsonNode primaryReason = properties.get("primary_reason");
        if (primaryReason != null && (!primaryReason.isTextual() || !containsText(reasons, primaryReason.textValue()))) {
            addViolation(context, "properties", "primary_reason은 reasons 중 하나여야 합니다.");
            return false;
        }
        return true;
    }

    private static final Set<String> PURCHASE_REASONS = Set.of(
            "ingredient", "skin_fit", "reviews", "review_same_skin", "price",
            "brand_trust", "texture_finish", "clean_claim", "recommendation", "restock"
    );

    private boolean isNonBlankText(JsonNode node) {
        return node != null && node.isTextual() && !isBlank(node.textValue());
    }

    private boolean isPositiveInteger(JsonNode node) {
        return node != null && node.isIntegralNumber() && node.longValue() > 0;
    }

    private boolean isPositiveNumber(JsonNode node) {
        return node != null && node.isNumber() && node.decimalValue().signum() > 0;
    }

    private boolean containsText(JsonNode nodes, String value) {
        for (JsonNode node : nodes) {
            if (node.isTextual() && value.equals(node.textValue())) {
                return true;
            }
        }
        return false;
    }

    private boolean requireNonBlankProperty(
            ConstraintValidatorContext context,
            JsonNode properties,
            String propertyName
    ) {
        JsonNode value = properties.get(propertyName);
        if (value != null && value.isTextual() && !isBlank(value.textValue())) {
            return true;
        }
        addViolation(context, "properties", "synthetic 이벤트에는 " + propertyName + "가 필요합니다.");
        return false;
    }

    private void addViolation(ConstraintValidatorContext context, String property, String message) {
        context.buildConstraintViolationWithTemplate(message)
                .addPropertyNode(property)
                .addConstraintViolation();
    }

    private boolean isBlank(String value) {
        return value == null || value.isBlank();
    }
}
