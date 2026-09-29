package com.cosmetic.shopbackend.security;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.cosmetic.shopbackend.identity.AccountRole;
import com.cosmetic.shopbackend.identity.AccountStatus;
import com.cosmetic.shopbackend.identity.MemberRepository;
import java.util.Optional;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockFilterChain;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

class JwtAuthenticationFilterTest {

  private final JwtTokenService tokens = new JwtTokenService("01234567890123456789012345678901", 60_000);
  private final MemberRepository members = mock(MemberRepository.class);
  private final JwtAuthenticationFilter filter = new JwtAuthenticationFilter(tokens, members);

  @AfterEach
  void clear() {
    SecurityContextHolder.clearContext();
  }

  private Authentication run(String token) throws Exception {
    MockHttpServletRequest req = new MockHttpServletRequest("GET", "/api/orders");
    req.addHeader("Authorization", "Bearer " + token);
    filter.doFilter(req, new MockHttpServletResponse(), new MockFilterChain());
    return SecurityContextHolder.getContext().getAuthentication();
  }

  @Test
  void activeMemberTokenAuthenticates() throws Exception {
    when(members.findStatusById("m-1")).thenReturn(Optional.of(AccountStatus.ACTIVE));

    Authentication auth = run(tokens.issue("m-1", AccountRole.MEMBER));

    assertNotNull(auth);
    assertEquals("m-1", ((ShopPrincipal) auth.getPrincipal()).accountId());
  }

  @Test
  void withdrawnOrMissingMemberTokenDoesNotAuthenticate() throws Exception {
    when(members.findStatusById("m-1")).thenReturn(Optional.of(AccountStatus.WITHDRAWN));
    when(members.findStatusById("m-gone")).thenReturn(Optional.empty());

    assertNull(run(tokens.issue("m-1", AccountRole.MEMBER)));
    SecurityContextHolder.clearContext();
    assertNull(run(tokens.issue("m-gone", AccountRole.MEMBER)));
  }

  @Test
  void sellerAndAdminTokensSkipMemberLookup() throws Exception {
    assertNotNull(run(tokens.issue("s-1", AccountRole.SELLER, "brand-1")));
    SecurityContextHolder.clearContext();
    assertNotNull(run(tokens.issue("a-1", AccountRole.ADMIN)));
    verify(members, never()).findStatusById(anyString());
  }
}
