package com.cosmetic.collector.event.api.validation;

import com.cosmetic.collector.event.api.ActivityEvent;
import com.cosmetic.collector.event.api.EventBatchRequest;
import jakarta.validation.Validator;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;

/** 요청 envelope 오류와 이벤트별 폐기 대상을 분리한다. */
@Component
public class EventBatchSemanticValidator {

    private final Validator validator;

    public EventBatchSemanticValidator(Validator validator) {
        this.validator = validator;
    }

    public ValidationResult validate(EventBatchRequest request) {
        if (request.events() == null || request.events().isEmpty() || request.events().size() > 100
                || !validator.validateValue(EventBatchRequest.class, "schemaVersion", request.schemaVersion()).isEmpty()) {
            return ValidationResult.invalidEnvelope();
        }

        List<ActivityEvent> accepted = new ArrayList<>();
        int rejected = 0;
        for (ActivityEvent event : request.events()) {
            if (event == null || !request.schemaVersion().equals(event.schemaVersion()) || hasViolations(event)) {
                rejected++;
            } else {
                accepted.add(event);
            }
        }
        return new ValidationResult(new EventBatchRequest(request.schemaVersion(), accepted), rejected, false);
    }

    private boolean hasViolations(ActivityEvent event) {
        return !validator.validate(event).isEmpty();
    }

    public record ValidationResult(EventBatchRequest acceptedRequest, int rejectedCount, boolean invalidBatch) {
        static ValidationResult invalidEnvelope() {
            return new ValidationResult(null, 0, true);
        }
    }
}
