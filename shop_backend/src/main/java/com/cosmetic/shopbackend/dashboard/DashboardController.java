package com.cosmetic.shopbackend.dashboard;

import com.cosmetic.shopbackend.identity.AccountRole;
import com.cosmetic.shopbackend.security.ShopPrincipal;
import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/seller/dashboard")
public class DashboardController {

  private final JdbcTemplate jdbc;

  public DashboardController(JdbcTemplate jdbc) {
    this.jdbc = jdbc;
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
    String seller = actor.accountId();
    if (
      jdbc.queryForObject(
        "select count(*) from brand where brand_id=? and seller_account_id=?",
        Integer.class,
        brandId,
        seller
      ) == 0
    ) throw new org.springframework.web.server.ResponseStatusException(
      org.springframework.http.HttpStatus.FORBIDDEN
    );
    return jdbc.queryForMap(
      "select count(distinct oi.order_id) orders,coalesce(sum(oi.line_amount),0) revenue,(select count(*) from review r join order_item x on x.order_item_id=r.order_item_id where x.brand_id=?) reviews,(select count(*) from feedback f join order_item x on x.order_item_id=f.order_item_id where x.brand_id=? and f.status='VISIBLE') feedbacks from order_item oi join shop_order o on o.order_id=oi.order_id where oi.brand_id=? and o.status='PAID'",
      brandId,
      brandId,
      brandId
    );
  }
}
