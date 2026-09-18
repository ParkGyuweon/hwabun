package com.cosmetic.shopbackend.feedback;

import com.cosmetic.shopbackend.brand.BrandRepository;
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

  private final BrandRepository brands;
  private final FeedbackClassificationService classifications;

  public FeedbackClassificationController(
    BrandRepository brands,
    FeedbackClassificationService classifications
  ) {
    this.brands = brands;
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
    String ownedBrandId = brands.findAllBySeller_Id(actor.accountId()).stream()
      .findFirst()
      .map(brand -> brand.getId())
      .orElseThrow(() -> new ResponseStatusException(
        HttpStatus.FORBIDDEN,
        "brand access denied"
      ));
    if (requestedBrandId != null && !requestedBrandId.isBlank() &&
      !ownedBrandId.equals(requestedBrandId)) {
      throw new ResponseStatusException(HttpStatus.FORBIDDEN, "brand access denied");
    }
    return ownedBrandId;
  }
}
