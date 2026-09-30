package com.cosmetic.shopbackend.feedback;

import com.cosmetic.shopbackend.brand.SellerBrandResolver;
import com.cosmetic.shopbackend.identity.AccountRole;
import com.cosmetic.shopbackend.notification.NotificationService;
import com.cosmetic.shopbackend.security.ShopPrincipal;
import tools.jackson.databind.ObjectMapper;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api")
public class FeedbackController {

  private static final Set<String> FEEDBACK_AXES = Set.of(
    "efficacy",
    "texture",
    "scent",
    "packaging",
    "value"
  );
  private final JdbcTemplate jdbc;
  private final ObjectMapper objectMapper;
  private final NotificationService notifications;
  private final SellerBrandResolver sellerBrands;
  public FeedbackController(
    JdbcTemplate jdbc,
    ObjectMapper objectMapper,
    NotificationService notifications,
    SellerBrandResolver sellerBrands
  ) {
    this.jdbc = jdbc;
    this.objectMapper = objectMapper;
    this.notifications = notifications;
    this.sellerBrands = sellerBrands;
  }

  @PostMapping("/reviews")
  @ResponseStatus(HttpStatus.CREATED)
  public Map<String, Object> createReview(
    @AuthenticationPrincipal ShopPrincipal actor,
    @Valid @RequestBody ReviewRequest req
  ) {
    requireRole(actor, AccountRole.MEMBER);
    String memberId = actor.accountId();
    String productId = purchasedOrderItemProductId(memberId, req.orderItemId());
    if (
      count(
        "select count(*) from review where order_item_id=?",
        req.orderItemId()
      ) > 0
    ) throw new ResponseStatusException(
      HttpStatus.CONFLICT,
      "review already exists"
    );
    String id = UUID.randomUUID().toString();
    jdbc.update(
      "insert into review(review_id,product_id,order_item_id,rating,is_recommended,title,body,skin_type_snapshot,skin_tone_snapshot,hair_color_snapshot,eye_color_snapshot) " +
        "select ?,?,?,?,?,?,?,m.skin_type_code,m.skin_tone_code,m.hair_color_code,m.eye_color_code from member m where m.member_id=?",
      id,
      productId,
      req.orderItemId(),
      req.rating(),
      req.isRecommended(),
      req.title(),
      req.body(),
      memberId
    );
    return Map.of("reviewId", id, "status", "PUBLISHED");
  }

  @GetMapping("/products/{productId}/reviews")
  public List<Map<String, Object>> reviews(@PathVariable String productId) {
    return jdbc.queryForList(
      "select r.review_id reviewId,r.rating,r.is_recommended isRecommended,r.title,r.body,r.created_at createdAt " +
        "from review r join order_item oi on oi.order_item_id=r.order_item_id join shop_order o on o.order_id=oi.order_id " +
        "join product p on p.product_id=oi.product_id join brand b on b.brand_id=p.brand_id " +
        "where oi.product_id=? and r.status='PUBLISHED' and p.status='ACTIVE' and b.status='ACTIVE' order by r.created_at desc",
      productId
    );
  }

  @GetMapping("/seller/reviews")
  public List<Map<String, Object>> sellerReviews(
    @AuthenticationPrincipal ShopPrincipal actor,
    @RequestParam(required = false) String brandId
  ) {
    String ownedBrandId = ownedBrandId(actor, brandId);
    return jdbc.queryForList(
      "select r.review_id reviewId,r.product_id productId,p.product_name productName, " +
        "r.order_item_id orderItemId,r.rating,r.is_recommended isRecommended, " +
        "r.title reviewTitle,r.body reviewText,coalesce(r.skin_type_snapshot,m.skin_type_code) skinType, " +
        "r.created_at submissionTime, " +
        "case when r.order_item_id is not null then true else false end isPurchaser " +
        "from review r join product p on p.product_id=r.product_id " +
        "left join order_item oi on oi.order_item_id=r.order_item_id " +
        "left join shop_order o on o.order_id=oi.order_id " +
        "left join member m on m.member_id=o.member_id " +
        "where p.brand_id=? and r.status='PUBLISHED' order by r.created_at desc",
      ownedBrandId
    );
  }

