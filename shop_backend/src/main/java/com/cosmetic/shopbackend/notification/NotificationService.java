package com.cosmetic.shopbackend.notification;

import com.cosmetic.shopbackend.identity.AccountRole;
import com.cosmetic.shopbackend.security.ShopPrincipal;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;
import tools.jackson.databind.ObjectMapper;

/** 피드백 알림의 저장, 수신자 검증, 읽음 처리를 한곳에 둔다. */
@Service
public class NotificationService {

  private final JdbcTemplate jdbc;
  private final ObjectMapper objectMapper;

  public NotificationService(JdbcTemplate jdbc, ObjectMapper objectMapper) {
    this.jdbc = jdbc;
    this.objectMapper = objectMapper;
  }

  public void createFeedbackNotification(
    AccountRole recipientRole,
    String recipientAccountId,
    String type,
    String feedbackId,
    String productId,
    String productName,
    String title,
    String body
  ) {
    if (recipientRole != AccountRole.MEMBER && recipientRole != AccountRole.SELLER) {
      throw new IllegalArgumentException("notification recipient must be member or seller");
    }
    jdbc.update(
      "insert into notification(notification_id,recipient_role,recipient_account_id,type,feedback_id,title,body,payload_json) values(?,?,?,?,?,?,?,?)",
      UUID.randomUUID().toString(),
      recipientRole.name(),
      recipientAccountId,
      type,
      feedbackId,
      title,
      body,
      payload(productId, productName)
    );
  }

  public Map<String, Object> notifications(ShopPrincipal actor, int limit) {
    Recipient recipient = recipient(actor);
    List<Map<String, Object>> rows = jdbc.queryForList(
      "select notification_id notificationId,type,feedback_id feedbackId,title,body,payload_json payloadJson,read_at readAt,created_at createdAt " +
        "from notification where recipient_role=? and recipient_account_id=? order by created_at desc,notification_id desc limit ?",
      recipient.role(),
      recipient.accountId(),
      limit
    );
    for (Map<String, Object> row : rows) {
      row.put("payload", payloadMap(row.remove("payloadJson")));
    }
    return Map.of("items", rows);
  }

  public Map<String, Object> unreadCount(ShopPrincipal actor) {
    Recipient recipient = recipient(actor);
    Integer count = jdbc.queryForObject(
      "select count(*) from notification where recipient_role=? and recipient_account_id=? and read_at is null",
      Integer.class,
      recipient.role(),
      recipient.accountId()
    );
    return Map.of("count", count == null ? 0 : count);
  }

  @Transactional
  public Map<String, Object> markRead(ShopPrincipal actor, String notificationId) {
    Recipient recipient = recipient(actor);
    List<Map<String, Object>> rows = jdbc.queryForList(
      "select recipient_role recipientRole,recipient_account_id recipientAccountId,read_at readAt from notification where notification_id=?",
      notificationId
    );
    if (rows.isEmpty()) throw new ResponseStatusException(HttpStatus.NOT_FOUND, "notification not found");
    Map<String, Object> row = rows.getFirst();
    if (
      !recipient.role().equals(row.get("recipientRole")) ||
      !recipient.accountId().equals(row.get("recipientAccountId"))
    ) throw new ResponseStatusException(HttpStatus.FORBIDDEN, "notification access denied");
    jdbc.update(
      "update notification set read_at=coalesce(read_at,current_timestamp(6)) where notification_id=?",
      notificationId
    );
    Map<String, Object> updated = jdbc.queryForList(
      "select notification_id notificationId,read_at readAt from notification where notification_id=?",
      notificationId
    ).getFirst();
    return updated;
  }

  @Transactional
  public Map<String, Object> markAllRead(ShopPrincipal actor) {
    Recipient recipient = recipient(actor);
    int updated = jdbc.update(
      "update notification set read_at=current_timestamp(6) where recipient_role=? and recipient_account_id=? and read_at is null",
      recipient.role(),
      recipient.accountId()
    );
    return Map.of("updatedCount", updated);
  }

  private String payload(String productId, String productName) {
    try {
      return objectMapper.writeValueAsString(Map.of("productId", productId, "productName", productName));
    } catch (Exception exception) {
      throw new IllegalStateException("notification payload serialization failed", exception);
    }
  }

  @SuppressWarnings("unchecked")
  private Map<String, Object> payloadMap(Object raw) {
    if (raw == null) return Map.of();
    try {
      return objectMapper.readValue(raw.toString(), Map.class);
    } catch (Exception ignored) {
      return Map.of();
    }
  }

  private Recipient recipient(ShopPrincipal actor) {
    if (actor == null || actor.accountId() == null) {
      throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "authentication required");
    }
    if (actor.role() != AccountRole.MEMBER && actor.role() != AccountRole.SELLER) {
      throw new ResponseStatusException(HttpStatus.FORBIDDEN, "member or seller role required");
    }
    return new Recipient(actor.role().name(), actor.accountId());
  }

  private record Recipient(String role, String accountId) {}
}
