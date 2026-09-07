package com.cosmetic.collector.config;

import static org.assertj.core.api.Assertions.assertThat;

import com.cosmetic.collector.common.ErrorResponse;
import com.cosmetic.collector.event.observability.CollectorMetrics;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.nio.charset.StandardCharsets;
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
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        EventRequestSizeFilter filter = new EventRequestSizeFilter(objectMapper, new CollectorMetrics(registry), 10);
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/api/events");
        request.setContent("01234567890".getBytes());
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(request, response, new MockFilterChain());

        ErrorResponse body = objectMapper.readValue(response.getContentAsByteArray(), ErrorResponse.class);
        assertThat(response.getStatus()).isEqualTo(413);
        assertThat(body.code()).isEqualTo("EVENT_REQUEST_TOO_LARGE");
        assertThat(registry.get("collector.events.validation.rejected")
                .tag("code", "event_request_too_large").counter().count()).isEqualTo(1);
    }

    @Test
    void passesARequestWithinTheLimitToTheNextFilter() throws Exception {
        EventRequestSizeFilter filter = filter(10);
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/api/events");
        request.setContent("0123456789".getBytes());
        MockHttpServletResponse response = new MockHttpServletResponse();
        AtomicBoolean proceeded = new AtomicBoolean();

        filter.doFilter(request, response, (ignoredRequest, ignoredResponse) -> proceeded.set(true));

        assertThat(proceeded).isTrue();
    }

    @Test
    void rejectsAChunkedEventRequestWhoseBodyExceedsTheLimit() throws Exception {
        EventRequestSizeFilter filter = filter(10);
        MockHttpServletRequest request = chunkedEventRequest("01234567890");
        MockHttpServletResponse response = new MockHttpServletResponse();
        AtomicBoolean proceeded = new AtomicBoolean();

        filter.doFilter(request, response, (ignoredRequest, ignoredResponse) -> proceeded.set(true));

        assertThat(response.getStatus()).isEqualTo(413);
        assertThat(proceeded).isFalse();
    }

    @Test
    void passesAndPreservesAChunkedEventRequestWithinTheLimit() throws Exception {
        EventRequestSizeFilter filter = filter(10);
        MockHttpServletRequest request = chunkedEventRequest("0123456789");
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(request, response, (wrappedRequest, ignoredResponse) -> {
            assertThat(wrappedRequest.getInputStream().readAllBytes())
                    .isEqualTo("0123456789".getBytes(StandardCharsets.UTF_8));
        });

        assertThat(response.getStatus()).isEqualTo(200);
    }

    private MockHttpServletRequest chunkedEventRequest(String body) {
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/api/events") {
            @Override
            public long getContentLengthLong() {
                return -1;
            }
        };
        request.setContent(body.getBytes(StandardCharsets.UTF_8));
        return request;
    }

    private EventRequestSizeFilter filter(long maxEventRequestBytes) {
        return new EventRequestSizeFilter(
                objectMapper,
                new CollectorMetrics(new SimpleMeterRegistry()),
                maxEventRequestBytes
        );
    }
}
