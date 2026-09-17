package com.cosmetic.shopbackend.commerce;

import com.cosmetic.shopbackend.identity.AccountRole;
import com.cosmetic.shopbackend.security.ShopPrincipal;
import java.sql.Date;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

/**
 * 판매자 주문 목록 (`docs/dashboard/seller-console-gaps.md` §4).
 *
 * 기존 `GET /api/orders` 는 **회원 본인의** 주문만 준다(`where member_id = 로그인한 사람`). 판매자가 자기
 * 브랜드에 들어온 주문을 보려면 `order_item.brand_id` 로 거르는 경로가 따로 있어야 한다. 프론트에서
 * 우회할 방법이 없고, 우회해서도 안 된다 — 남의 주문이기 때문이다.
 *
 * <h2>내 브랜드 줄만 싣는다</h2>
 * 한 주문에 여러 브랜드 상품이 섞일 수 있다. 그때 다른 브랜드 품목은 응답에 넣지 않고, 금액도 내 줄의
 * 합(`brand_amount`)이다. 주문 총액을 그대로 주면 남의 몫까지 내 매출로 읽힌다.
 *
 * <h2>싣지 않는 것</h2>
 * 구매자는 회원 id 와 표시 이름까지다. 이메일·연락처는 주문을 확인하는 데 필요하지 않아 싣지 않는다.
 */
@RestController
@RequestMapping("/api/seller")
public class SellerOrderController {

  private static final ZoneId KST = ZoneId.of("Asia/Seoul");

  /** 한 번에 내려 주는 주문 수. 화면이 표로 훑는 자리라 이 정도면 충분하다 */
  private static final int DEFAULT_LIMIT = 200;
  private static final int MAX_LIMIT = 1000;

  /** 기본 조회 기간 (to 포함). 마트 API 와 같은 값이라 두 화면의 "최근 14일" 이 같은 뜻이다 */
  private static final int DEFAULT_RANGE_DAYS = 14;

  private final JdbcTemplate jdbc;

  public SellerOrderController(JdbcTemplate jdbc) {
    this.jdbc = jdbc;
  }

