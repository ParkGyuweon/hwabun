package com.cosmetic.collector.config;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.mock.web.MockFilterChain;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.web.filter.CorsFilter;

class WebConfigTest {

    @Test
    void exposesRetryAfterForAllowedOrigins() throws Exception {
        FilterRegistrationBean<CorsFilter> registration = new WebConfig(new String[]{"http://localhost:3000"})
                .corsFilter();
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/api/events");
        request.addHeader("Origin", "http://localhost:3000");
        MockHttpServletResponse response = new MockHttpServletResponse();

        registration.getFilter().doFilter(request, response, new MockFilterChain());

        assertThat(response.getHeader("Access-Control-Allow-Origin")).isEqualTo("http://localhost:3000");
        assertThat(response.getHeader("Access-Control-Expose-Headers"))
                .contains("X-Request-Id", "Retry-After");
    }
}
