package com.cosmetic.collector.config;

import com.cosmetic.collector.common.ErrorResponse;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.List;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import tools.jackson.databind.ObjectMapper;

@Component
public class EventRequestSizeFilter extends OncePerRequestFilter {

    private static final String EVENTS_PATH = "/api/events";

    private final ObjectMapper objectMapper;
    private final long maxEventRequestBytes;

    public EventRequestSizeFilter(
            ObjectMapper objectMapper,
            @Value("${collector.http.max-event-request-bytes}") long maxEventRequestBytes
    ) {
        this.objectMapper = objectMapper;
        this.maxEventRequestBytes = maxEventRequestBytes;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return !EVENTS_PATH.equals(request.getRequestURI()) || !"POST".equals(request.getMethod());
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain
    ) throws ServletException, IOException {
        if (request.getContentLengthLong() > maxEventRequestBytes) {
            response.setStatus(HttpServletResponse.SC_REQUEST_ENTITY_TOO_LARGE);
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            objectMapper.writeValue(response.getOutputStream(), new ErrorResponse(
                    "EVENT_REQUEST_TOO_LARGE",
                    "이벤트 요청 본문이 최대 크기를 초과했습니다.",
                    List.of()
            ));
            return;
        }

        filterChain.doFilter(request, response);
    }
}
