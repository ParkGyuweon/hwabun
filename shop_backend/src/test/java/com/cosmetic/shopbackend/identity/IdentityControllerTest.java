package com.cosmetic.shopbackend.identity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.cosmetic.shopbackend.security.JwtTokenService;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
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

    controller.member(
      new IdentityController.RegisterMember(
        "member@example.com",
        "password123",
        "회원",
        "combination",
        "medium",
        "brown",
        "hazel"
      )
    );

    ArgumentCaptor<Member> saved = ArgumentCaptor.forClass(Member.class);
    org.mockito.Mockito.verify(members).save(saved.capture());
    assertEquals("combination", saved.getValue().getSkinTypeCode());
    assertEquals("medium", saved.getValue().getSkinToneCode());
    assertEquals("brown", saved.getValue().getHairColorCode());
    assertEquals("hazel", saved.getValue().getEyeColorCode());
  }
}
