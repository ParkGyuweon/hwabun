package com.cosmetic.shopbackend.security;

import com.cosmetic.shopbackend.identity.AccountRole;
import io.jsonwebtoken.*;
import io.jsonwebtoken.security.Keys;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Date;
import javax.crypto.SecretKey;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class JwtTokenService {

  private final SecretKey key;
  private final long expirationMs;

  public JwtTokenService(
    @Value("${SHOP_BACKEND_JWT_SECRET:}") String secret,
    @Value("${SHOP_BACKEND_JWT_EXPIRATION_MS:900000}") long expirationMs
  ) {
    if (secret == null || secret.length() < 32) throw new IllegalStateException(
      "SHOP_BACKEND_JWT_SECRET must contain at least 32 characters"
    );
    this.key = Keys.hmacShaKeyFor(secret.getBytes(StandardCharsets.UTF_8));
    this.expirationMs = expirationMs;
  }

  public String issue(String accountId, AccountRole role) {
    Instant now = Instant.now();
    return Jwts.builder()
      .subject(accountId)
      .claim("role", role.name())
      .issuedAt(Date.from(now))
      .expiration(Date.from(now.plusMillis(expirationMs)))
      .signWith(key)
      .compact();
  }

  public ShopPrincipal parse(String token) {
    Claims c = Jwts.parser()
      .verifyWith(key)
      .build()
      .parseSignedClaims(token)
      .getPayload();
    return new ShopPrincipal(
      c.getSubject(),
      AccountRole.valueOf(c.get("role", String.class))
    );
  }
}
