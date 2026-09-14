package com.cosmetic.shopbackend.recommendation;

import com.cosmetic.shopbackend.identity.AccountRole;
import com.cosmetic.shopbackend.identity.Member;
import com.cosmetic.shopbackend.identity.MemberRepository;
import com.cosmetic.shopbackend.security.ShopPrincipal;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/recommend")
public class RecommendationController {

  private final RecommendationClient recommendations;
  private final MemberRepository members;

  public RecommendationController(RecommendationClient recommendations, MemberRepository members) {
    this.recommendations = recommendations;
    this.members = members;
  }

  @GetMapping
  public ResponseEntity<String> recommend(
    @AuthenticationPrincipal ShopPrincipal actor,
    @RequestParam(defaultValue = "10") int size,
    @RequestParam(defaultValue = "2") int reserved,
    @RequestParam(name = "banner_slots", defaultValue = "0") int bannerSlots,
    @RequestParam(defaultValue = "concern,segment") String axes,
    @RequestParam(defaultValue = "top") String hero
  ) {
    if (actor == null) {
      throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "authentication required");
    }
    if (actor.role() != AccountRole.MEMBER) {
      throw new ResponseStatusException(HttpStatus.FORBIDDEN, "member role required");
    }
    Member member = members.findById(actor.accountId()).orElseThrow(
      () -> new ResponseStatusException(HttpStatus.UNAUTHORIZED, "member account not found")
    );
    // persona_id and seed are deliberately not client inputs. Profile values come from the
    // member record, so stale or forged query parameters never change personalization.
    return recommendations.recommend(
      actor.accountId(),
      new RecommendationQuery(
        size, reserved, bannerSlots, axes, hero,
        member.getSkinTypeCode(), member.getSkinToneCode(),
        member.getHairColorCode(), member.getEyeColorCode()
      )
    );
  }
}
