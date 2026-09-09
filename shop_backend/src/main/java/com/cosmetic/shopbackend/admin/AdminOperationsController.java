package com.cosmetic.shopbackend.admin;

import com.cosmetic.shopbackend.identity.AccountRole;
import com.cosmetic.shopbackend.security.ShopPrincipal;
import java.time.LocalDateTime;
import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/admin")
public class AdminOperationsController {

  private final JdbcTemplate jdbc;

  public AdminOperationsController(JdbcTemplate jdbc) {
    this.jdbc = jdbc;
  }

  @PatchMapping("/products/{id}/approval")
  public Map<String, Object> product(
    @PathVariable String id,
    @AuthenticationPrincipal ShopPrincipal actor,
    @RequestParam String status
  ) {
    requireAdmin(actor);
    String normalized = enumValue(
      status,
      "DRAFT",
      "PENDING_APPROVAL",
      "ACTIVE",
      "INACTIVE",
      "REJECTED"
    );
    updateOr404(
      "update product set status=? where product_id=?",
      normalized,
      id
    );
    return Map.of("productId", id, "status", normalized);
  }

  @PatchMapping("/brands/{id}/status")
  public Map<String, Object> brand(
    @PathVariable String id,
    @AuthenticationPrincipal ShopPrincipal actor,
    @RequestParam String status
  ) {
    requireAdmin(actor);
    String normalized = enumValue(status, "ACTIVE", "INACTIVE");
    updateOr404("update brand set status=? where brand_id=?", normalized, id);
    return Map.of("brandId", id, "status", normalized);
  }

  @PatchMapping("/feedback/{id}/status")
  public Map<String, Object> feedback(
    @PathVariable String id,
    @AuthenticationPrincipal ShopPrincipal actor,
    @RequestParam String status
  ) {
    requireAdmin(actor);
    String normalized = enumValue(status, "VISIBLE", "HIDDEN", "DELETED");
    updateOr404(
      "update feedback set status=? where feedback_id=?",
      normalized,
      id
    );
    return Map.of("feedbackId", id, "status", normalized);
  }

  @PostMapping("/settlements/{id}/complete")
  public Map<String, Object> complete(
    @PathVariable String id,
    @AuthenticationPrincipal ShopPrincipal actor
  ) {
    requireAdmin(actor);
    String admin = actor.accountId();
    updateOr404(
      "update settlement set status='COMPLETED',completed_at=?,completed_by=? where settlement_id=? and status='PENDING'",
      LocalDateTime.now(),
      admin,
      id
    );
    return Map.of("settlementId", id, "status", "COMPLETED");
  }

  private void requireAdmin(ShopPrincipal actor) {
    if (
      actor == null ||
      actor.role() != AccountRole.ADMIN ||
      jdbc.queryForObject(
        "select count(*) from admin_account where admin_account_id=? and status='ACTIVE'",
        Integer.class,
        actor.accountId()
      ) == 0
    ) throw new org.springframework.web.server.ResponseStatusException(
      org.springframework.http.HttpStatus.FORBIDDEN,
      "active administrator required"
    );
  }

  private String enumValue(String value, String... allowed) {
    String normalized = value.toUpperCase(java.util.Locale.ROOT);
    for (String a : allowed) if (a.equals(normalized)) return normalized;
    throw new org.springframework.web.server.ResponseStatusException(
      org.springframework.http.HttpStatus.BAD_REQUEST,
      "unsupported status"
    );
  }

  private void updateOr404(String sql, Object... args) {
    if (
      jdbc.update(sql, args) == 0
    ) throw new org.springframework.web.server.ResponseStatusException(
      org.springframework.http.HttpStatus.NOT_FOUND,
      "resource not found or already completed"
    );
  }
}
