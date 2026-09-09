package com.cosmetic.shopbackend.feedback;

import com.cosmetic.shopbackend.identity.AccountRole;
import com.cosmetic.shopbackend.security.ShopPrincipal;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
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

  public FeedbackController(JdbcTemplate jdbc, ObjectMapper objectMapper) {
    this.jdbc = jdbc;
    this.objectMapper = objectMapper;
  }

  @PostMapping("/reviews")
  @ResponseStatus(HttpStatus.CREATED)
  public Map<String, Object> createReview(
    @AuthenticationPrincipal ShopPrincipal actor,
    @Valid @RequestBody ReviewRequest req
  ) {
    requireRole(actor, AccountRole.MEMBER);
    String memberId = actor.accountId();
    purchasedOrderItem(memberId, req.orderItemId());
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
      "insert into review(review_id,order_item_id,rating,is_recommended,title,body) values(?,?,?,?,?,?)",
      id,
      req.orderItemId(),
      req.rating(),
      req.isRecommended(),
      req.title(),
      req.body()
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

  @PostMapping("/feedback")
  @ResponseStatus(HttpStatus.CREATED)
  @Transactional
  public Map<String, Object> createFeedback(
    @AuthenticationPrincipal ShopPrincipal actor,
    @Valid @RequestBody FeedbackRequest req
  ) {
    requireRole(actor, AccountRole.MEMBER);
    String memberId = actor.accountId();
    String orderItemId = purchased(memberId, req.productId());
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
    return Map.of(
      "feedbackId",
      id,
      "productId",
      req.productId(),
      "axisId",
      axisId,
      "status",
      "VISIBLE",
      "classificationStatus",
      "PENDING"
    );
  }

  @GetMapping("/seller/feedback")
  public List<Map<String, Object>> sellerFeedback(
    @AuthenticationPrincipal ShopPrincipal actor,
    @RequestParam String brandId
  ) {
    requireRole(actor, AccountRole.SELLER);
    String sellerId = actor.accountId();
    owns(sellerId, brandId);
    List<Map<String, Object>> rows = jdbc.queryForList(
      "select f.feedback_id feedbackId,f.order_item_id orderItemId,f.product_id productId, " +
        "oi.product_name_snapshot productName,f.member_id authorMemberId, " +
        "m.skin_type_code authorSkinTypeCode,m.skin_tone_code authorSkinToneCode, " +
        "m.hair_color_code authorHairColorCode,m.eye_color_code authorEyeColorCode, " +
        "f.axis_id axisId,f.body,f.status,f.created_at createdAt, " +
        "coalesce(fc.classification_status,'PENDING') classificationStatus,coalesce(fc.hidden_by_default,false) hiddenByDefault " +
        "from feedback f join order_item oi on oi.order_item_id=f.order_item_id " +
        "left join member m on m.member_id=f.member_id " +
        "left join feedback_classification fc on fc.feedback_id=f.feedback_id " +
        "where oi.brand_id=? and f.product_id=oi.product_id and f.status='VISIBLE' order by f.created_at desc",
      brandId
    );
    for (Map<String, Object> row : rows) {
      Map<String, Object> classification = classification(
        String.valueOf(row.get("feedbackId"))
      );
      row.putAll(classification);
    }
    return rows;
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

  private String purchased(String memberId, String productId) {
    List<String> itemIds = jdbc.query(
      "select oi.order_item_id from order_item oi join shop_order o on o.order_id=oi.order_id " +
        "where oi.product_id=? and o.member_id=? and o.status='PAID' order by o.paid_at desc",
      (rs, rowNum) -> rs.getString("order_item_id"),
      productId,
      memberId
    );
    if (itemIds.isEmpty()) throw new ResponseStatusException(
      HttpStatus.FORBIDDEN,
      "paid purchase required"
    );
    return itemIds.get(0);
  }

  private void purchasedOrderItem(String memberId, String itemId) {
    if (
      count(
        "select count(*) from order_item oi join shop_order o on o.order_id=oi.order_id where oi.order_item_id=? and o.member_id=? and o.status='PAID'",
        itemId,
        memberId
      ) == 0
    ) throw new ResponseStatusException(
      HttpStatus.FORBIDDEN,
      "paid purchase required"
    );
  }

  private void owns(String sellerId, String brandId) {
    if (
      count(
        "select count(*) from brand where brand_id=? and seller_account_id=?",
        brandId,
        sellerId
      ) == 0
    ) throw new ResponseStatusException(
      HttpStatus.FORBIDDEN,
      "brand access denied"
    );
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
}
