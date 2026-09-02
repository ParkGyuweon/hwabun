package com.cosmetic.collector.config;

import com.cosmetic.collector.common.ErrorResponse;
import com.cosmetic.collector.event.observability.CollectorMetrics;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ReadListener;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletInputStream;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpServletRequestWrapper;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import tools.jackson.databind.ObjectMapper;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 1)
public class EventRequestSizeFilter extends OncePerRequestFilter {

    private static final String EVENTS_PATH = "/api/events";

    private final ObjectMapper objectMapper;
    private final CollectorMetrics metrics;
    private final long maxEventRequestBytes;

    public EventRequestSizeFilter(
            ObjectMapper objectMapper,
            CollectorMetrics metrics,
            @Value("${collector.http.max-event-request-bytes}") long maxEventRequestBytes
    ) {
        this.objectMapper = objectMapper;
        this.metrics = metrics;
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
            writePayloadTooLarge(response);
            return;
        }

        if (request.getContentLengthLong() < 0) {
            byte[] body = readBodyWithinLimit(request.getInputStream());
            if (body == null) {
                writePayloadTooLarge(response);
                return;
            }
            filterChain.doFilter(new CachedBodyRequest(request, body), response);
            return;
        }

        filterChain.doFilter(request, response);
    }

    private byte[] readBodyWithinLimit(InputStream input) throws IOException {
        ByteArrayOutputStream body = new ByteArrayOutputStream();
        byte[] buffer = new byte[8192];
        long bytesRead = 0;

        while (true) {
            int nextReadSize = (int) Math.min(buffer.length, maxEventRequestBytes - bytesRead + 1);
            int read = input.read(buffer, 0, nextReadSize);
            if (read == -1) {
                return body.toByteArray();
            }

            body.write(buffer, 0, read);
            bytesRead += read;
            if (bytesRead > maxEventRequestBytes) {
                return null;
            }
        }
    }

    private void writePayloadTooLarge(HttpServletResponse response) throws IOException {
        metrics.recordValidationFailure("event_request_too_large");
        response.setStatus(HttpServletResponse.SC_REQUEST_ENTITY_TOO_LARGE);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        objectMapper.writeValue(response.getOutputStream(), new ErrorResponse(
                "EVENT_REQUEST_TOO_LARGE",
                "이벤트 요청 본문이 최대 크기를 초과했습니다.",
                List.of()
        ));
    }

    private static class CachedBodyRequest extends HttpServletRequestWrapper {

        private final byte[] body;

        CachedBodyRequest(HttpServletRequest request, byte[] body) {
            super(request);
            this.body = body;
        }

        @Override
        public ServletInputStream getInputStream() {
            return new CachedServletInputStream(body);
        }

        @Override
        public BufferedReader getReader() {
            String encoding = getCharacterEncoding();
            Charset charset = encoding == null ? StandardCharsets.UTF_8 : Charset.forName(encoding);
            return new BufferedReader(new InputStreamReader(new ByteArrayInputStream(body), charset));
        }
    }

    private static class CachedServletInputStream extends ServletInputStream {

        private final ByteArrayInputStream input;

        CachedServletInputStream(byte[] body) {
            this.input = new ByteArrayInputStream(body);
        }

        @Override
        public int read() {
            return input.read();
        }

        @Override
        public int read(byte[] bytes, int offset, int length) {
            return input.read(bytes, offset, length);
        }

        @Override
        public boolean isFinished() {
            return input.available() == 0;
        }

        @Override
        public boolean isReady() {
            return true;
        }

        @Override
        public void setReadListener(ReadListener readListener) {
            throw new UnsupportedOperationException("Asynchronous reads are not supported");
        }
    }
}
