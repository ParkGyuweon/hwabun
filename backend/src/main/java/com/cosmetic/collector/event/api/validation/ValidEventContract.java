package com.cosmetic.collector.event.api.validation;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;

import java.lang.annotation.Documented;
import java.lang.annotation.Retention;
import java.lang.annotation.Target;

import static java.lang.annotation.ElementType.TYPE;
import static java.lang.annotation.RetentionPolicy.RUNTIME;

@Documented
@Constraint(validatedBy = EventContractValidator.class)
@Target(TYPE)
@Retention(RUNTIME)
public @interface ValidEventContract {

    String message() default "이벤트 계약을 만족하지 않습니다.";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
