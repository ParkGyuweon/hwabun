package com.cosmetic.shopbackend.recommendation;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.cosmetic.shopbackend.identity.AccountRole;
import com.cosmetic.shopbackend.identity.Member;
import com.cosmetic.shopbackend.identity.MemberRepository;
import com.cosmetic.shopbackend.security.ShopPrincipal;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.server.ResponseStatusException;

class RecommendationControllerTest {

  @Test
  void rejectsAnonymousRequestsBeforeCallingRecommendationService() {
    RecommendationClient client = mock(RecommendationClient.class);
    MemberRepository members = mock(MemberRepository.class);

    ResponseStatusException exception = assertThrows(
      ResponseStatusException.class,
      () -> new RecommendationController(client, members).recommend(null, 10, 2, 0, "concern,segment", "top")
    );

    assertEquals(HttpStatus.UNAUTHORIZED, exception.getStatusCode());
  }

  @Test
  void memberAccountIsThePersonaStateKey() {
    RecommendationClient client = mock(RecommendationClient.class);
    MemberRepository members = mock(MemberRepository.class);
    ShopPrincipal member = new ShopPrincipal("member-42", AccountRole.MEMBER);
    Member profile = new Member();
    profile.setSkinTypeCode("dry");
    when(members.findById("member-42")).thenReturn(java.util.Optional.of(profile));
    when(client.recommend(eq("member-42"), any(RecommendationQuery.class)))
      .thenReturn(ResponseEntity.ok("{\"items\":[]}"));

    new RecommendationController(client, members).recommend(member, 10, 2, 0, "concern,segment", "new_brand");

    verify(client).recommend(eq("member-42"), any(RecommendationQuery.class));
  }

  @Test
  void rejectsNonMemberAccounts() {
    RecommendationClient client = mock(RecommendationClient.class);
    MemberRepository members = mock(MemberRepository.class);
    ShopPrincipal seller = new ShopPrincipal("seller-42", AccountRole.SELLER);

    ResponseStatusException exception = assertThrows(
      ResponseStatusException.class,
      () -> new RecommendationController(client, members).recommend(seller, 10, 2, 0, "concern,segment", "top")
    );

    assertEquals(HttpStatus.FORBIDDEN, exception.getStatusCode());
  }
}
