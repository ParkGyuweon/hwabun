package com.cosmetic.collector.event.api.validation;

import com.cosmetic.collector.event.api.ActivityEvent;
import com.cosmetic.collector.event.api.EventBatchRequest;
import com.cosmetic.collector.event.application.IndexedActivityEvent;
import com.cosmetic.collector.event.application.RejectedEvent;
import com.cosmetic.collector.event.application.ValidationViolation;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** 요청 envelope 오류와 이벤트별 폐기 대상을 분리한다. */
@Component
public class EventBatchSemanticValidator {

    private static final Map<String, Integer> REJECTION_CODE_PRIORITIES = Map.ofEntries(
            Map.entry("null_event", 1),
            Map.entry("schema_version_mismatch", 2),
            Map.entry("unregistered_event", 3),
            Map.entry("event_intent_mismatch", 4),
            Map.entry("missing_required_property", 5),
            Map.entry("invalid_property_type", 6),
            Map.entry("invalid_property_enum", 7),
            Map.entry("collector_validation_failure", 8)
    );
    private static final Comparator<ValidationViolation> REJECTION_PRIORITY = Comparator
            .comparingInt((ValidationViolation violation) -> REJECTION_CODE_PRIORITIES
                    .getOrDefault(violation.code(), Integer.MAX_VALUE))
            .thenComparing(ValidationViolation::code)
            .thenComparing(ValidationViolation::field)
            .thenComparing(ValidationViolation::message);

    private final Validator validator;

    public EventBatchSemanticValidator(Validator validator) {
        this.validator = validator;
    }

    public ValidationResult validate(EventBatchRequest request) {
        if (request.events() == null || request.events().isEmpty() || request.events().size() > 100
                || !validator.validateValue(EventBatchRequest.class, "schemaVersion", request.schemaVersion()).isEmpty()) {
            return ValidationResult.invalidEnvelope();
        }

        List<IndexedActivityEvent> accepted = new ArrayList<>();
        List<RejectedEvent> rejected = new ArrayList<>();
        for (int index = 0; index < request.events().size(); index++) {
            ActivityEvent event = request.events().get(index);
            List<ValidationViolation> violations = violationsFor(request.schemaVersion(), event);
            if (!violations.isEmpty()) {
                rejected.add(new RejectedEvent(event, index, violations));
                continue;
            }
            accepted.add(new IndexedActivityEvent(event, index));
        }
        return new ValidationResult(accepted, rejected, false);
    }

    private List<ValidationViolation> violationsFor(String schemaVersion, ActivityEvent event) {
        if (event == null) {
            return List.of(new ValidationViolation("null_event", "events", "이벤트는 null일 수 없습니다."));
        }
        if (!schemaVersion.equals(event.schemaVersion())) {
            return List.of(new ValidationViolation(
                    "schema_version_mismatch",
                    "schema_version",
                    "배치와 이벤트의 schema_version이 일치해야 합니다."
            ));
        }
        Set<ConstraintViolation<ActivityEvent>> violations = validator.validate(event);
        return violations.stream()
                .map(violation -> toValidationViolation(violation))
                .sorted(REJECTION_PRIORITY)
                .toList();
    }

    private ValidationViolation toValidationViolation(ConstraintViolation<ActivityEvent> violation) {
        String message = violation.getMessage();
        int separator = message.indexOf('|');
        if (separator > 0) {
            return new ValidationViolation(
                    message.substring(0, separator),
                    violation.getPropertyPath().toString(),
                    message.substring(separator + 1)
            );
        }
        return new ValidationViolation("collector_validation_failure", violation.getPropertyPath().toString(), message);
    }

    public record ValidationResult(
            List<IndexedActivityEvent> acceptedEvents,
            List<RejectedEvent> rejectedEvents,
            boolean invalidBatch
    ) {
        public int rejectedCount() {
            return rejectedEvents.size();
        }

        static ValidationResult invalidEnvelope() {
            return new ValidationResult(List.of(), List.of(), true);
        }
    }
}
