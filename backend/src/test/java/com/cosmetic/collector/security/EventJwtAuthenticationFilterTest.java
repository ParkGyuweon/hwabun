package com.cosmetic.collector.security;

import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockFilterChain;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Date;

import static org.assertj.core.api.Assertions.assertThat;

class EventJwtAuthenticationFilterTest {

    private static final String SECRET = "01234567890123456789012345678901";

    @Test
    void passesMissingJwtAsAnAnonymousRequest() throws Exception {
        EventJwtAuthenticationFilter filter = filter();
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/api/events");
        request.setServletPath("/api/events");
        MockHttpServletResponse response = new MockHttpServletResponse();
        MockFilterChain chain = new MockFilterChain();

        filter.doFilter(request, response, chain);

        assertThat(response.getStatus()).isEqualTo(200);
        assertThat(request.getAttribute(EventJwtAuthenticationFilter.ACCOUNT_ID_ATTRIBUTE)).isNull();
        assertThat(chain.getRequest()).isSameAs(request);
    }

    @Test
    void passesOnlyVerifiedJwtSubjectToTheController() throws Exception {
        EventJwtAuthenticationFilter filter = filter();
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/api/events");
        request.setServletPath("/api/events");
        request.addHeader("Authorization", "Bearer " + token("123"));
        MockHttpServletResponse response = new MockHttpServletResponse();
        MockFilterChain chain = new MockFilterChain();

        filter.doFilter(request, response, chain);

        assertThat(response.getStatus()).isEqualTo(200);
        assertThat(request.getAttribute(EventJwtAuthenticationFilter.ACCOUNT_ID_ATTRIBUTE)).isEqualTo("123");
        assertThat(chain.getRequest()).isSameAs(request);
    }

    @Test
    void passesInvalidJwtAsAnAnonymousRequest() throws Exception {
        EventJwtAuthenticationFilter filter = filter();
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/api/events");
        request.setServletPath("/api/events");
        request.addHeader("Authorization", "Bearer not-a-jwt");
        MockHttpServletResponse response = new MockHttpServletResponse();
        MockFilterChain chain = new MockFilterChain();

        filter.doFilter(request, response, chain);

        assertThat(response.getStatus()).isEqualTo(200);
        assertThat(request.getAttribute(EventJwtAuthenticationFilter.ACCOUNT_ID_ATTRIBUTE)).isNull();
        assertThat(chain.getRequest()).isSameAs(request);
    }

    private EventJwtAuthenticationFilter filter() {
        return new EventJwtAuthenticationFilter(new JwtAccountVerifier(SECRET));
    }

    private String token(String accountId) {
        return Jwts.builder()
                .subject(accountId)
                .expiration(Date.from(Instant.now().plusSeconds(60)))
                .signWith(Keys.hmacShaKeyFor(SECRET.getBytes(StandardCharsets.UTF_8)))
                .compact();
    }
}
