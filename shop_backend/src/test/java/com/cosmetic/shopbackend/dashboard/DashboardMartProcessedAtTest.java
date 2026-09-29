package com.cosmetic.shopbackend.dashboard;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

import java.sql.Timestamp;
import java.time.LocalDateTime;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/** DW 의 mart_processed_at 은 UTC DATETIME 이다. 응답은 KST(+09:00) 로 나가야 한다. */
class DashboardMartProcessedAtTest {

  @Test
  @DisplayName("MySQL 드라이버가 주는 LocalDateTime 도 UTC 로 읽어 KST 로 바꾼다")
  void convertsLocalDateTimeFromUtc() {
    assertEquals(
      "2026-09-20T18:56:03+09:00",
      DashboardMartService.timestampText(LocalDateTime.parse("2026-09-20T09:56:03"))
    );
  }

  @Test
  @DisplayName("Timestamp 로 와도 같은 값이 나온다")
  void convertsTimestampFromUtc() {
    assertEquals(
      "2026-09-21T08:30+09:00",
      DashboardMartService.timestampText(Timestamp.valueOf(LocalDateTime.parse("2026-09-20T23:30:00")))
    );
  }

  @Test
  void nullStaysNull() {
    assertNull(DashboardMartService.timestampText(null));
  }
}
