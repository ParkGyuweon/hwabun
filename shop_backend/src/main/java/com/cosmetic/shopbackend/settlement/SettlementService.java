package com.cosmetic.shopbackend.settlement;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowCallbackHandler;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;
import java.time.LocalDate;
import java.util.*;

@Service
public class SettlementService {
    private final JdbcTemplate jdbc;
    public SettlementService(JdbcTemplate jdbc) { this.jdbc = jdbc; }

    @Transactional
    public Map<String,Object> generate(String brandId, LocalDate month) {
        if (jdbc.queryForObject("select count(*) from settlement where brand_id=? and settlement_month=?", Integer.class, brandId, month) > 0)
            throw new ResponseStatusException(HttpStatus.CONFLICT, "settlement exists");
        long gross = Optional.ofNullable(jdbc.queryForObject("select coalesce(sum(line_amount),0) from order_item oi join shop_order o on o.order_id=oi.order_id where oi.brand_id=? and o.status='PAID' and o.paid_at>=? and o.paid_at<?", Long.class, brandId, month, month.plusMonths(1))).orElse(0L);
        String id = UUID.randomUUID().toString();
        jdbc.update("insert into settlement(settlement_id,brand_id,settlement_month,gross_amount,net_amount) values(?,?,?,?,?)", id, brandId, month, gross, gross);
        jdbc.query("select oi.order_item_id,oi.line_amount from order_item oi join shop_order o on o.order_id=oi.order_id where oi.brand_id=? and o.status='PAID' and o.paid_at>=? and o.paid_at<?", ps -> { ps.setString(1, brandId); ps.setObject(2, month); ps.setObject(3, month.plusMonths(1)); }, (RowCallbackHandler) rs -> jdbc.update("insert into settlement_item(settlement_item_id,settlement_id,brand_id,order_item_id,gross_amount,net_amount) values(?,?,?,?,?,?)", UUID.randomUUID().toString(), id, brandId, rs.getString("order_item_id"), rs.getLong("line_amount"), rs.getLong("line_amount")));
        return Map.of("settlementId", id, "grossAmount", gross, "netAmount", gross, "status", "PENDING");
    }
}
