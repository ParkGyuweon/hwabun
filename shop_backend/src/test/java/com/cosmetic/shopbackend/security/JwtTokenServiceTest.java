package com.cosmetic.shopbackend.security;

import static org.junit.jupiter.api.Assertions.*;

import com.cosmetic.shopbackend.identity.AccountRole;
import io.jsonwebtoken.JwtException;
import org.junit.jupiter.api.Test;

class JwtTokenServiceTest {

  private static final String SECRET = "01234567890123456789012345678901";

  @Test
  void issueAndParseRoundTripPreservesSubjectAndRole() {
    JwtTokenService service = new JwtTokenService(SECRET, 60_000);

    ShopPrincipal principal = service.parse(
      service.issue("account-42", AccountRole.SELLER)
    );

    assertEquals("account-42", principal.accountId());
    assertEquals(AccountRole.SELLER, principal.role());
  }

  @Test
  void issueAndParseRoundTripPreservesSellerBrandClaim() {
    JwtTokenService service = new JwtTokenService(SECRET, 60_000);

    ShopPrincipal principal = service.parse(
      service.issue("seller-42", AccountRole.SELLER, "brand-42")
    );

    assertEquals("brand-42", principal.brandId());
  }

  @Test
  void rejectsTokenSignedWithDifferentSecret() {
    JwtTokenService issuer = new JwtTokenService(SECRET, 60_000);
    JwtTokenService parser = new JwtTokenService(
      "abcdefghijklmnopqrstuvwxyz123456",
      60_000
    );

    String token = issuer.issue("account-42", AccountRole.MEMBER);

    assertThrows(JwtException.class, () -> parser.parse(token));
  }

  @Test
  void rejectsExpiredToken() {
    JwtTokenService service = new JwtTokenService(SECRET, -1);

    String token = service.issue("account-42", AccountRole.ADMIN);

    assertThrows(JwtException.class, () -> service.parse(token));
  }
}
