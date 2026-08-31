package com.cosmetic.collector.config;

import static org.assertj.core.api.Assertions.assertThat;

import com.cosmetic.collector.common.ErrorResponse;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockFilterChain;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import tools.jackson.databind.ObjectMapper;

class EventRequestSizeFilterTest {

    private final ObjectMapper objectMapper = new ObjectMapper();

    @Test
    void rejectsAnEventRequestWhoseContentLengthExceedsTheLimit() throws Exception {
        EventRequestSizeFilter filter = new EventRequestSizeFilter(objectMapper, 10);
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/api/events");
        request.setContent("01234567890".getBytes());
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(request, response, new MockFilterChain());

        ErrorResponse body = objectMapper.readValue(response.getContentAsByteArray(), ErrorResponse.class);
        assertThat(response.getStatus()).isEqualTo(413);
        assertThat(body.code()).isEqualTo("EVENT_REQUEST_TOO_LARGE");
    }

    @Test
    void passesARequestWithinTheLimitToTheNextFilter() throws Exception {
        EventRequestSizeFilter filter = new EventRequestSizeFilter(objectMapper, 10);
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/api/events");
        request.setContent("0123456789".getBytes());
        MockHttpServletResponse response = new MockHttpServletResponse();
        AtomicBoolean proceeded = new AtomicBoolean();

        filter.doFilter(request, response, (ignoredRequest, ignoredResponse) -> proceeded.set(true));

        assertThat(proceeded).isTrue();
    }
}
