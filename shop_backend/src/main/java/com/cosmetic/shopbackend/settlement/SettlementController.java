package com.cosmetic.shopbackend.settlement;

import com.cosmetic.shopbackend.identity.AccountRole;
import com.cosmetic.shopbackend.security.ShopPrincipal;
import java.time.LocalDate;
import java.util.*;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/settlements")
public class SettlementController {

  private final JdbcTemplate jdbc;
  private final SettlementService settlements;

  public SettlementController(
    JdbcTemplate jdbc,
    SettlementService settlements
  ) {
    this.jdbc = jdbc;
    this.settlements = settlements;
  }

  @GetMapping
  public List<Map<String, Object>> list(
    @AuthenticationPrincipal ShopPrincipal actor,
    @RequestParam String brandId
  ) {
    requireSeller(actor);
    owns(actor.accountId(), brandId);
    return jdbc.queryForList(
      "select * from settlement where brand_id=? order by settlement_month desc",
      brandId
    );
  }

  @PostMapping("/generate")
  public Map<String, Object> generate(
    @AuthenticationPrincipal ShopPrincipal actor,
    @RequestParam String brandId,
    @RequestParam String month
  ) {
    requireSeller(actor);
    owns(actor.accountId(), brandId);
    return settlements.generate(brandId, LocalDate.parse(month + "-01"));
  }

  private void owns(String seller, String brand) {
    if (
      jdbc.queryForObject(
        "select count(*) from brand where brand_id=? and seller_account_id=?",
        Integer.class,
        brand,
        seller
      ) == 0
    ) throw new ResponseStatusException(
      HttpStatus.FORBIDDEN,
      "brand access denied"
    );
  }

  private void requireSeller(ShopPrincipal actor) {
    if (
      actor == null || actor.role() != AccountRole.SELLER
    ) throw new ResponseStatusException(
      HttpStatus.FORBIDDEN,
      "seller role required"
    );
  }
}
