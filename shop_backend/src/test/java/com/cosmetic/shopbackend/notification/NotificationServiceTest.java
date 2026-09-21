package com.cosmetic.shopbackend.notification;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.cosmetic.shopbackend.identity.AccountRole;
import com.cosmetic.shopbackend.security.ShopPrincipal;
import java.util.List;
import java.util.LinkedHashMap;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.server.ResponseStatusException;

class NotificationServiceTest {

  private JdbcTemplate jdbc;
  private NotificationService service;

  @BeforeEach
  void setUp() {
    jdbc = org.mockito.Mockito.mock(JdbcTemplate.class);
    service = new NotificationService(
      jdbc,
      new tools.jackson.databind.ObjectMapper()
    );
  }

  @Test
  void listsOnlyTheAuthenticatedRecipientAndDecodesPayload() {
    Map<String, Object> notification = new LinkedHashMap<>();
    notification.put("notificationId", "n-1");
    notification.put("payloadJson", "{\"productId\":\"p-1\",\"productName\":\"크림\"}");
    when(jdbc.queryForList(anyString(), any(Object[].class))).thenReturn(List.of(notification));

    Map<String, Object> result = service.notifications(
      new ShopPrincipal("member-1", AccountRole.MEMBER),
      20
    );

    List<?> items = (List<?>) result.get("items");
    Map<?, ?> item = (Map<?, ?>) items.getFirst();
    assertEquals(Map.of("productId", "p-1", "productName", "크림"), item.get("payload"));
    verify(jdbc).queryForList(anyString(), eq("MEMBER"), eq("member-1"), eq(20));
  }

  @Test
  void cannotMarkAnotherRecipientsNotificationAsRead() {
    Map<String, Object> otherRecipient = new LinkedHashMap<>();
    otherRecipient.put("recipientRole", "MEMBER");
    otherRecipient.put("recipientAccountId", "member-2");
    otherRecipient.put("readAt", null);
    when(jdbc.queryForList(anyString(), any(Object[].class))).thenReturn(List.of(otherRecipient));

    ResponseStatusException exception = assertThrows(
      ResponseStatusException.class,
      () -> service.markRead(
        new ShopPrincipal("member-1", AccountRole.MEMBER),
        "n-1"
      )
    );

    assertEquals(403, exception.getStatusCode().value());
    verify(jdbc, never()).update(anyString(), any(Object[].class));
  }

  @Test
  void marksAllNotificationsForTheAuthenticatedRecipient() {
    when(jdbc.update(anyString(), eq("SELLER"), eq("seller-1"))).thenReturn(3);

    Map<String, Object> result = service.markAllRead(
      new ShopPrincipal("seller-1", AccountRole.SELLER)
    );

    assertEquals(3, result.get("updatedCount"));
    verify(jdbc).update(anyString(), eq("SELLER"), eq("seller-1"));
  }
}
