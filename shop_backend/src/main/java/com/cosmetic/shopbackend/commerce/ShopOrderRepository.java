package com.cosmetic.shopbackend.commerce;

import java.util.*;
import org.springframework.data.jpa.repository.*;
import org.springframework.data.repository.query.Param;

public interface ShopOrderRepository extends JpaRepository<ShopOrder, String> {
  Optional<ShopOrder> findByMemberIdAndIdempotencyKey(String m, String k);
  List<ShopOrder> findByMemberIdOrderByIdDesc(String m);

  // native UPDATE 뒤 1차 캐시에 남아 있던 CREATED 엔티티를 다시 응답하지 않도록 한다.
  @Modifying(flushAutomatically = true, clearAutomatically = true)
  @Query(
    value = "update shop_order set status='PAID', paid_at=CURRENT_TIMESTAMP(6) where order_id=:id and member_id=:memberId and status='CREATED'",
    nativeQuery = true
  )
  int markPaid(@Param("id") String id, @Param("memberId") String memberId);
}
