package com.cosmetic.shopbackend.identity;

import com.cosmetic.shopbackend.security.ShopPrincipal;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Size;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

/**
 * 로그인한 회원 본인의 피부 프로필 (member.skin_type_code · skin_tone_code · hair_color_code · eye_color_code).
 *
 * 가입 때 받은 네 값은 컬럼에 있었지만 읽고 고치는 API 가 없어서, 마이페이지가 이 브라우저(localStorage)에만 저장하고
 * 서버 값은 한 번도 보여 주지 못했다 (2026-09-21 제보). 이 두 엔드포인트가 그 자리다.
 *
 *   GET /api/members/me/profile   → 200 { skinTypeCode, skinToneCode, hairColorCode, eyeColorCode } (없으면 null)
 *   PUT /api/members/me/profile   { 같은 네 필드 } → 200 저장된 값. 필드를 null 로 보내면 "선택 안 함" 으로 지운다
 *
 * 값 검증은 하지 않는다 — 어휘(contracts/product-form-labels-ko.json segment)는 프론트가 정하고, 리뷰 스냅샷·마트가
 * 이 컬럼을 그대로 읽는다. 길이만 컬럼 크기(32)로 막는다. MEMBER 만. /api/auth/** 가 permitAll 이라 거기 두지 않았다.
 */
@RestController
@RequestMapping("/api/members/me/profile")
public class MemberProfileController {

  private final MemberRepository members;

  public MemberProfileController(MemberRepository members) {
    this.members = members;
  }

  public record Profile(
    @Size(max = 32) String skinTypeCode,
    @Size(max = 32) String skinToneCode,
    @Size(max = 32) String hairColorCode,
    @Size(max = 32) String eyeColorCode
  ) {
    static Profile of(Member m) {
      return new Profile(m.getSkinTypeCode(), m.getSkinToneCode(), m.getHairColorCode(), m.getEyeColorCode());
    }
  }

  @GetMapping
  public Profile get(@AuthenticationPrincipal ShopPrincipal actor) {
    return Profile.of(member(actor));
  }

  @PutMapping
  @Transactional
  public Profile update(@AuthenticationPrincipal ShopPrincipal actor, @Valid @RequestBody Profile req) {
    Member m = member(actor);
    m.setSkinTypeCode(blankToNull(req.skinTypeCode()));
    m.setSkinToneCode(blankToNull(req.skinToneCode()));
    m.setHairColorCode(blankToNull(req.hairColorCode()));
    m.setEyeColorCode(blankToNull(req.eyeColorCode()));
    members.save(m);
    return Profile.of(m);
  }

  private Member member(ShopPrincipal actor) {
    if (actor == null || actor.role() != AccountRole.MEMBER) {
      throw new ResponseStatusException(HttpStatus.FORBIDDEN, "member role required");
    }
    return members
      .findById(actor.accountId())
      .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "member not found"));
  }

  private static String blankToNull(String s) {
    return s == null || s.isBlank() ? null : s.trim();
  }
}
