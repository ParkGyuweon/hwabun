package com.cosmetic.shopbackend.settlement;

import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;
import java.time.LocalDate;
import java.util.*;

@RestController
@RequestMapping("/api/settlements")
public class SettlementController {
 private final JdbcTemplate jdbc;
 public SettlementController(JdbcTemplate jdbc){this.jdbc=jdbc;}
 @GetMapping public List<Map<String,Object>> list(@RequestHeader("X-User-Id") String sellerId,@RequestHeader("X-User-Role") String role,@RequestParam String brandId){ requireSeller(role); owns(sellerId,brandId); return jdbc.queryForList("select * from settlement where brand_id=? order by settlement_month desc",brandId); }
 @PostMapping("/generate") @Transactional public Map<String,Object> generate(@RequestHeader("X-User-Id") String sellerId,@RequestHeader("X-User-Role") String role,@RequestParam String brandId,@RequestParam String month){
  requireSeller(role);
  owns(sellerId,brandId); LocalDate m=LocalDate.parse(month+"-01");
  if(jdbc.queryForObject("select count(*) from settlement where brand_id=? and settlement_month=?",Integer.class,brandId,m)>0) throw new ResponseStatusException(HttpStatus.CONFLICT,"settlement exists");
  long gross=Optional.ofNullable(jdbc.queryForObject("select coalesce(sum(line_amount),0) from order_item oi join shop_order o on o.order_id=oi.order_id where oi.brand_id=? and o.status='PAID' and o.paid_at>=? and o.paid_at<?",Long.class,brandId,m,m.plusMonths(1))).orElse(0L);
  String id=UUID.randomUUID().toString(); jdbc.update("insert into settlement(settlement_id,brand_id,settlement_month,gross_amount,net_amount) values(?,?,?,?,?)",id,brandId,m,gross,gross);
  jdbc.query("select oi.order_item_id,oi.line_amount from order_item oi join shop_order o on o.order_id=oi.order_id where oi.brand_id=? and o.status='PAID' and o.paid_at>=? and o.paid_at<?", ps -> { ps.setString(1,brandId); ps.setObject(2,m); ps.setObject(3,m.plusMonths(1)); }, rs -> { jdbc.update("insert into settlement_item(settlement_item_id,settlement_id,brand_id,order_item_id,gross_amount,net_amount) values(?,?,?,?,?,?)",UUID.randomUUID().toString(),id,brandId,rs.getString("order_item_id"),rs.getLong("line_amount"),rs.getLong("line_amount")); });
  return Map.of("settlementId",id,"grossAmount",gross,"netAmount",gross,"status","PENDING");
 }
 private void owns(String seller,String brand){if(jdbc.queryForObject("select count(*) from brand where brand_id=? and seller_account_id=?",Integer.class,brand,seller)==0) throw new ResponseStatusException(HttpStatus.FORBIDDEN,"brand access denied");}
 private void requireSeller(String role){if(!"SELLER".equalsIgnoreCase(role))throw new ResponseStatusException(HttpStatus.FORBIDDEN,"seller role required");}
}
