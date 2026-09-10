package com.cosmetic.collector.security;

import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Date;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class JwtAccountVerifierTest {

    private static final String SECRET = "01234567890123456789012345678901";

    @Test
    void returnsTheSubjectOnlyAfterSignatureAndExpiryValidation() {
        JwtAccountVerifier verifier = new JwtAccountVerifier(SECRET);
        String token = token("123", Instant.now().plusSeconds(60), SECRET);

        assertThat(verifier.accountId(token)).isEqualTo("123");
        assertThatThrownBy(() -> verifier.accountId(token("123", Instant.now().plusSeconds(60),
                "another-012345678901234567890123456")))
                .isInstanceOf(RuntimeException.class);
        assertThatThrownBy(() -> verifier.accountId(token("123", Instant.now().minusSeconds(1), SECRET)))
                .isInstanceOf(RuntimeException.class);
    }

    private String token(String accountId, Instant expiresAt, String secret) {
        return Jwts.builder()
                .subject(accountId)
                .expiration(Date.from(expiresAt))
                .signWith(Keys.hmacShaKeyFor(secret.getBytes(StandardCharsets.UTF_8)))
                .compact();
    }
}
