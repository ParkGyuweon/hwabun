package com.cosmetic.shopbackend.settlement;

import java.time.LocalDate;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowCallbackHandler;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class SettlementBatchScheduler {

  private final JdbcTemplate jdbc;
  private final SettlementService settlements;

  public SettlementBatchScheduler(
    JdbcTemplate jdbc,
    SettlementService settlements
  ) {
    this.jdbc = jdbc;
    this.settlements = settlements;
  }

  @Scheduled(cron = "${shop.settlement.cron:0 0 2 * * *}", zone = "Asia/Seoul")
  public void generateDaily() {
    LocalDate month = LocalDate.now().withDayOfMonth(1);
    jdbc.query(
      "select b.brand_id from brand b left join settlement s on s.brand_id=b.brand_id and s.settlement_month=? where b.status='ACTIVE' and s.settlement_id is null",
      ps -> ps.setObject(1, month),
      (RowCallbackHandler) rs ->
        settlements.generate(rs.getString("brand_id"), month)
    );
  }
}
