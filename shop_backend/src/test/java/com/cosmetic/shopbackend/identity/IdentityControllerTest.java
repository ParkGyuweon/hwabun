package com.cosmetic.shopbackend.identity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.cosmetic.shopbackend.security.JwtTokenService;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.crypto.password.PasswordEncoder;

class IdentityControllerTest {

  @Test
  void persistsOptionalMemberProfileCodesAtRegistration() {
    SellerAccountRepository sellers = mock(SellerAccountRepository.class);
    MemberRepository members = mock(MemberRepository.class);
    AdminAccountRepository admins = mock(AdminAccountRepository.class);
    PasswordEncoder encoder = mock(PasswordEncoder.class);
    JwtTokenService tokens = mock(JwtTokenService.class);
    when(members.findByEmail("member@example.com")).thenReturn(Optional.empty());
    when(encoder.encode("password123")).thenReturn("encoded");
    when(members.save(any(Member.class))).thenAnswer(invocation -> invocation.getArgument(0));
    when(tokens.issue(any(String.class), any(AccountRole.class))).thenReturn("token");
    IdentityController controller = new IdentityController(
      sellers,
      members,
      admins,
      encoder,
      tokens
    );

    ResponseEntity<?> created = controller.member(
      new IdentityController.RegisterMember(
        "member@example.com",
        "password123",
        "회원",
        "combination",
        "medium",
        "brown",
        "hazel",
        true,
        true,
        true,
        null
      )
    );

    ArgumentCaptor<Member> saved = ArgumentCaptor.forClass(Member.class);
    org.mockito.Mockito.verify(members).save(saved.capture());
    assertEquals("combination", saved.getValue().getSkinTypeCode());
    assertEquals("medium", saved.getValue().getSkinToneCode());
    assertEquals("brown", saved.getValue().getHairColorCode());
    assertEquals("hazel", saved.getValue().getEyeColorCode());
    assertNotNull(saved.getValue().getTermsAgreedAt());
    assertNotNull(saved.getValue().getPrivacyAgreedAt());
    assertNotNull(saved.getValue().getSkinInfoAgreedAt());
    assertNull(saved.getValue().getBehaviorLinkAgreedAt());
    assertEquals(
      IdentityController.CONSENT_VERSION,
      saved.getValue().getConsentVersion()
    );
    // 연결 동의(agreeBehaviorLink)를 안 했으니 행동 로그는 계정과 잇지 않는다
    assertFalse(saved.getValue().isBehaviorLinked());
    assertFalse(
      ((IdentityController.AccountResponse) created.getBody()).behaviorLinked()
    );
  }

  @Test
  void behaviorLinkFollowsConsentButLegacyAccountsStayLinked() {
    Member legacy = new Member();
    assertTrue(legacy.isBehaviorLinked());

    Member declined = new Member();
    declined.setConsentVersion(IdentityController.CONSENT_VERSION);
    assertFalse(declined.isBehaviorLinked());

    Member agreed = new Member();
    agreed.setConsentVersion(IdentityController.CONSENT_VERSION);
    agreed.setBehaviorLinkAgreedAt(java.time.LocalDateTime.now());
    assertTrue(agreed.isBehaviorLinked());
  }

  @Test
  void loginReportsBehaviorLinkOfMember() {
    MemberRepository members = mock(MemberRepository.class);
    PasswordEncoder encoder = mock(PasswordEncoder.class);
    Member declined = new Member();
    declined.setId("m-1");
    declined.setEmail("declined@example.com");
    declined.setNickname("회원");
    declined.setPasswordHash("$2a$hash");
    declined.setConsentVersion(IdentityController.CONSENT_VERSION);
    when(members.findByEmail("declined@example.com")).thenReturn(Optional.of(declined));

    IdentityController c = new IdentityController(
      mock(SellerAccountRepository.class),
      members,
      mock(AdminAccountRepository.class),
      encoder,
      mock(JwtTokenService.class)
    );
    when(encoder.matches("password123", "$2a$hash")).thenReturn(true);

    ResponseEntity<IdentityController.AccountResponse> res = c.login(
      new IdentityController.Login("declined@example.com", "password123", AccountRole.MEMBER)
    );

    assertEquals(200, res.getStatusCode().value());
    assertFalse(res.getBody().behaviorLinked());
  }

  @Test
  void rejectsRegistrationWithoutRequiredConsent() {
    MemberRepository members = mock(MemberRepository.class);
    IdentityController controller = controller(members);

    ResponseEntity<?> res = controller.member(
      register(false, true, true, "combination")
    );

    assertEquals(400, res.getStatusCode().value());
    assertTrue(((Map<?, ?>) res.getBody()).get("message").toString().contains("동의"));
    verify(members, never()).save(any(Member.class));
    assertEquals(
      400,
      controller.member(register(true, null, true, "dry")).getStatusCode().value()
    );
  }

  @Test
  void dropsSkinProfileWhenSkinInfoNotAgreed() {
    MemberRepository members = mock(MemberRepository.class);
    IdentityController controller = controller(members);

    ResponseEntity<?> res = controller.member(
      register(true, true, false, "combination")
    );

    assertEquals(201, res.getStatusCode().value());
    ArgumentCaptor<Member> saved = ArgumentCaptor.forClass(Member.class);
    verify(members).save(saved.capture());
    assertNull(saved.getValue().getSkinTypeCode());
    assertNull(saved.getValue().getSkinToneCode());
    assertNull(saved.getValue().getHairColorCode());
    assertNull(saved.getValue().getEyeColorCode());
    assertNull(saved.getValue().getSkinInfoAgreedAt());
    assertNotNull(saved.getValue().getTermsAgreedAt());
  }

  private static IdentityController.RegisterMember register(
    Boolean terms,
    Boolean privacy,
    Boolean skinInfo,
    String skinType
  ) {
    return new IdentityController.RegisterMember(
      "member@example.com",
      "password123",
      "회원",
      skinType,
      "medium",
      "brown",
      "hazel",
      terms,
      privacy,
      skinInfo,
      false
    );
  }

  private static IdentityController controller(MemberRepository members) {
    PasswordEncoder encoder = mock(PasswordEncoder.class);
    JwtTokenService tokens = mock(JwtTokenService.class);
    when(members.findByEmail("member@example.com")).thenReturn(Optional.empty());
    when(encoder.encode("password123")).thenReturn("encoded");
    when(members.save(any(Member.class))).thenAnswer(invocation -> invocation.getArgument(0));
    when(tokens.issue(any(String.class), any(AccountRole.class))).thenReturn("token");
    return new IdentityController(
      mock(SellerAccountRepository.class),
      members,
      mock(AdminAccountRepository.class),
      encoder,
      tokens
    );
  }
}
