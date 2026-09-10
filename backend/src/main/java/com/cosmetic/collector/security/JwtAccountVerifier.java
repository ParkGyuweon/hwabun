package com.cosmetic.collector.security;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;

/** Validates the signed shop JWT and returns its authenticated account subject. */
@Service
public class JwtAccountVerifier {

    private final SecretKey key;

    public JwtAccountVerifier(@Value("${SHOP_BACKEND_JWT_SECRET:}") String secret) {
        if (secret == null || secret.length() < 32) {
            throw new IllegalStateException("SHOP_BACKEND_JWT_SECRET must contain at least 32 characters");
        }
        this.key = Keys.hmacShaKeyFor(secret.getBytes(StandardCharsets.UTF_8));
    }

    public String accountId(String token) {
        Claims claims = Jwts.parser().verifyWith(key).build().parseSignedClaims(token).getPayload();
        String subject = claims.getSubject();
        if (subject == null || subject.isBlank()) {
            throw new IllegalArgumentException("JWT subject is required");
        }
        return subject;
    }
}
