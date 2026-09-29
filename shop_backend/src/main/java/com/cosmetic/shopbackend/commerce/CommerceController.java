package com.cosmetic.shopbackend.commerce;

import com.cosmetic.shopbackend.brand.BrandRepository;
import com.cosmetic.shopbackend.brand.BrandStatus;
import com.cosmetic.shopbackend.catalog.Product;
import com.cosmetic.shopbackend.catalog.ProductRepository;
import com.cosmetic.shopbackend.catalog.ProductVariant;
import com.cosmetic.shopbackend.catalog.ProductVariantRepository;
import com.cosmetic.shopbackend.identity.AccountRole;
import com.cosmetic.shopbackend.security.ShopPrincipal;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api")
public class CommerceController {

  private final CartRepository carts;
  private final CartItemRepository cartItems;
  private final ProductVariantRepository variants;
  private final ProductRepository products;
  private final ShopOrderRepository orders;
  private final OrderItemRepository orderItems;
  private final BrandRepository brands;
  private final JdbcTemplate jdbc;

  /**
   * 결제 없이 PAID 로 표시하는 테스트 주문(`POST /orders/{id}/pay`)을 허용할 회원 ID 접두.
   *
   * 이 경로는 원래 결제 연동이 없던 시절의 길인데, 지금은 **에이전트 러너 전용**이다. PA 러너
   * (Playwright)는 카카오페이 창을 넘을 수 없어(카카오 로그인·QR 승인) 이 길로 주문을 끝내고,
   * 그래야 재구매 지표("같은 사람·같은 상품·다른 주문 2건")가 잡힌다.
   *
   * **프론트의 `?pay=test`·`navigator.webdriver` 판정은 보호 장치가 아니다.** 로그인한 사람이면
   * 누구나 토큰으로 이 엔드포인트를 직접 부를 수 있다. 실제 차단은 여기서 한다.
   *
   * 값은 러너 계정의 `member_id` 접두다 (`PA00001`~`PA00100`, 시드 `shop_backend_seed.sql`).
   * 빈 값이면 **아무도 통과하지 못한다**(닫힌 채로 실패). 설정이 빠진 배포가 모든 회원에게
   * 테스트 결제를 열어 주면 안 되기 때문이다. 로컬 개발도 application.yml 기본값 `PA` 로 돈다.
   */
  @Value("${shop.test-pay.allowed-member-prefix:PA}")
  private String testPayAllowedMemberPrefix;

  public CommerceController(
    CartRepository carts,
    CartItemRepository cartItems,
    ProductVariantRepository variants,
    ProductRepository products,
    ShopOrderRepository orders,
    OrderItemRepository orderItems,
    BrandRepository brands,
    JdbcTemplate jdbc
  ) {
    this.carts = carts;
    this.cartItems = cartItems;
    this.variants = variants;
    this.products = products;
    this.orders = orders;
    this.orderItems = orderItems;
    this.brands = brands;
    this.jdbc = jdbc;
  }

  public record CartRequest(String variantId, int quantity) {}

  public record OrderRequest(String idempotencyKey) {}

  public record OrderResponse(
    String orderId,
    String status,
    BigDecimal totalAmount,
    BigDecimal paidAmount,
    String currency,
    String paymentId,
    String paymentProvider,
    java.time.LocalDateTime paidAt,
    java.time.LocalDateTime createdAt,
    int itemCount,
    /**
     * 주문에 든 품목. 리뷰를 쓰려면 `POST /api/reviews` 가 `orderItemId` 를 요구하는데, 주문 목록이
     * 주문 단위 합계만 주고 있어서 화면이 그 값을 알 방법이 없었다 — 산 사람이 리뷰를 못 쓰고 있었다.
     */
    List<OrderItemResponse> items
  ) {}

  /** `reviewed` 는 이미 리뷰를 쓴 품목인지. 한 품목에 리뷰는 하나다(서버가 409 로 막는다) */
  public record OrderItemResponse(
    String orderItemId,
    String productId,
    String productName,
    String variantLabel,
    int quantity,
    BigDecimal lineAmount,
    boolean reviewed
  ) {}

