package com.cosmetic.shopbackend.identity;

import com.cosmetic.shopbackend.security.ShopPrincipal;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Size;
import java.util.Set;
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
 * 값은 프론트와 같은 어휘만 받는다. 이 컬럼은 리뷰 스냅샷·추천·마트가 그대로 읽으므로, 정의되지 않은 값은
 * 400으로 거절해 데이터 계약을 지킨다. MEMBER 만. /api/auth/** 가 permitAll 이라 거기 두지 않았다.
 */
@RestController
@RequestMapping("/api/members/me/profile")
public class MemberProfileController {

  private static final Set<String> SKIN_TYPES = Set.of("combination", "dry", "normal", "oily");
  private static final Set<String> SKIN_TONES = Set.of("fair", "light", "medium", "tan", "deep");
  private static final Set<String> HAIR_COLORS = Set.of("black", "brown", "blonde", "auburn", "red", "gray");
  private static final Set<String> EYE_COLORS = Set.of("blue", "brown", "green", "gray", "hazel");

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
    String skinType = validOrNull(req.skinTypeCode(), SKIN_TYPES, "skinTypeCode");
    String skinTone = validOrNull(req.skinToneCode(), SKIN_TONES, "skinToneCode");
    String hairColor = validOrNull(req.hairColorCode(), HAIR_COLORS, "hairColorCode");
    String eyeColor = validOrNull(req.eyeColorCode(), EYE_COLORS, "eyeColorCode");
    m.setSkinTypeCode(skinType);
    m.setSkinToneCode(skinTone);
    m.setHairColorCode(hairColor);
    m.setEyeColorCode(eyeColor);
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

  private static String validOrNull(String value, Set<String> allowed, String field) {
    if (value == null || value.isBlank()) return null;
    if (!allowed.contains(value)) {
      throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "invalid " + field);
    }
    return value;
  }
}
