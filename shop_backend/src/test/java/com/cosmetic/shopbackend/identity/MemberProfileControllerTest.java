package com.cosmetic.shopbackend.identity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.cosmetic.shopbackend.security.ShopPrincipal;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.springframework.web.server.ResponseStatusException;

class MemberProfileControllerTest {

  private Member member() {
    Member m = new Member();
    m.setId("m-1");
    m.setEmail("member@example.com");
    m.setNickname("회원");
    m.setPasswordHash("x");
    m.setSkinTypeCode("combination");
    m.setSkinToneCode("light");
    return m;
  }

  @Test
  void readsOwnProfileFromMemberColumns() {
    MemberRepository members = mock(MemberRepository.class);
    when(members.findById("m-1")).thenReturn(Optional.of(member()));
    MemberProfileController c = new MemberProfileController(members);

    MemberProfileController.Profile p = c.get(new ShopPrincipal("m-1", AccountRole.MEMBER));

    assertEquals("combination", p.skinTypeCode());
    assertEquals("light", p.skinToneCode());
    assertNull(p.hairColorCode());
    assertNull(p.eyeColorCode());
  }

  @Test
  void updateWritesAllFourAndTreatsBlankAsNull() {
    MemberRepository members = mock(MemberRepository.class);
    Member m = member();
    when(members.findById("m-1")).thenReturn(Optional.of(m));
    when(members.save(any(Member.class))).thenAnswer(inv -> inv.getArgument(0));
    MemberProfileController c = new MemberProfileController(members);

    MemberProfileController.Profile p = c.update(
      new ShopPrincipal("m-1", AccountRole.MEMBER),
      new MemberProfileController.Profile("dry", "", null, "brown")
    );

    assertEquals("dry", m.getSkinTypeCode());
    assertNull(m.getSkinToneCode());
    assertNull(m.getHairColorCode());
    assertEquals("brown", m.getEyeColorCode());
    assertEquals("dry", p.skinTypeCode());
    // 마이페이지에서 스스로 저장하면 피부 정보 동의로 본다. 가입 판(consent_version)은 그대로
    assertNotNull(m.getSkinInfoAgreedAt());
    assertNull(m.getConsentVersion());
  }

  @Test
  void clearingAllFourDoesNotRecordSkinInfoConsent() {
    MemberRepository members = mock(MemberRepository.class);
    Member m = member();
    when(members.findById("m-1")).thenReturn(Optional.of(m));
    when(members.save(any(Member.class))).thenAnswer(inv -> inv.getArgument(0));
    MemberProfileController c = new MemberProfileController(members);

    c.update(
      new ShopPrincipal("m-1", AccountRole.MEMBER),
      new MemberProfileController.Profile(null, "", null, null)
    );

    assertNull(m.getSkinTypeCode());
    assertNull(m.getSkinInfoAgreedAt());
  }

  @Test
  void rejectsProfileCodeOutsideDefinedVocabularyWithoutPersisting() {
    MemberRepository members = mock(MemberRepository.class);
    Member m = member();
    when(members.findById("m-1")).thenReturn(Optional.of(m));
    MemberProfileController c = new MemberProfileController(members);

    ResponseStatusException error = assertThrows(ResponseStatusException.class, () -> c.update(
      new ShopPrincipal("m-1", AccountRole.MEMBER),
      new MemberProfileController.Profile("sensitive", "light", "brown", "hazel")
    ));

    assertEquals(400, error.getStatusCode().value());
    assertEquals("combination", m.getSkinTypeCode());
    verify(members, never()).save(any(Member.class));
  }

  @Test
  void rejectsNonMemberAndAnonymous() {
    MemberRepository members = mock(MemberRepository.class);
    MemberProfileController c = new MemberProfileController(members);

    assertThrows(ResponseStatusException.class, () -> c.get(null));
    assertThrows(ResponseStatusException.class, () -> c.get(new ShopPrincipal("s-1", AccountRole.SELLER)));
  }
}