  @GetMapping("/orders")
  public List<OrderResponse> orders(@AuthenticationPrincipal ShopPrincipal actor) {
    requireMember(actor);
    String memberId = actor.accountId();

    /*
     * 품목을 같이 내려 준다. 리뷰를 쓰려면 `POST /api/reviews` 가 `orderItemId` 를 요구하는데 주문 목록이
     * 주문 단위 합계(itemCount)만 주고 있어서, 화면이 "무엇을 리뷰할 수 있는지" 를 알 방법이 없었다.
     * 산 사람이 리뷰를 못 쓰고 있던 것이 이것 때문이다.
     *
     * 주문마다 따로 부르지 않고 한 번에 읽어 메모리에서 묶는다 (따로 부르면 N+1).
     * `reviewed` 는 이미 쓴 품목인지 — 한 품목에 리뷰는 하나이고 서버가 409 로 막는다.
     */
    Map<String, List<OrderItemResponse>> itemsByOrder = new LinkedHashMap<>();
    jdbc
      .query(
        """
        select oi.order_id,oi.order_item_id,oi.product_id,oi.product_name_snapshot,
               oi.variant_label_snapshot,oi.quantity,oi.line_amount,
               case when r.review_id is null then 0 else 1 end reviewed
        from order_item oi
        join shop_order o on o.order_id=oi.order_id
        left join review r on r.order_item_id=oi.order_item_id
        where o.member_id=? and o.status='PAID'
        order by oi.order_id,oi.order_item_id
        """,
        (rs, rowNum) ->
          Map.entry(
            rs.getString("order_id"),
            new OrderItemResponse(
              rs.getString("order_item_id"),
              rs.getString("product_id"),
              rs.getString("product_name_snapshot"),
              rs.getString("variant_label_snapshot"),
              rs.getInt("quantity"),
              rs.getBigDecimal("line_amount"),
              rs.getInt("reviewed") == 1
            )
          ),
        memberId
      )
      .forEach(entry -> itemsByOrder.computeIfAbsent(entry.getKey(), k -> new ArrayList<>()).add(entry.getValue()));

    return jdbc.query(
      """
      select o.order_id,o.status,o.total_amount,o.paid_amount,o.currency,
             o.payment_id,o.payment_provider,o.paid_at,o.created_at,
             coalesce(sum(oi.quantity),0) item_count
      from shop_order o
      left join order_item oi on oi.order_id=o.order_id
      where o.member_id=? and o.status='PAID'
      group by o.order_id,o.status,o.total_amount,o.paid_amount,o.currency,
               o.payment_id,o.payment_provider,o.paid_at,o.created_at
      order by o.created_at desc
      """,
      (rs, rowNum) -> new OrderResponse(
        rs.getString("order_id"),
        rs.getString("status"),
        rs.getBigDecimal("total_amount"),
        rs.getBigDecimal("paid_amount"),
        rs.getString("currency"),
        rs.getString("payment_id"),
        rs.getString("payment_provider"),
        rs.getObject("paid_at", java.time.LocalDateTime.class),
        rs.getObject("created_at", java.time.LocalDateTime.class),
        rs.getInt("item_count"),
        itemsByOrder.getOrDefault(rs.getString("order_id"), List.of())
      ),
      memberId
    );
  }

  @GetMapping("/cart")
  public Map<String, Object> view(
    @AuthenticationPrincipal ShopPrincipal actor
  ) {
    requireMember(actor);
    Cart cart = cart(actor.accountId());
    return Map.of(
      "cartId",
      cart.getId(),
      "items",
      cartItems.findByCartId(cart.getId())
    );
  }

  @PostMapping("/cart/items")
  @Transactional
  public ResponseEntity<?> add(
    @AuthenticationPrincipal ShopPrincipal actor,
    @RequestBody CartRequest request
  ) {
    requireMember(actor);
    if (request.quantity() < 1 || request.variantId() == null) {
      return ResponseEntity.badRequest().body("invalid cart item");
    }
    if (activeVariant(request.variantId()).isEmpty()) {
      return ResponseEntity.status(HttpStatus.CONFLICT).body(
        "inactive or unavailable product"
      );
    }

    Cart cart = cart(actor.accountId());
    cartItems.addQuantity(
      UUID.randomUUID().toString(),
      cart.getId(),
      request.variantId(),
      request.quantity()
    );
    return ResponseEntity.ok(
      cartItems
        .findByCartIdAndVariantId(cart.getId(), request.variantId())
        .orElseThrow()
    );
  }

