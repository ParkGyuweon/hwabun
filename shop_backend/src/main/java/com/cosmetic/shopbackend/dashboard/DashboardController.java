package com.cosmetic.shopbackend.dashboard;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.*;
import java.util.Map;

@RestController @RequestMapping("/api/seller/dashboard")
public class DashboardController {
 private final JdbcTemplate jdbc; public DashboardController(JdbcTemplate jdbc){this.jdbc=jdbc;}
 @GetMapping public Map<String,Object> dashboard(@RequestHeader("X-User-Id") String seller,@RequestHeader("X-User-Role") String role,@RequestParam String brandId){
  if(!"SELLER".equalsIgnoreCase(role)) throw new org.springframework.web.server.ResponseStatusException(org.springframework.http.HttpStatus.FORBIDDEN,"seller role required");
  if(jdbc.queryForObject("select count(*) from brand where brand_id=? and seller_account_id=?",Integer.class,brandId,seller)==0) throw new org.springframework.web.server.ResponseStatusException(org.springframework.http.HttpStatus.FORBIDDEN);
  return jdbc.queryForMap("select count(distinct oi.order_id) orders,coalesce(sum(oi.line_amount),0) revenue,(select count(*) from review r join order_item x on x.order_item_id=r.order_item_id where x.brand_id=?) reviews,(select count(*) from feedback f join order_item x on x.order_item_id=f.order_item_id where x.brand_id=? and f.status='VISIBLE') feedbacks from order_item oi join shop_order o on o.order_id=oi.order_id where oi.brand_id=? and o.status='PAID'",brandId,brandId,brandId);
 }
}