  @PostMapping("/feedback")
  @ResponseStatus(HttpStatus.CREATED)
  @Transactional
  public Map<String, Object> createFeedback(
    @AuthenticationPrincipal ShopPrincipal actor,
    @Valid @RequestBody FeedbackRequest req
  ) {
    requireRole(actor, AccountRole.MEMBER);
    String memberId = actor.accountId();
    String orderItemId = purchasedItemOrNull(memberId, req.productId());
    String axisId = normalizeAxisValue(req.axisId());
    if (
      count(
        "select count(*) from feedback where member_id=? and product_id=? and axis_id=?",
        memberId,
        req.productId(),
        axisId
      ) > 0
    ) throw new ResponseStatusException(
      HttpStatus.CONFLICT,
      "feedback already exists for this product axis"
    );
    String id = UUID.randomUUID().toString();
    jdbc.update(
      "insert into feedback(feedback_id,member_id,product_id,axis_id,order_item_id,body) values(?,?,?,?,?,?)",
      id,
      memberId,
      req.productId(),
      axisId,
      orderItemId,
      req.body()
    );
    jdbc.update(
      "insert into feedback_classification(feedback_id) values(?)",
      id
    );
    notifySellerOfFeedback(id, req.productId());
    return Map.of(
      "feedbackId",
      id,
      "productId",
      req.productId(),
      "axisId",
      axisId,
      "isPurchaser",
      orderItemId != null,
      "status",
      "VISIBLE",
      "classificationStatus",
      "PENDING"
    );
  }

