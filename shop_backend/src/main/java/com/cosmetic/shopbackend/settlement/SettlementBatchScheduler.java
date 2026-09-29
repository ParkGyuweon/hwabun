package com.cosmetic.shopbackend.settlement;

import java.time.LocalDate;
import java.time.ZoneId;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class SettlementBatchScheduler {

  private static final Logger log = LoggerFactory.getLogger(SettlementBatchScheduler.class);
  private static final ZoneId KST = ZoneId.of("Asia/Seoul");

  private final JdbcTemplate jdbc;
  private final SettlementService settlements;

  public SettlementBatchScheduler(
    JdbcTemplate jdbc,
    SettlementService settlements
  ) {
    this.jdbc = jdbc;
    this.settlements = settlements;
  }

  /**
   * 매일 새벽 2시(KST)에 전달과 이번 달 정산을 갱신한다 (판매자 정산 화면 "매일 새벽 2시 갱신").
   * 정산이 아직 없는 ACTIVE 브랜드는 새로 만들고, 완료(COMPLETED)되지 않은 정산은 다시 만든다.
   * 전달도 함께 도는 까닭: 월말 02:00 이후 결제는 그달 마지막 배치 뒤에 들어오므로, 다음 날(1일) 실행이
   * 전달 정산을 다시 만들어야 빠지지 않는다. 관리자가 전달을 완료 처리하면 그 뒤로는 건드리지 않는다.
   * 한 브랜드가 실패해도 나머지 브랜드는 계속 돈다.
   */
  @Scheduled(cron = "${shop.settlement.cron:0 0 2 * * *}", zone = "Asia/Seoul")
  public void generateDaily() {
    generateFor(LocalDate.now(KST));
  }

  /** today(KST) 기준으로 전달, 이번 달 순서로 정산을 갱신한다. */
  void generateFor(LocalDate today) {
    LocalDate thisMonth = today.withDayOfMonth(1);
    generateMonth(thisMonth.minusMonths(1));
    generateMonth(thisMonth);
  }

  void generateMonth(LocalDate month) {
    List<String> brandIds = jdbc.queryForList(
      "select b.brand_id from brand b left join settlement s on s.brand_id=b.brand_id and s.settlement_month=? " +
        "where b.status='ACTIVE' and (s.settlement_id is null or s.status<>'COMPLETED')",
      String.class,
      month
    );
    for (String brandId : brandIds) {
      try {
        settlements.generate(brandId, month);
      } catch (RuntimeException exception) {
        log.warn("settlement generate failed brand={} month={}", brandId, month, exception);
      }
    }
  }
}
