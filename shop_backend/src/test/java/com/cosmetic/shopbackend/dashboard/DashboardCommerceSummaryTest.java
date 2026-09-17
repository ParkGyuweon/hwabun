package com.cosmetic.shopbackend.dashboard;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.web.server.ResponseStatusException;

/**
 * 판매자 요약 4칸(+판매 수량·가짓수) 집계.
 *
 * 주문 수와 팔린 개수는 다른 값이다. 한 주문에 3개가 들어가면 주문 1 · 수량 3 이다. 화면이 둘을 나란히
 * 적는 이유가 그것이고, 이 테스트가 재는 것도 그 구분이다.
 */
class DashboardCommerceSummaryTest {

  private static final String BRAND = "6018";
  private static final String SELLER = "brand-admin-6018";

  private JdbcTemplate shop;
  private DashboardMartService service;

  @BeforeEach
  void setUp() {
    DriverManagerDataSource ds = new DriverManagerDataSource(
      "jdbc:h2:mem:shop_" + UUID.randomUUID().toString().replace("-", "") +
        ";MODE=MySQL;DATABASE_TO_LOWER=TRUE;CASE_INSENSITIVE_IDENTIFIERS=TRUE;DB_CLOSE_DELAY=-1",
      "sa",
      "shop-test"
    );
    ds.setDriverClassName("org.h2.Driver");
    shop = new JdbcTemplate(ds);
    shop.execute("create table brand (brand_id varchar(64), seller_account_id varchar(64))");
    shop.execute("create table shop_order (order_id varchar(64), status varchar(32))");
    shop.execute(
      "create table order_item (order_item_id varchar(64), order_id varchar(64), product_id varchar(64)," +
        "brand_id varchar(64), quantity int, line_amount decimal(18,0))"
    );
    shop.execute("create table review (review_id varchar(64), order_item_id varchar(64))");
    shop.execute("create table feedback (feedback_id varchar(64), order_item_id varchar(64), status varchar(32))");
    shop.update("insert into brand values (?,?)", BRAND, SELLER);
    // DW 는 이 테스트에서 쓰지 않는다. 연결이 없으면 마트 엔드포인트만 503 이고 요약은 쇼핑몰 DB 만 읽는다.
    service = new DashboardMartService(shop, new DashboardMartJdbcProvider("", "", ""));
  }

  @Test
  @DisplayName("팔린 개수는 주문 수와 다르다 — 한 주문에 여러 개가 들어간다")
  void countsUnitsSeparatelyFromOrders() {
    paidOrder("O1");
    paidOrder("O2");
    // O1: P1 두 개 + P2 한 개, O2: P1 세 개 → 주문 2 · 수량 6 · 가짓수 2 · 주문 줄 3
    line("I1", "O1", "P1", 2, 20_000);
    line("I2", "O1", "P2", 1, 5_000);
    line("I3", "O2", "P1", 3, 30_000);

    Map<String, Object> summary = service.commerceSummary(SELLER, BRAND);

    assertEquals(2L, number(summary.get("orders")));
    assertEquals(6L, number(summary.get("units")));
    assertEquals(2L, number(summary.get("sold_products")));
    assertEquals(3L, number(summary.get("order_items")));
    assertEquals(55_000L, number(summary.get("revenue")));
  }

  @Test
  @DisplayName("결제가 끝나지 않은 주문은 어느 칸에도 들어가지 않는다")
  void ignoresUnpaidOrders() {
    paidOrder("O1");
    line("I1", "O1", "P1", 2, 20_000);
    shop.update("insert into shop_order values (?,?)", "O2", "PENDING");
    line("I2", "O2", "P9", 50, 500_000);

    Map<String, Object> summary = service.commerceSummary(SELLER, BRAND);

    assertEquals(1L, number(summary.get("orders")));
    assertEquals(2L, number(summary.get("units")));
    assertEquals(20_000L, number(summary.get("revenue")));
  }

  @Test
  @DisplayName("다른 브랜드가 판 것은 섞이지 않는다")
  void keepsOtherBrandsOut() {
    paidOrder("O1");
    line("I1", "O1", "P1", 2, 20_000);
    shop.update("insert into order_item values (?,?,?,?,?,?)", "I2", "O1", "P2", "9999", 7, 70_000);

    Map<String, Object> summary = service.commerceSummary(SELLER, BRAND);

    assertEquals(2L, number(summary.get("units")));
    assertEquals(1L, number(summary.get("sold_products")));
  }

  @Test
  @DisplayName("판 것이 없으면 0 이다. 빈 결과가 null 로 새면 화면이 깨진다")
  void zeroWhenNothingSold() {
    Map<String, Object> summary = service.commerceSummary(SELLER, BRAND);

    assertEquals(0L, number(summary.get("orders")));
    assertEquals(0L, number(summary.get("units")));
    assertEquals(0L, number(summary.get("sold_products")));
    assertEquals(0L, number(summary.get("revenue")));
  }

  @Test
  @DisplayName("남의 브랜드는 막는다")
  void refusesAnotherSeller() {
    ResponseStatusException thrown = assertThrows(
      ResponseStatusException.class,
      () -> service.commerceSummary("seller-2", BRAND)
    );
    assertEquals(403, thrown.getStatusCode().value());
  }

  private void paidOrder(String orderId) {
    shop.update("insert into shop_order values (?,?)", orderId, "PAID");
  }

  private void line(String itemId, String orderId, String productId, int quantity, long amount) {
    shop.update("insert into order_item values (?,?,?,?,?,?)", itemId, orderId, productId, BRAND, quantity, amount);
  }

  private static long number(Object value) {
    return ((Number) value).longValue();
  }
}
