package com.cosmetic.collector.security;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpMethod;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

/**
 * Optionally enriches public event ingestion with the authenticated shop account.
 * Missing, expired, or invalid tokens remain anonymous and must never supply an account ID.
 */
@Component
public class EventJwtAuthenticationFilter extends OncePerRequestFilter {

    public static final String ACCOUNT_ID_ATTRIBUTE = "collector.account_id";
    private final JwtAccountVerifier verifier;

    public EventJwtAuthenticationFilter(JwtAccountVerifier verifier) {
        this.verifier = verifier;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return !HttpMethod.POST.matches(request.getMethod()) || !"/api/events".equals(request.getServletPath());
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        String authorization = request.getHeader("Authorization");
        if (authorization == null || !authorization.startsWith("Bearer ")) {
            chain.doFilter(request, response);
            return;
        }
        try {
            request.setAttribute(ACCOUNT_ID_ATTRIBUTE, verifier.accountId(authorization.substring(7)));
        } catch (RuntimeException exception) {
            // Logging is available to anonymous visitors. An invalid credential is never trusted.
        }
        chain.doFilter(request, response);
    }
}