  @GetMapping("/orders")
  public Map<String, Object> orders(
    @AuthenticationPrincipal ShopPrincipal actor,
    @RequestParam String brandId,
    @RequestParam(required = false) String from,
    @RequestParam(required = false) String to,
    @RequestParam(required = false) Integer limit
  ) {
    String seller = requireSeller(actor);
    owns(seller, brandId);

    LocalDate end;
    LocalDate start;
    try {
      end = to == null || to.isBlank() ? LocalDate.now(KST) : LocalDate.parse(to);
      start = from == null || from.isBlank() ? end.minusDays(DEFAULT_RANGE_DAYS - 1) : LocalDate.parse(from);
    } catch (RuntimeException exception) {
      throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "bad_range");
    }
    if (start.isAfter(end)) throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "bad_range");
    int cap = limit == null ? DEFAULT_LIMIT : Math.min(Math.max(limit, 1), MAX_LIMIT);

    /*
     * 주문 줄을 한 번에 읽고 Java 에서 주문 단위로 접는다. 주문 목록과 품목을 따로 부르면 N+1 이 된다
     * (상품 상세에서 같은 실수로 요청 459건이 나간 적이 있다 — 백엔드 지적 2026-09-14).
     *
     * 결제가 끝난 주문만 판매다. 날짜는 결제 시각 기준이고, 아직 결제 시각이 없으면 생성 시각으로 본다.
     */
    List<Map<String, Object>> rows = jdbc.queryForList(
      """
      select o.order_id, o.member_id buyer_id, m.nickname buyer_nickname, o.status, o.currency,
             coalesce(o.paid_at, o.created_at) ordered_at,
             oi.product_id, oi.product_name_snapshot product_name,
             oi.variant_label_snapshot variant_label, oi.quantity, oi.unit_price, oi.line_amount
      from shop_order o
      join order_item oi on oi.order_id = o.order_id
      join member m on m.member_id = o.member_id
      where oi.brand_id = ? and o.status = 'PAID'
        and date(coalesce(o.paid_at, o.created_at)) between ? and ?
      order by coalesce(o.paid_at, o.created_at) desc, o.order_id, oi.order_item_id
      """,
      brandId,
      Date.valueOf(start),
      Date.valueOf(end)
    );

    Map<String, Map<String, Object>> byOrder = new LinkedHashMap<>();
    for (Map<String, Object> row : rows) {
      String orderId = String.valueOf(row.get("order_id"));
      Map<String, Object> order = byOrder.get(orderId);
      if (order == null) {
        if (byOrder.size() >= cap) continue; // 상한을 넘은 주문은 통째로 뺀다. 품목만 잘려 나가면 금액이 틀린다
        order = new LinkedHashMap<>();
        order.put("order_id", orderId);
        order.put("buyer_id", row.get("buyer_id"));
        order.put("buyer_nickname", row.get("buyer_nickname"));
        order.put("status", row.get("status"));
        order.put("currency", row.get("currency"));
        order.put("ordered_at", text(row.get("ordered_at")));
        order.put("brand_amount", 0L);
        order.put("item_count", 0L);
        order.put("items", new ArrayList<Map<String, Object>>());
        byOrder.put(orderId, order);
      }
      @SuppressWarnings("unchecked")
      List<Map<String, Object>> items = (List<Map<String, Object>>) order.get("items");
      Map<String, Object> item = new LinkedHashMap<>();
      item.put("product_id", row.get("product_id"));
      item.put("product_name", row.get("product_name"));
      item.put("variant_label", row.get("variant_label"));
      item.put("quantity", longOf(row.get("quantity")));
      item.put("unit_price", longOf(row.get("unit_price")));
      item.put("line_amount", longOf(row.get("line_amount")));
      items.add(item);
      order.put("brand_amount", longOf(order.get("brand_amount")) + longOf(row.get("line_amount")));
      order.put("item_count", longOf(order.get("item_count")) + longOf(row.get("quantity")));
    }

    Map<String, Object> out = new LinkedHashMap<>();
    out.put("brand_id", brandId);
    out.put("range", Map.of("from", start.toString(), "to", end.toString()));
    out.put("orders", List.copyOf(byOrder.values()));
    return out;
  }

  private String requireSeller(ShopPrincipal actor) {
    if (actor == null || actor.role() != AccountRole.SELLER) {
      throw new ResponseStatusException(HttpStatus.FORBIDDEN, "seller role required");
    }
    return actor.accountId();
  }

  private void owns(String seller, String brandId) {
    Integer count = jdbc.queryForObject(
      "select count(*) from brand where brand_id=? and seller_account_id=?",
      Integer.class,
      brandId,
      seller
    );
    if (count == null || count == 0) throw new ResponseStatusException(HttpStatus.FORBIDDEN, "brand access denied");
  }

  /**
   * 시각은 문자열로 보낸다. 직렬화 설정에 따라 숫자가 되면 화면이 날짜를 잘라 쓰다가 깨진다.
   *
   * 초를 명시적인 형식으로 고정한다. `LocalDateTime.toString()` 은 초가 정각(0초)이면 그 자리를
   * 통째로 생략한다 — "14:02:11" 은 그대로 나오지만 "14:02:00" 은 "14:02" 가 되어 응답 모양이
   * 레코드마다 달라진다. 화면이 초까지 보여줘야 해서 형식을 고정해 항상 같은 길이로 낸다.
   */
  private static final java.time.format.DateTimeFormatter TIMESTAMP_FORMAT =
    java.time.format.DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss");

  private static String text(Object value) {
    if (value == null) return null;
    if (value instanceof java.sql.Timestamp timestamp) return timestamp.toLocalDateTime().format(TIMESTAMP_FORMAT);
    return String.valueOf(value);
  }

  private static long longOf(Object value) {
    return value instanceof Number number ? number.longValue() : 0L;
  }
}