  @DeleteMapping("/cart/items/{id}")
  public ResponseEntity<?> remove(
    @AuthenticationPrincipal ShopPrincipal actor,
    @PathVariable String id
  ) {
    requireMember(actor);
    return cartItems
      .findById(id)
      .filter(item ->
        carts
          .findById(item.getCartId())
          .map(cart -> cart.getMemberId().equals(actor.accountId()))
          .orElse(false)
      )
      .map(item -> {
        cartItems.delete(item);
        return ResponseEntity.noContent().build();
      })
      .orElseGet(() -> ResponseEntity.notFound().build());
  }

  @PostMapping("/orders")
  @Transactional
  public ResponseEntity<?> order(
    @AuthenticationPrincipal ShopPrincipal actor,
    @RequestBody OrderRequest request
  ) {
    requireMember(actor);
    if (
      request.idempotencyKey() == null || request.idempotencyKey().isBlank()
    ) {
      return ResponseEntity.badRequest().build();
    }

    Optional<ShopOrder> existing = orders.findByMemberIdAndIdempotencyKey(
      actor.accountId(),
      request.idempotencyKey()
    );
    if (existing.isPresent()) {
      List<CartItem> retryItems = carts
        .findByMemberId(actor.accountId())
        .map(cart -> cartItems.findByCartId(cart.getId()))
        .orElseGet(List::of);
      if (
        !retryItems.isEmpty() &&
        !existing.get().getRequestHash().equals(hash(retryItems))
      ) {
        return ResponseEntity.status(HttpStatus.CONFLICT).body(
          "idempotency key reused with different cart"
        );
      }
      return ResponseEntity.ok(orderView(existing.get()));
    }

    Cart cart = cart(actor.accountId());
    List<CartItem> items = cartItems.findByCartId(cart.getId());
    if (items.isEmpty()) {
      return ResponseEntity.badRequest().body("cart is empty");
    }

    String orderId = UUID.randomUUID().toString();
    BigDecimal total = BigDecimal.ZERO;
    List<OrderItem> snapshots = new ArrayList<>();
    for (CartItem cartItem : items) {
      ProductVariant variant = activeVariant(
        cartItem.getVariantId()
      ).orElseThrow(() ->
        new ResponseStatusException(
          HttpStatus.CONFLICT,
          "inactive or unavailable product"
        )
      );
      Product product = products.findById(variant.getProductId()).orElseThrow();
      String brandName = brands
        .findById(product.getBrandId())
        .map(brand -> brand.getName())
        .orElseThrow(() ->
          new ResponseStatusException(HttpStatus.CONFLICT, "brand unavailable")
        );
      BigDecimal lineAmount = variant
        .unitPrice()
        .multiply(BigDecimal.valueOf(cartItem.getQuantity()));
      total = total.add(lineAmount);
      snapshots.add(
        new OrderItem(
          UUID.randomUUID().toString(),
          orderId,
          variant.getId(),
          product.getId(),
          product.getBrandId(),
          product.getName(),
          brandName,
          variant.getSku(),
          variant.getLabel(),
          variant.unitPrice(),
          cartItem.getQuantity()
        )
      );
    }

    ShopOrder order = orders.save(
      new ShopOrder(
        orderId,
        actor.accountId(),
        request.idempotencyKey(),
        hash(items),
        total
      )
    );
    orderItems.saveAll(snapshots);
    cartItems.deleteByCartId(cart.getId());
    return ResponseEntity.status(HttpStatus.CREATED).body(orderView(order));
  }

