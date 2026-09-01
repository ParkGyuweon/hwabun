package com.cosmetic.collector.event.api.validation;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;

import java.lang.annotation.Documented;
import java.lang.annotation.Retention;
import java.lang.annotation.Target;

import static java.lang.annotation.ElementType.TYPE;
import static java.lang.annotation.RetentionPolicy.RUNTIME;

@Documented
@Constraint(validatedBy = EventBatchContractValidator.class)
@Target(TYPE)
@Retention(RUNTIME)
public @interface ValidEventBatchContract {

    String message() default "이벤트 배치 계약을 만족하지 않습니다.";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
