package com.cosmetic.shopbackend.commerce;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.cosmetic.shopbackend.identity.AccountRole;
import com.cosmetic.shopbackend.security.ShopPrincipal;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.web.server.ResponseStatusException;

/**
 * 판매자 주문 목록.
 *
 * 재는 것은 둘이다 — **남의 브랜드 줄이 섞이지 않는가**, 그리고 **금액이 내 줄의 합인가**.
 * 한 주문에 두 브랜드가 섞였을 때 주문 총액을 그대로 주면 남의 몫까지 내 매출이 된다.
 */
class SellerOrderControllerTest {

  private static final String BRAND = "ssafy-beauty";
  private static final String SELLER = "brand-admin-ssafy";
  private static final String TODAY = java.time.LocalDate.now(java.time.ZoneId.of("Asia/Seoul")).toString();

  private JdbcTemplate jdbc;
  private SellerOrderController controller;

  @BeforeEach
  void setUp() {
    DriverManagerDataSource ds = new DriverManagerDataSource(
      "jdbc:h2:mem:orders_" + UUID.randomUUID().toString().replace("-", "") +
        ";MODE=MySQL;DATABASE_TO_LOWER=TRUE;CASE_INSENSITIVE_IDENTIFIERS=TRUE;DB_CLOSE_DELAY=-1",
      "sa",
      "orders-test"
    );
    ds.setDriverClassName("org.h2.Driver");
    jdbc = new JdbcTemplate(ds);
    jdbc.execute("create table brand (brand_id varchar(64), seller_account_id varchar(64))");
    jdbc.execute("create table member (member_id varchar(64), nickname varchar(100))");
    jdbc.execute(
      "create table shop_order (order_id varchar(64), member_id varchar(64), status varchar(32)," +
        "currency varchar(3), paid_at timestamp, created_at timestamp)"
    );
    jdbc.execute(
      "create table order_item (order_item_id varchar(64), order_id varchar(64), product_id varchar(64)," +
        "brand_id varchar(64), product_name_snapshot varchar(300), variant_label_snapshot varchar(200)," +
        "quantity int, unit_price decimal(18,0), line_amount decimal(18,0))"
    );
    jdbc.update("insert into brand values (?,?)", BRAND, SELLER);
    jdbc.update("insert into member values (?,?)", "M1", "유림");
    controller = new SellerOrderController(jdbc);
  }

  @Test
  @DisplayName("한 주문에 다른 브랜드가 섞여도 내 줄만, 금액도 내 줄의 합이다")
  void keepsOnlyMyBrandLines() {
    paidOrder("O1");
    line("I1", "O1", "SB1", BRAND, "제로 포어 토닝 패드", 2, 16_100);
    line("I2", "O1", "P9", "6018", "남의 브랜드 세럼", 1, 90_000);

    Map<String, Object> body = call(null, null);
    List<?> orders = (List<?>) body.get("orders");
    Map<?, ?> order = (Map<?, ?>) orders.getFirst();

    assertEquals(1, orders.size());
    assertEquals(32_200L, number(order.get("brand_amount")));
    assertEquals(2L, number(order.get("item_count")));
    assertEquals(1, ((List<?>) order.get("items")).size());
    assertEquals("SB1", ((Map<?, ?>) ((List<?>) order.get("items")).getFirst()).get("product_id"));
  }

  @Test
  @DisplayName("한 주문의 여러 줄은 한 주문으로 접고 수량·금액을 더한다")
  void foldsLinesIntoOneOrder() {
    paidOrder("O1");
    line("I1", "O1", "SB1", BRAND, "토닝 패드", 2, 16_100);
    line("I2", "O1", "SB2", BRAND, "비타C 세럼", 1, 21_100);

    Map<?, ?> order = (Map<?, ?>) ((List<?>) call(null, null).get("orders")).getFirst();

    assertEquals(53_300L, number(order.get("brand_amount")));
    assertEquals(3L, number(order.get("item_count")));
    assertEquals(2, ((List<?>) order.get("items")).size());
    assertEquals("유림", order.get("buyer_nickname"));
  }

  @Test
  @DisplayName("결제가 끝나지 않은 주문은 판매가 아니다")
  void ignoresUnpaidOrders() {
    jdbc.update(
      "insert into shop_order values (?,?,?,?,?,?)",
      "O2", "M1", "CREATED", "KRW", null, java.sql.Timestamp.valueOf(TODAY + " 10:00:00")
    );
    line("I1", "O2", "SB1", BRAND, "토닝 패드", 5, 16_100);

    assertTrue(((List<?>) call(null, null).get("orders")).isEmpty());
  }

  @Test
  @DisplayName("기간 밖 주문은 빠진다")
  void filtersByRange() {
    paidOrder("O1");
    line("I1", "O1", "SB1", BRAND, "토닝 패드", 1, 16_100);

    assertTrue(((List<?>) call("2026-01-01", "2026-01-31").get("orders")).isEmpty());
    assertEquals(1, ((List<?>) call(TODAY, TODAY).get("orders")).size());
  }

  @Test
  @DisplayName("팔린 것이 없으면 빈 목록이다. 오류가 아니다")
  void emptyWhenNothingSold() {
    Map<String, Object> body = call(null, null);
    assertTrue(((List<?>) body.get("orders")).isEmpty());
    assertEquals(BRAND, body.get("brand_id"));
  }

  @Test
  @DisplayName("남의 브랜드와 판매자가 아닌 사람은 막는다")
  void refusesOthers() {
    assertEquals(403, forbidden(new ShopPrincipal("seller-2", AccountRole.SELLER)));
    assertEquals(403, forbidden(new ShopPrincipal("M1", AccountRole.MEMBER)));
  }

  @Test
  @DisplayName("날짜가 뒤집혔으면 400 bad_range")
  void rejectsBadRange() {
    ResponseStatusException thrown = assertThrows(
      ResponseStatusException.class,
      () -> call("2026-09-17", "2026-09-01")
    );
    assertEquals(400, thrown.getStatusCode().value());
    assertEquals("bad_range", thrown.getReason());
  }

  private int forbidden(ShopPrincipal actor) {
    ResponseStatusException thrown = assertThrows(
      ResponseStatusException.class,
      () -> controller.orders(actor, BRAND, null, null, null)
    );
    return thrown.getStatusCode().value();
  }

  private Map<String, Object> call(String from, String to) {
    return controller.orders(new ShopPrincipal(SELLER, AccountRole.SELLER), BRAND, from, to, null);
  }

  private void paidOrder(String orderId) {
    jdbc.update(
      "insert into shop_order values (?,?,?,?,?,?)",
      orderId,
      "M1",
      "PAID",
      "KRW",
      java.sql.Timestamp.valueOf(TODAY + " 14:02:11"),
      java.sql.Timestamp.valueOf(TODAY + " 14:00:00")
    );
  }

  private void line(String itemId, String orderId, String productId, String brandId, String name, int qty, long unit) {
    jdbc.update(
      "insert into order_item values (?,?,?,?,?,?,?,?,?)",
      itemId, orderId, productId, brandId, name, "기본", qty, unit, unit * qty
    );
  }

  private static long number(Object value) {
    return ((Number) value).longValue();
  }
}
