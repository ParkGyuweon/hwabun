package com.cosmetic.shopbackend.settlement;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.web.server.ResponseStatusException;

/**
 * 매일 새벽 정산 배치. 이번 달 첫 실행 뒤에도 완료되지 않은 정산은 다시 만들어 새 결제·취소를 반영해야 한다.
 */
class SettlementBatchSchedulerTest {

  private static final LocalDate MONTH = LocalDate.of(2026, 9, 1);

  private JdbcTemplate jdbc;
  private SettlementService service;
  private SettlementBatchScheduler scheduler;

  @BeforeEach
  void setUp() {
    DriverManagerDataSource ds = new DriverManagerDataSource(
      "jdbc:h2:mem:settle_" + UUID.randomUUID().toString().replace("-", "") +
        ";MODE=MySQL;DATABASE_TO_LOWER=TRUE;CASE_INSENSITIVE_IDENTIFIERS=TRUE;DB_CLOSE_DELAY=-1",
      "sa",
      "shop-test"
    );
    ds.setDriverClassName("org.h2.Driver");
    jdbc = new JdbcTemplate(ds);
    jdbc.execute("create table brand (brand_id varchar(64), status varchar(32))");
    jdbc.execute("create table shop_order (order_id varchar(64), status varchar(32), paid_at timestamp)");
    jdbc.execute("create table order_item (order_item_id varchar(64), order_id varchar(64), brand_id varchar(64), line_amount decimal(18,0))");
    jdbc.execute(
      "create table settlement (settlement_id varchar(64) primary key, brand_id varchar(64), settlement_month date," +
        "gross_amount decimal(18,0), net_amount decimal(18,0), status varchar(16) default 'PENDING'," +
        "unique (brand_id, settlement_month))"
    );
    jdbc.execute(
      "create table settlement_item (settlement_item_id varchar(64) primary key, settlement_id varchar(64)," +
        "brand_id varchar(64), order_item_id varchar(64) unique, gross_amount decimal(18,0), net_amount decimal(18,0))"
    );
    service = new SettlementService(jdbc);
    scheduler = new SettlementBatchScheduler(jdbc, service);
  }

  @Test
  @DisplayName("첫 실행 뒤 들어온 결제와 취소가 다음 날 배치에 반영된다")
  void regeneratesPendingSettlementEveryRun() {
    brand("A", "ACTIVE");
    order("O1", "PAID", "2026-09-03T10:00");
    item("I1", "O1", "A", 10_000);

    scheduler.generateMonth(MONTH);
    assertEquals(10_000L, gross("A"));

    // 다음 날: 새 결제 하나, 앞 주문은 환불
    order("O2", "PAID", "2026-09-04T10:00");
    item("I2", "O2", "A", 7_000);
    jdbc.update("update shop_order set status='REFUNDED' where order_id='O1'");

    scheduler.generateMonth(MONTH);
    assertEquals(7_000L, gross("A"));
    assertEquals(1, count("select count(*) from settlement_item"));
    assertEquals(1, count("select count(*) from settlement where brand_id='A'"));

    // 같은 날 두 번 돌아도 결과가 같다
    scheduler.generateMonth(MONTH);
    assertEquals(7_000L, gross("A"));
    assertEquals(1, count("select count(*) from settlement_item"));
  }

  @Test
  @DisplayName("완료된 정산과 ACTIVE 가 아닌 브랜드는 건드리지 않고, 나머지 브랜드는 계속 돈다")
  void skipsCompletedAndInactive() {
    brand("A", "ACTIVE");
    brand("B", "ACTIVE");
    brand("C", "SUSPENDED");
    order("O1", "PAID", "2026-09-03T10:00");
    item("I1", "O1", "A", 10_000);
    item("I2", "O1", "B", 5_000);
    item("I3", "O1", "C", 1_000);

    scheduler.generateMonth(MONTH);
    jdbc.update("update settlement set status='COMPLETED' where brand_id='A'");

    order("O2", "PAID", "2026-09-05T10:00");
    item("I4", "O2", "A", 3_000);
    item("I5", "O2", "B", 2_000);

    scheduler.generateMonth(MONTH);
    assertEquals(10_000L, gross("A"));
    assertEquals(7_000L, gross("B"));
    assertEquals(0, count("select count(*) from settlement where brand_id='C'"));
    assertThrows(ResponseStatusException.class, () -> service.generate("A", MONTH));
  }

  @Test
  @DisplayName("다른 달에 결제된 주문은 이번 달 정산에 들어가지 않는다")
  void onlyThisMonth() {
    brand("A", "ACTIVE");
    order("O1", "PAID", "2026-08-31T23:59");
    order("O2", "PAID", "2026-10-01T00:00");
    order("O3", "PAID", "2026-09-30T23:59");
    item("I1", "O1", "A", 1_000);
    item("I2", "O2", "A", 2_000);
    item("I3", "O3", "A", 4_000);

    scheduler.generateMonth(MONTH);
    assertEquals(4_000L, gross("A"));
  }

  private void brand(String id, String status) {
    jdbc.update("insert into brand values (?,?)", id, status);
  }

  private void order(String id, String status, String paidAt) {
    jdbc.update("insert into shop_order values (?,?,?)", id, status, LocalDateTime.parse(paidAt));
  }

  private void item(String id, String orderId, String brandId, long amount) {
    jdbc.update("insert into order_item values (?,?,?,?)", id, orderId, brandId, amount);
  }

  private long gross(String brandId) {
    return jdbc.queryForObject(
      "select gross_amount from settlement where brand_id=? and settlement_month=?",
      Long.class,
      brandId,
      MONTH
    );
  }

  private int count(String sql) {
    return jdbc.queryForObject(sql, Integer.class);
  }
}
