package com.cosmetic.shopbackend.feedback;

import com.cosmetic.shopbackend.identity.AccountRole;
import com.cosmetic.shopbackend.security.ShopPrincipal;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/seller/feedback")
public class FeedbackClassificationController {

  private final FeedbackClassificationService classifications;

  public FeedbackClassificationController(FeedbackClassificationService classifications) {
    this.classifications = classifications;
  }

  @PostMapping("/classify")
  public Map<String, Object> classify(
    @AuthenticationPrincipal ShopPrincipal actor,
    @RequestParam(required = false) String brandId
  ) {
    String ownedBrandId = ownedBrandId(actor, brandId);
    FeedbackClassificationService.RunResult result = classifications.classifyPending(
      ownedBrandId,
      null
    );
    return Map.of(
      "status", result.status(),
      "selected", result.selected(),
      "completed", result.completed(),
      "failed", result.failed()
    );
  }

  private String ownedBrandId(ShopPrincipal actor, String requestedBrandId) {
    if (actor == null || actor.role() != AccountRole.SELLER) {
      throw new ResponseStatusException(HttpStatus.FORBIDDEN, "seller role required");
    }
    String ownedBrandId = actor.brandId();
    if (ownedBrandId == null || ownedBrandId.isBlank()) {
      throw new ResponseStatusException(HttpStatus.FORBIDDEN, "brand claim required");
    }
    if (requestedBrandId != null && !requestedBrandId.isBlank() &&
      !ownedBrandId.equals(requestedBrandId)) {
      throw new ResponseStatusException(HttpStatus.FORBIDDEN, "brand access denied");
    }
    return ownedBrandId;
  }
}
