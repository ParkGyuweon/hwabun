package com.cosmetic.shopbackend.feedback;

import com.cosmetic.shopbackend.brand.SellerBrandResolver;
import com.cosmetic.shopbackend.identity.AccountRole;
import com.cosmetic.shopbackend.security.ShopPrincipal;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
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
  private final SellerBrandResolver sellerBrands;

  public FeedbackClassificationController(
    FeedbackClassificationService classifications,
    SellerBrandResolver sellerBrands
  ) {
    this.classifications = classifications;
    this.sellerBrands = sellerBrands;
  }

  @PostMapping("/classify")
  public ResponseEntity<Map<String, Object>> classify(
    @AuthenticationPrincipal ShopPrincipal actor,
    @RequestParam(required = false) String brandId
  ) {
    String ownedBrandId = ownedBrandId(actor, brandId);
    if (!classifications.startAsync(ownedBrandId, null)) {
      return ResponseEntity.status(HttpStatus.CONFLICT).body(Map.of(
        "status", "IN_PROGRESS",
        "message", "feedback classification is already running"
      ));
    }
    return ResponseEntity.accepted().body(Map.of(
      "status", "ACCEPTED",
      "message", "feedback classification started"
    ));
  }

  private String ownedBrandId(ShopPrincipal actor, String requestedBrandId) {
    if (actor == null || actor.role() != AccountRole.SELLER) {
      throw new ResponseStatusException(HttpStatus.FORBIDDEN, "seller role required");
    }
    String ownedBrandId = sellerBrands.brandIdOf(actor);
    if (requestedBrandId != null && !requestedBrandId.isBlank() &&
      !ownedBrandId.equals(requestedBrandId)) {
      throw new ResponseStatusException(HttpStatus.FORBIDDEN, "brand access denied");
    }
    return ownedBrandId;
  }
}
