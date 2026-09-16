package com.cosmetic.shopbackend.payment;

import com.cosmetic.shopbackend.identity.AccountRole;
import com.cosmetic.shopbackend.security.ShopPrincipal;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/orders")
public class PaymentController {

  private final PaymentConfirmationService confirmations;

  public PaymentController(PaymentConfirmationService confirmations) {
    this.confirmations = confirmations;
  }

  public record ConfirmRequest(@NotBlank String paymentId) {}

  @PostMapping("/{orderId}/confirm")
  public PaymentConfirmationService.Confirmation confirm(
    @AuthenticationPrincipal ShopPrincipal actor,
    @PathVariable String orderId,
    @Valid @RequestBody ConfirmRequest request
  ) {
    if (actor == null || actor.role() != AccountRole.MEMBER) {
      throw new ResponseStatusException(HttpStatus.FORBIDDEN, "member role required");
    }
    return confirmations.confirm(orderId, actor.accountId(), request.paymentId());
  }
}
