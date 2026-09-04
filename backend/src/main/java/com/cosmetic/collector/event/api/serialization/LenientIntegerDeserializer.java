package com.cosmetic.collector.event.api.serialization;

import tools.jackson.core.JacksonException;
import tools.jackson.core.JsonParser;
import tools.jackson.core.JsonToken;
import tools.jackson.databind.DeserializationContext;
import tools.jackson.databind.ValueDeserializer;

/** 이벤트 단위 거절을 위해 잘못된 sequence_no는 null로 변환한다. */
public class LenientIntegerDeserializer extends ValueDeserializer<Integer> {

    @Override
    public Integer deserialize(JsonParser parser, DeserializationContext context) throws JacksonException {
        try {
            if (parser.hasToken(JsonToken.VALUE_NUMBER_INT)) {
                return parser.getIntValue();
            }
            if (parser.hasToken(JsonToken.VALUE_STRING)) {
                return Integer.valueOf(parser.getString());
            }
        } catch (NumberFormatException | JacksonException exception) {
            return null;
        }
        parser.skipChildren();
        return null;
    }
}
