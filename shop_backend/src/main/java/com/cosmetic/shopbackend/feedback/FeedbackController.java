package com.cosmetic.shopbackend.feedback;

import com.cosmetic.shopbackend.identity.AccountRole;
import com.cosmetic.shopbackend.security.ShopPrincipal;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.*;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.server.ResponseStatusException;

import java.util.List;
import java.util.Map;
import java.util.UUID;

@RestController
@RequestMapping("/api")
public class FeedbackController {
    private final JdbcTemplate jdbc;
    public FeedbackController(JdbcTemplate jdbc) { this.jdbc = jdbc; }

    @PostMapping("/reviews")
    @ResponseStatus(HttpStatus.CREATED)
    public Map<String,Object> createReview(@AuthenticationPrincipal ShopPrincipal actor,
                                            @Valid @RequestBody ReviewRequest req) {
        requireRole(actor, AccountRole.MEMBER);
        String memberId = actor.accountId();
        purchased(memberId, req.orderItemId());
        if (count("select count(*) from review where order_item_id=?", req.orderItemId()) > 0)
            throw new ResponseStatusException(HttpStatus.CONFLICT, "review already exists");
        String id = UUID.randomUUID().toString();
        jdbc.update("insert into review(review_id,order_item_id,rating,is_recommended,title,body) values(?,?,?,?,?,?)",
                id, req.orderItemId(), req.rating(), req.isRecommended(), req.title(), req.body());
        return Map.of("reviewId", id, "status", "PUBLISHED");
    }

    @GetMapping("/products/{productId}/reviews")
    public List<Map<String,Object>> reviews(@PathVariable String productId) {
        return jdbc.queryForList("select r.review_id reviewId,r.rating,r.is_recommended isRecommended,r.title,r.body,r.created_at createdAt " +
                "from review r join order_item oi on oi.order_item_id=r.order_item_id join shop_order o on o.order_id=oi.order_id " +
                "where oi.product_id=? and r.status='PUBLISHED' order by r.created_at desc", productId);
    }

    @PostMapping("/feedback")
    @ResponseStatus(HttpStatus.CREATED)
    public Map<String,Object> createFeedback(@AuthenticationPrincipal ShopPrincipal actor,
                                              @Valid @RequestBody FeedbackRequest req) {
        requireRole(actor, AccountRole.MEMBER);
        String memberId = actor.accountId();
        purchased(memberId, req.orderItemId());
        if (count("select count(*) from feedback where order_item_id=?", req.orderItemId()) > 0)
            throw new ResponseStatusException(HttpStatus.CONFLICT, "feedback already exists");
        String id = UUID.randomUUID().toString();
        jdbc.update("insert into feedback(feedback_id,order_item_id,body) values(?,?,?)", id, req.orderItemId(), req.body());
        return Map.of("feedbackId", id, "status", "VISIBLE");
    }

    @GetMapping("/seller/feedback")
    public List<Map<String,Object>> sellerFeedback(@AuthenticationPrincipal ShopPrincipal actor,
                                                    @RequestParam String brandId) {
        requireRole(actor, AccountRole.SELLER);
        String sellerId = actor.accountId();
        owns(sellerId, brandId);
        return jdbc.queryForList("select f.feedback_id feedbackId,f.order_item_id orderItemId,f.body,f.status,f.created_at createdAt " +
                "from feedback f join order_item oi on oi.order_item_id=f.order_item_id where oi.brand_id=? and f.status='VISIBLE' order by f.created_at desc", brandId);
    }

    private void purchased(String memberId, String itemId) {
        if (count("select count(*) from order_item oi join shop_order o on o.order_id=oi.order_id where oi.order_item_id=? and o.member_id=? and o.status='PAID'", itemId, memberId) == 0)
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "paid purchase required");
    }
    private void owns(String sellerId, String brandId) {
        if (count("select count(*) from brand where brand_id=? and seller_account_id=?", brandId, sellerId) == 0)
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "brand access denied");
    }
    private int count(String sql, Object... args) { return jdbc.queryForObject(sql, Integer.class, args); }
    private void requireRole(ShopPrincipal actor, AccountRole expected) { if (actor == null || actor.role() != expected) throw new ResponseStatusException(HttpStatus.FORBIDDEN, "required role: " + expected); }
    public record ReviewRequest(@NotBlank String orderItemId, @Min(1) @Max(5) int rating, Boolean isRecommended, String title, String body) {}
    public record FeedbackRequest(@NotBlank String orderItemId, @NotBlank String body) {}
}