  @PostMapping("/orders/{id}/pay")
  @Transactional
  public ResponseEntity<?> pay(
    @AuthenticationPrincipal ShopPrincipal actor,
    @PathVariable String id
  ) {
    requireMember(actor);
    requireTestPayAllowed(actor);
    Optional<ShopOrder> order = orders.findById(id);
    if (
      order.isEmpty() || !order.get().getMemberId().equals(actor.accountId())
    ) return ResponseEntity.notFound().build();
    orders.markPaid(
      id,
      actor.accountId(),
      java.time.LocalDateTime.now(java.time.ZoneId.of("Asia/Seoul"))
    );
    return ResponseEntity.ok(orderView(orders.findById(id).orElseThrow()));
  }

  private OrderResponse orderView(ShopOrder order) {
    List<OrderItem> lines = orderItems.findByOrderId(order.getId());
    int itemCount = lines.stream().mapToInt(OrderItem::getQuantity).sum();
    /*
     * 방금 만든 주문이라 리뷰는 아직 없다 — `reviewed` 는 전부 false 다. 주문 목록(`GET /api/orders`)은
     * 리뷰 유무를 질의로 확인하지만 여기는 생성 직후 응답이라 그럴 필요가 없다.
     */
    List<OrderItemResponse> items = lines
      .stream()
      .map(line ->
        new OrderItemResponse(
          line.getId(),
          line.getProductId(),
          line.getProductName(),
          line.getVariantLabel(),
          line.getQuantity(),
          line.getLineAmount(),
          false
        )
      )
      .toList();
    return new OrderResponse(
      order.getId(),
      order.getStatus().name(),
      order.getTotalAmount(),
      order.getPaidAmount(),
      order.getCurrency(),
      order.getPaymentId(),
      order.getPaymentProvider(),
      order.getPaidAt(),
      order.getCreatedAt(),
      itemCount,
      items
    );
  }

  private Cart cart(String memberId) {
    return carts
      .findByMemberId(memberId)
      .orElseGet(() ->
        carts.save(new Cart(UUID.randomUUID().toString(), memberId))
      );
  }

  private Optional<ProductVariant> activeVariant(String variantId) {
    return variants
      .findById(variantId)
      .filter(variant -> variant.getStatus() == ProductVariant.Status.ACTIVE)
      .filter(variant ->
        products
          .findById(variant.getProductId())
          .filter(product -> product.getStatus() == Product.Status.ACTIVE)
          .flatMap(product -> brands.findById(product.getBrandId()))
          .map(brand -> brand.getStatus() == BrandStatus.ACTIVE)
          .orElse(false)
      );
  }

  /**
   * 테스트 주문(`/pay`)을 부를 수 있는 계정인가.
   *
   * 설정한 접두로 시작하는 회원만 통과하고 나머지는 403 이다 — 조용히 실패시키지 않고 이유를 준다.
   * 접두가 비어 있으면 모두 막는다(설정 누락이 전체 허용이 되지 않게). 프론트는 이 응답을
   * "주문에 실패했습니다" 로 화면에 그대로 띄우므로 사용자가 막힌 것을 안다.
   */
  private void requireTestPayAllowed(ShopPrincipal actor) {
    if (
      !testPayAllowed(testPayAllowedMemberPrefix, actor.accountId())
    ) throw new ResponseStatusException(
      HttpStatus.FORBIDDEN,
      "test payment is limited to agent runner accounts"
    );
  }

  static boolean testPayAllowed(String configuredPrefix, String accountId) {
    String prefix = configuredPrefix == null ? "" : configuredPrefix.trim();
    if (prefix.isEmpty()) return false;
    return accountId != null && accountId.startsWith(prefix);
  }

  private void requireMember(ShopPrincipal actor) {
    if (
      actor == null || actor.role() != AccountRole.MEMBER
    ) throw new ResponseStatusException(
      HttpStatus.FORBIDDEN,
      "member role required"
    );
  }

  private String hash(List<CartItem> items) {
    try {
      MessageDigest digest = MessageDigest.getInstance("SHA-256");
      String source = items
        .stream()
        .map(item -> item.getVariantId() + ":" + item.getQuantity())
        .sorted()
        .reduce("", String::concat);
      return HexFormat.of().formatHex(
        digest.digest(source.getBytes(StandardCharsets.UTF_8))
      );
    } catch (Exception exception) {
      throw new IllegalStateException(exception);
    }
  }
}
