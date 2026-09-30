package com.cosmetic.shopbackend.feedback;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

import com.cosmetic.shopbackend.identity.AccountRole;
import com.cosmetic.shopbackend.notification.NotificationService;
import com.cosmetic.shopbackend.security.ShopPrincipal;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;

class FeedbackResponseControllerTest {

  @Test
  void recordsReplyUpdatesHandlingStatusAndNotifiesTheMember() {
    JdbcTemplate jdbc = mock(JdbcTemplate.class);
    NotificationService notifications = mock(NotificationService.class);
    FeedbackController controller = new FeedbackController(
      jdbc,
      new tools.jackson.databind.ObjectMapper(),
      notifications,
      new com.cosmetic.shopbackend.brand.SellerBrandResolver(
        mock(com.cosmetic.shopbackend.brand.BrandRepository.class)
      )
    );

    doAnswer(invocation -> {
      String sql = invocation.getArgument(0, String.class);
      if (sql.startsWith("select f.member_id")) {
        return List.of(Map.of(
          "memberId", "member-1",
          "productId", "product-1",
          "productName", "수분 크림"
        ));
      }
      Map<String, Object> response = new LinkedHashMap<>();
      response.put("feedbackResponseId", "response-1");
      response.put("action", "REPLIED");
      response.put("body", "답변입니다");
      response.put("createdAt", "2026-09-18T10:00:00");
      return List.of(response);
    }).when(jdbc).queryForList(anyString(), any(Object[].class));

    Map<String, Object> result = controller.respondToFeedback(
      new ShopPrincipal("seller-1", AccountRole.SELLER, "brand-1"),
      "feedback-1",
      new FeedbackController.FeedbackResponseRequest("replied", " 답변입니다 ")
    );

    assertEquals("ACKNOWLEDGED", result.get("handlingStatus"));
    assertEquals("REPLIED", ((Map<?, ?>) result.get("response")).get("action"));
    verify(notifications).createFeedbackNotification(
      eq(AccountRole.MEMBER),
      eq("member-1"),
      eq("FEEDBACK_REPLIED"),
      eq("feedback-1"),
      eq("product-1"),
      eq("수분 크림"),
      eq("업체가 답변을 남겼어요"),
      eq("답변입니다")
    );
  }
}