  @PostMapping("/seller/feedback/{feedbackId}/responses")
  @ResponseStatus(HttpStatus.CREATED)
  @Transactional
  public Map<String, Object> respondToFeedback(
    @AuthenticationPrincipal ShopPrincipal actor,
    @PathVariable String feedbackId,
    @Valid @RequestBody FeedbackResponseRequest req
  ) {
    requireRole(actor, AccountRole.SELLER);
    ResponseAction action = ResponseAction.from(req.action());
    String body = normalizedBody(req.body());
    if (action == ResponseAction.REPLIED && body == null) {
      throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "reply body required");
    }
    if (action != ResponseAction.REPLIED && body != null) {
      throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "body is only allowed for REPLIED");
    }
    List<Map<String, Object>> feedbacks = jdbc.queryForList(
      "select f.member_id memberId,f.product_id productId,p.product_name productName " +
        "from feedback f join product p on p.product_id=f.product_id join brand b on b.brand_id=p.brand_id " +
        "where f.feedback_id=? and b.seller_account_id=? and f.status='VISIBLE'",
      feedbackId,
      actor.accountId()
    );
    if (feedbacks.isEmpty()) throw new ResponseStatusException(HttpStatus.FORBIDDEN, "feedback access denied");
    Map<String, Object> feedback = feedbacks.getFirst();
    String responseId = UUID.randomUUID().toString();
    String handlingStatus = action == ResponseAction.IMPLEMENTED ? "IMPLEMENTED" : "ACKNOWLEDGED";
    jdbc.update(
      "insert into feedback_response(feedback_response_id,feedback_id,seller_account_id,action,body) values(?,?,?,?,?)",
      responseId,
      feedbackId,
      actor.accountId(),
      action.name(),
      body
    );
    jdbc.update(
      "update feedback set handling_status=?,last_responded_at=current_timestamp(6) where feedback_id=?",
      handlingStatus,
      feedbackId
    );
    Map<String, Object> response = jdbc.queryForList(
      "select feedback_response_id feedbackResponseId,action,body,created_at createdAt from feedback_response where feedback_response_id=?",
      responseId
    ).getFirst();
    Object createdAt = response.get("createdAt");
    notifications.createFeedbackNotification(
      AccountRole.MEMBER,
      String.valueOf(feedback.get("memberId")),
      notificationType(action),
      feedbackId,
      String.valueOf(feedback.get("productId")),
      String.valueOf(feedback.get("productName")),
      notificationTitle(action),
      notificationBody(action, String.valueOf(feedback.get("productName")), body)
    );
    Map<String, Object> result = new LinkedHashMap<>();
    result.put("feedbackId", feedbackId);
    result.put("handlingStatus", handlingStatus);
    result.put("lastRespondedAt", createdAt);
    result.put("response", response);
    return result;
  }

  @GetMapping("/seller/feedback")
  public List<Map<String, Object>> sellerFeedback(
    @AuthenticationPrincipal ShopPrincipal actor,
    @RequestParam(required = false) String brandId
  ) {
    requireRole(actor, AccountRole.SELLER);
    String ownedBrandId = ownedBrandId(actor, brandId);
    /*
      * 브랜드 필터는 **상품(product.brand_id)** 으로 한다. 예전에는 `order_item` 을 inner join 해서
     * 걸렀는데, 미구매자 의견은 `order_item_id` 가 NULL 이라 그 조인에서 통째로 사라진다 —
     * 사장님이 "안 산 사람이 뭐라 했는지" 를 영영 볼 수 없었다.
     *
     * `purchased` 는 그 의견이 산 사람의 것인지. `order_item_id` 가 있으면 구매자다 (서버가 결제 완료
     * 주문에서만 그 값을 채운다). 상품명은 구매자면 주문 당시 스냅샷을, 아니면 현재 상품명을 쓴다.
     */
    List<Map<String, Object>> rows = jdbc.queryForList(
      "select f.feedback_id feedbackId,f.order_item_id orderItemId,f.product_id productId, " +
        "coalesce(oi.product_name_snapshot,p.product_name) productName, " +
        "case when f.order_item_id is not null then true else false end isPurchaser, " +
        "f.member_id authorMemberId, " +
        "m.skin_type_code authorSkinTypeCode,m.skin_tone_code authorSkinToneCode, " +
        "m.hair_color_code authorHairColorCode,m.eye_color_code authorEyeColorCode, " +
        "f.axis_id axisId,f.body,f.status,f.handling_status handlingStatus,f.last_responded_at lastRespondedAt,f.created_at createdAt, " +
        "latest.action latestResponseAction,latest.body latestResponseBody,latest.created_at latestResponseCreatedAt, " +
        "coalesce(fc.classification_status,'PENDING') classificationStatus,coalesce(fc.hidden_by_default,false) hiddenByDefault " +
        "from feedback f " +
        "join product p on p.product_id=f.product_id " +
        "left join order_item oi on oi.order_item_id=f.order_item_id and oi.product_id=f.product_id " +
        "left join member m on m.member_id=f.member_id " +
        "left join feedback_classification fc on fc.feedback_id=f.feedback_id " +
        "left join feedback_response latest on latest.feedback_response_id=(" +
          "select fr.feedback_response_id from feedback_response fr where fr.feedback_id=f.feedback_id order by fr.created_at desc,fr.feedback_response_id desc limit 1) " +
        "where p.brand_id=? and f.status='VISIBLE' order by f.created_at desc",
      ownedBrandId
    );
    for (Map<String, Object> row : rows) {
      Map<String, Object> latestResponse = null;
      if (row.get("latestResponseAction") != null) {
        latestResponse = new LinkedHashMap<>();
        latestResponse.put("action", row.remove("latestResponseAction"));
        latestResponse.put("body", row.remove("latestResponseBody"));
        latestResponse.put("createdAt", row.remove("latestResponseCreatedAt"));
      } else {
        row.remove("latestResponseAction");
        row.remove("latestResponseBody");
        row.remove("latestResponseCreatedAt");
      }
      row.put("latestResponse", latestResponse);
      Map<String, Object> classification = classification(
        String.valueOf(row.get("feedbackId"))
      );
      row.putAll(classification);
    }
    return rows;
  }

  private void notifySellerOfFeedback(String feedbackId, String productId) {
    List<Map<String, Object>> recipients = jdbc.queryForList(
      "select b.seller_account_id sellerAccountId,p.product_name productName from product p join brand b on b.brand_id=p.brand_id where p.product_id=?",
      productId
    );
    if (recipients.isEmpty()) throw new ResponseStatusException(HttpStatus.NOT_FOUND, "product not found");
    Map<String, Object> recipient = recipients.getFirst();
    String productName = String.valueOf(recipient.get("productName"));
    notifications.createFeedbackNotification(
      AccountRole.SELLER,
      String.valueOf(recipient.get("sellerAccountId")),
      "FEEDBACK_CREATED",
      feedbackId,
      productId,
      productName,
      "새 피드백이 등록되었어요",
      productName + "에 새 피드백이 등록되었습니다."
    );
  }

  private String normalizedBody(String value) {
    if (value == null || value.trim().isEmpty()) return null;
    return value.trim();
  }

  private String notificationType(ResponseAction action) {
    return switch (action) {
      case ACKNOWLEDGED -> "FEEDBACK_ACKNOWLEDGED";
      case REPLIED -> "FEEDBACK_REPLIED";
      case IMPLEMENTED -> "FEEDBACK_IMPLEMENTED";
    };
  }

  private String notificationTitle(ResponseAction action) {
    return switch (action) {
      case ACKNOWLEDGED -> "업체가 의견을 확인했어요";
      case REPLIED -> "업체가 답변을 남겼어요";
      case IMPLEMENTED -> "의견이 반영되었어요";
    };
  }

  private String notificationBody(ResponseAction action, String productName, String reply) {
    if (action == ResponseAction.REPLIED) return reply;
    return productName + (action == ResponseAction.IMPLEMENTED ? "의 개선 의견이 반영되었습니다." : "의 의견을 업체가 확인했습니다.");
  }

  private Map<String, Object> classification(String feedbackId) {
    List<Map<String, Object>> classifications = jdbc.queryForList(
      "select classification_status classificationStatus,primary_axis_id primaryAxisId,primary_category_id primaryCategoryId,off_axis_hint offAxisHint,classifier,vocab_version vocabVersion,classified_at classifiedAt,banned_terms_json bannedTermsJson,hidden_by_default hiddenByDefault from feedback_classification where feedback_id=?",
      feedbackId
    );
    if (classifications.isEmpty()) {
      Map<String, Object> pending = new LinkedHashMap<>();
      pending.put("labels", List.of());
      pending.put("primary", null);
      pending.put("offAxisHint", null);
      pending.put("classifier", null);
      pending.put("vocabVersion", null);
      pending.put("classifiedAt", null);
      pending.put("bannedTerms", List.of());
      pending.put("classificationStatus", "PENDING");
      pending.put("hiddenByDefault", false);
      return pending;
    }
    Map<String, Object> row = classifications.get(0);
    String status = String.valueOf(row.get("classificationStatus"));
    List<Map<String, Object>> labels = "COMPLETED".equals(status)
      ? jdbc.queryForList(
          "select axis_id axisId,category_id categoryId from feedback_classification_label where feedback_id=? order by axis_id,category_id",
          feedbackId
        )
      : List.of();
    Map<String, Object> primary = null;
    if (
      "COMPLETED".equals(status) && row.get("primaryCategoryId") != null
    ) primary = Map.of(
      "axisId",
      row.get("primaryAxisId"),
      "categoryId",
      row.get("primaryCategoryId")
    );
    List<String> bannedTerms = parseBannedTerms(row.get("bannedTermsJson"));
    Map<String, Object> result = new LinkedHashMap<>();
    result.put("labels", labels);
    result.put("primary", primary);
    result.put("offAxisHint", row.get("offAxisHint"));
    result.put("classifier", row.get("classifier"));
    result.put("vocabVersion", row.get("vocabVersion"));
    result.put("classifiedAt", row.get("classifiedAt"));
    result.put("bannedTerms", bannedTerms);
    result.put("classificationStatus", status);
    result.put("hiddenByDefault", booleanValue(row.get("hiddenByDefault")));
    return result;
  }

  private boolean booleanValue(Object value) {
    return (
      Boolean.TRUE.equals(value) ||
      (value instanceof Number number && number.intValue() != 0)
    );
  }

  private List<String> parseBannedTerms(Object raw) {
    if (raw == null) return List.of();
    try {
      return objectMapper.readValue(
        raw.toString(),
        objectMapper
          .getTypeFactory()
          .constructCollectionType(List.class, String.class)
      );
    } catch (Exception ignored) {
      return List.of();
    }
  }

  /**
   * 이 회원이 그 상품을 산 적이 있으면 가장 최근 결제 품목, 아니면 **null**.
   *
   * 예전에는 없으면 403 이었다. 그래서 미구매자의 의견은 사장님에게 영영 닿지 않았다 — 제품을 아직 안
   * 샀지만 살까 말까 하며 묻고 싶은 사람이 가장 많은데 그 말이 통째로 막혀 있었다.
   * 이제 누구나 보낼 수 있고, 산 사람인지는 이 값이 있는지로 구분해 사장님 화면이 배지로 적는다.
   */
  private String purchasedItemOrNull(String memberId, String productId) {
    List<String> itemIds = jdbc.query(
      "select oi.order_item_id from order_item oi join shop_order o on o.order_id=oi.order_id " +
        "where oi.product_id=? and o.member_id=? and o.status='PAID' order by o.paid_at desc",
      (rs, rowNum) -> rs.getString("order_item_id"),
      productId,
      memberId
    );
    return itemIds.isEmpty() ? null : itemIds.get(0);
  }

  private String purchasedOrderItemProductId(String memberId, String itemId) {
    List<String> productIds = jdbc.query(
      "select oi.product_id from order_item oi join shop_order o on o.order_id=oi.order_id " +
        "where oi.order_item_id=? and o.member_id=? and o.status='PAID'",
      (rs, rowNum) -> rs.getString("product_id"),
      itemId,
      memberId
    );
    if (productIds.isEmpty()) throw new ResponseStatusException(
      HttpStatus.FORBIDDEN,
      "paid purchase required"
    );
    return productIds.get(0);
  }

  private String ownedBrandId(ShopPrincipal actor, String requestedBrandId) {
    requireRole(actor, AccountRole.SELLER);
    String ownedBrandId = sellerBrands.brandIdOf(actor);
    if (requestedBrandId != null && !requestedBrandId.isBlank() &&
      !ownedBrandId.equals(requestedBrandId)) {
      throw new ResponseStatusException(HttpStatus.FORBIDDEN, "brand access denied");
    }
    return ownedBrandId;
  }

  private int count(String sql, Object... args) {
    return jdbc.queryForObject(sql, Integer.class, args);
  }

  static String normalizeAxisValue(String value) {
    String axis = value == null ? "" : value.trim().toLowerCase(Locale.ROOT);
    if (!FEEDBACK_AXES.contains(axis)) throw new ResponseStatusException(
      HttpStatus.BAD_REQUEST,
      "unsupported feedback axis"
    );
    return axis;
  }

  private void requireRole(ShopPrincipal actor, AccountRole expected) {
    if (
      actor == null || actor.role() != expected
    ) throw new ResponseStatusException(
      HttpStatus.FORBIDDEN,
      "required role: " + expected
    );
  }

  public record ReviewRequest(
    @NotBlank String orderItemId,
    @Min(1) @Max(5) int rating,
    Boolean isRecommended,
    String title,
    String body
  ) {}

  public record FeedbackRequest(
    @NotBlank String productId,
    @NotBlank String axisId,
    @NotBlank String body
  ) {}

  public record FeedbackResponseRequest(@NotBlank String action, @Size(max = 1000) String body) {}

  private enum ResponseAction {
    ACKNOWLEDGED,
    REPLIED,
    IMPLEMENTED;

    static ResponseAction from(String value) {
      try {
        return valueOf(value.trim().toUpperCase(Locale.ROOT));
      } catch (Exception exception) {
        throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "unsupported feedback response action");
      }
    }
  }
}
