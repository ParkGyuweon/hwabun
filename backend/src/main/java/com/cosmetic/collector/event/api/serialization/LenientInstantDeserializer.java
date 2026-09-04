package com.cosmetic.collector.event.api.serialization;

import tools.jackson.core.JacksonException;
import tools.jackson.core.JsonParser;
import tools.jackson.core.JsonToken;
import tools.jackson.databind.DeserializationContext;
import tools.jackson.databind.ValueDeserializer;

import java.time.Instant;
import java.time.format.DateTimeParseException;

/** 이벤트 단위 거절을 위해 잘못된 occurred_at은 null로 변환한다. */
public class LenientInstantDeserializer extends ValueDeserializer<Instant> {

    @Override
    public Instant deserialize(JsonParser parser, DeserializationContext context) throws JacksonException {
        if (!parser.hasToken(JsonToken.VALUE_STRING)) {
            parser.skipChildren();
            return null;
        }
        try {
            return Instant.parse(parser.getString());
        } catch (DateTimeParseException exception) {
            return null;
        }
    }
}
