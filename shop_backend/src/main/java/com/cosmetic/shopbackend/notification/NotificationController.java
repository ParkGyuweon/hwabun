package com.cosmetic.shopbackend.notification;

import com.cosmetic.shopbackend.security.ShopPrincipal;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Validated
@RequestMapping("/api/notifications")
public class NotificationController {

  private final NotificationService notifications;

  public NotificationController(NotificationService notifications) {
    this.notifications = notifications;
  }

  @GetMapping
  public Map<String, Object> list(
    @AuthenticationPrincipal ShopPrincipal actor,
    @RequestParam(defaultValue = "20") @Min(1) @Max(50) int limit
  ) {
    return notifications.notifications(actor, limit);
  }

  @GetMapping("/unread-count")
  public Map<String, Object> unreadCount(@AuthenticationPrincipal ShopPrincipal actor) {
    return notifications.unreadCount(actor);
  }

  @PatchMapping("/{notificationId}/read")
  public Map<String, Object> markRead(
    @AuthenticationPrincipal ShopPrincipal actor,
    @PathVariable String notificationId
  ) {
    return notifications.markRead(actor, notificationId);
  }

  @PatchMapping("/read-all")
  public Map<String, Object> markAllRead(@AuthenticationPrincipal ShopPrincipal actor) {
    return notifications.markAllRead(actor);
  }
}
