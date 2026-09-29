package com.cosmetic.shopbackend.dashboard;

import com.cosmetic.shopbackend.brand.SellerBrandResolver;
import com.cosmetic.shopbackend.identity.AccountRole;
import com.cosmetic.shopbackend.security.ShopPrincipal;
import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/seller/dashboard")
public class DashboardController {

  private final DashboardMartService marts;
  private final SellerBrandResolver sellerBrands;

  public DashboardController(DashboardMartService marts, SellerBrandResolver sellerBrands) {
    this.marts = marts;
    this.sellerBrands = sellerBrands;
  }

  @GetMapping
  public Map<String, Object> dashboard(
    @AuthenticationPrincipal ShopPrincipal actor,
    @RequestParam String brandId
  ) {
    if (
      actor == null || actor.role() != AccountRole.SELLER
    ) throw new org.springframework.web.server.ResponseStatusException(
      org.springframework.http.HttpStatus.FORBIDDEN,
      "seller role required"
    );
    return marts.commerceSummary(actor.accountId(), brandId);
  }

  @GetMapping("/overview")
  public Map<String, Object> overview(@AuthenticationPrincipal ShopPrincipal actor, @RequestParam String brandId, @RequestParam(required = false) String from, @RequestParam(required = false) String to, @RequestParam(required = false) String actorType) { return marts.overview(requireSeller(actor), brandId, from, to, actorType); }

  @GetMapping("/products")
  public Map<String, Object> products(@AuthenticationPrincipal ShopPrincipal actor, @RequestParam String brandId, @RequestParam(required = false) String from, @RequestParam(required = false) String to, @RequestParam(required = false) String actorType) { return marts.products(requireSeller(actor), brandId, from, to, actorType); }

  @GetMapping("/content")
  public Map<String, Object> content(@AuthenticationPrincipal ShopPrincipal actor, @RequestParam String brandId, @RequestParam(required = false) String from, @RequestParam(required = false) String to, @RequestParam(required = false) String actorType) { return marts.content(requireSeller(actor), brandId, from, to, actorType); }

  @GetMapping("/segments")
  public Map<String, Object> segments(@AuthenticationPrincipal ShopPrincipal actor, @RequestParam String brandId, @RequestParam(required = false) String from, @RequestParam(required = false) String to, @RequestParam(required = false) String actorType) { return marts.segments(requireSeller(actor), brandId, from, to, actorType); }

  @GetMapping("/price-position")
  public Map<String, Object> pricePosition(@AuthenticationPrincipal ShopPrincipal actor) { return marts.pricePosition(requireSeller(actor), requireSellerBrand(actor)); }

  @GetMapping("/cohort-position")
  public Map<String, Object> cohortPosition(@AuthenticationPrincipal ShopPrincipal actor, @RequestParam(required = false) String from, @RequestParam(required = false) String to, @RequestParam(required = false) String actorType) { return marts.cohortPosition(requireSeller(actor), requireSellerBrand(actor), from, to, actorType); }

  @GetMapping("/cross-brand")
  public Map<String, Object> crossBrandInflow(
    @AuthenticationPrincipal ShopPrincipal actor,
    @RequestParam String brandId,
    @RequestParam(required = false) String from,
    @RequestParam(required = false) String to,
    @RequestParam(required = false) String actorType,
    @RequestParam(required = false) String generatorType
  ) {
    return marts.crossBrandInflow(requireSeller(actor), brandId, from, to, actorType, generatorType);
  }

  @GetMapping("/ingredients")
  public Map<String, Object> ingredients(@AuthenticationPrincipal ShopPrincipal actor, @RequestParam String brandId, @RequestParam(required = false) String from, @RequestParam(required = false) String to, @RequestParam(required = false) String actorType) { return marts.ingredients(requireSeller(actor), brandId, from, to, actorType); }

  @GetMapping("/friction")
  public Map<String, Object> friction(@AuthenticationPrincipal ShopPrincipal actor, @RequestParam String brandId, @RequestParam(required = false) String from, @RequestParam(required = false) String to, @RequestParam(required = false) String actorType) { return marts.friction(requireSeller(actor), brandId, from, to, actorType); }

  @GetMapping("/purchase")
  public Map<String, Object> purchase(@AuthenticationPrincipal ShopPrincipal actor, @RequestParam String brandId, @RequestParam(required = false) String from, @RequestParam(required = false) String to, @RequestParam(required = false) String actorType) { return marts.purchase(requireSeller(actor), brandId, from, to, actorType); }

  private String requireSeller(ShopPrincipal actor) {
    if (actor == null || actor.role() != AccountRole.SELLER) throw new org.springframework.web.server.ResponseStatusException(org.springframework.http.HttpStatus.FORBIDDEN, "seller role required");
    return actor.accountId();
  }

  private String requireSellerBrand(ShopPrincipal actor) {
    requireSeller(actor);
    return sellerBrands.brandIdOf(actor);
  }
}
