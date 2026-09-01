package com.cosmetic.collector.event.api.validation;

import com.cosmetic.collector.event.api.EventBatchRequest;
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

import java.util.Objects;

public class EventBatchContractValidator implements ConstraintValidator<ValidEventBatchContract, EventBatchRequest> {

    @Override
    public boolean isValid(EventBatchRequest request, ConstraintValidatorContext context) {
        if (request == null || request.events() == null) {
            return true;
        }

        boolean valid = true;
        context.disableDefaultConstraintViolation();

        for (int index = 0; index < request.events().size(); index++) {
            var event = request.events().get(index);
            if (event == null) {
                continue;
            }
            if (!Objects.equals(request.schemaVersion(), event.schemaVersion())) {
                valid = false;
                addViolation(context, index, "schemaVersion", "배치와 이벤트의 schema_version이 일치해야 합니다.");
            }
        }

        return valid;
    }

    private void addViolation(ConstraintValidatorContext context, int index, String property, String message) {
        context.buildConstraintViolationWithTemplate(message)
                .addPropertyNode("events")
                .inIterable()
                .atIndex(index)
                .addPropertyNode(property)
                .addConstraintViolation();
    }
}
