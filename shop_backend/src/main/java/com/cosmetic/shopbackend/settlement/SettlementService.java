package com.cosmetic.shopbackend.settlement;

import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowCallbackHandler;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;
import java.time.LocalDate;
import java.util.*;

@Service
public class SettlementService {
    private final JdbcTemplate jdbc;
    public SettlementService(JdbcTemplate jdbc) { this.jdbc = jdbc; }

    @Transactional
    public Map<String,Object> generate(String brandId, LocalDate month) {
        List<Map<String,Object>> existing = jdbc.queryForList("select settlement_id,status,gross_amount,net_amount from settlement where brand_id=? and settlement_month=?", brandId, month);
        String id;
        if (existing.isEmpty()) {
            id = UUID.randomUUID().toString();
            jdbc.update("insert into settlement(settlement_id,brand_id,settlement_month,gross_amount,net_amount) values(?,?,?,?,?)", id, brandId, month, 0L, 0L);
        } else {
            Map<String,Object> row = existing.get(0);
            if ("COMPLETED".equals(String.valueOf(row.get("status")))) throw new ResponseStatusException(HttpStatus.CONFLICT, "settlement already completed");
            id = String.valueOf(row.get("settlement_id"));
        }
        jdbc.query("select oi.order_item_id,oi.line_amount from order_item oi join shop_order o on o.order_id=oi.order_id where oi.brand_id=? and o.status='PAID' and o.paid_at>=? and o.paid_at<? and not exists (select 1 from settlement_item si where si.order_item_id=oi.order_item_id)", ps -> { ps.setString(1, brandId); ps.setObject(2, month); ps.setObject(3, month.plusMonths(1)); }, (RowCallbackHandler) rs -> jdbc.update("insert into settlement_item(settlement_item_id,settlement_id,brand_id,order_item_id,gross_amount,net_amount) values(?,?,?,?,?,?)", UUID.randomUUID().toString(), id, brandId, rs.getString("order_item_id"), rs.getLong("line_amount"), rs.getLong("line_amount")));
        Long gross = jdbc.queryForObject("select coalesce(sum(gross_amount),0) from settlement_item where settlement_id=?", Long.class, id);
        jdbc.update("update settlement set gross_amount=?,net_amount=? where settlement_id=? and status='PENDING'", gross, gross, id);
        return Map.of("settlementId", id, "grossAmount", gross, "netAmount", gross, "status", "PENDING");
    }
}
