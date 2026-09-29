package com.cosmetic.shopbackend.settlement;

import java.time.LocalDate;
import java.util.*;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowCallbackHandler;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class SettlementService {

  private final JdbcTemplate jdbc;

  public SettlementService(JdbcTemplate jdbc) {
    this.jdbc = jdbc;
  }

  /**
   * 한 브랜드의 한 달 정산을 만든다. 여러 번 불러도 결과가 같다 — 매일 새벽 배치가 이번 달 정산을 다시 부른다.
   *
   * 아직 완료(COMPLETED)되지 않은 정산이면 그 정산의 항목을 모두 지우고 그 달 PAID 주문 줄로 다시 채운다. 그래서
   * 새 결제는 들어오고, 그 사이 취소·환불된 주문 줄은 빠진다. 한 트랜잭션이라 중간에 실패하면 이전 항목이 그대로 남는다.
   * 정산 행을 FOR UPDATE 로 잠가 관리자 완료 처리와 겹치지 않게 한다. 완료된 정산은 건드리지 않는다 (409).
   */
  @Transactional
  public Map<String, Object> generate(String brandId, LocalDate month) {
    List<Map<String, Object>> existing = jdbc.queryForList(
      "select settlement_id,status,gross_amount,net_amount from settlement where brand_id=? and settlement_month=? for update",
      brandId,
      month
    );
    String id;
    if (existing.isEmpty()) {
      id = UUID.randomUUID().toString();
      jdbc.update(
        "insert into settlement(settlement_id,brand_id,settlement_month,gross_amount,net_amount) values(?,?,?,?,?)",
        id,
        brandId,
        month,
        0L,
        0L
      );
    } else {
      Map<String, Object> row = existing.get(0);
      if (
        "COMPLETED".equals(String.valueOf(row.get("status")))
      ) throw new ResponseStatusException(
        HttpStatus.CONFLICT,
        "settlement already completed"
      );
      id = String.valueOf(row.get("settlement_id"));
      // 다시 만들기: 이 정산(PENDING)의 항목을 비우고 아래에서 현재 PAID 주문 줄로 다시 채운다.
      jdbc.update("delete from settlement_item where settlement_id=?", id);
    }
    jdbc.query(
      "select oi.order_item_id,oi.line_amount from order_item oi join shop_order o on o.order_id=oi.order_id where oi.brand_id=? and o.status='PAID' and o.paid_at>=? and o.paid_at<? and not exists (select 1 from settlement_item si where si.order_item_id=oi.order_item_id)",
      ps -> {
        ps.setString(1, brandId);
        ps.setObject(2, month);
        ps.setObject(3, month.plusMonths(1));
      },
      (RowCallbackHandler) rs ->
        jdbc.update(
          "insert into settlement_item(settlement_item_id,settlement_id,brand_id,order_item_id,gross_amount,net_amount) values(?,?,?,?,?,?)",
          UUID.randomUUID().toString(),
          id,
          brandId,
          rs.getString("order_item_id"),
          rs.getLong("line_amount"),
          rs.getLong("line_amount")
        )
    );
    Long gross = jdbc.queryForObject(
      "select coalesce(sum(gross_amount),0) from settlement_item where settlement_id=?",
      Long.class,
      id
    );
    jdbc.update(
      "update settlement set gross_amount=?,net_amount=? where settlement_id=? and status='PENDING'",
      gross,
      gross,
      id
    );
    return Map.of(
      "settlementId",
      id,
      "grossAmount",
      gross,
      "netAmount",
      gross,
      "status",
      "PENDING"
    );
  }
}
