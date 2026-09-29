package com.cosmetic.shopbackend.commerce;

import java.util.*;
import org.springframework.data.jpa.repository.*;
import org.springframework.data.repository.query.Param;

public interface ShopOrderRepository extends JpaRepository<ShopOrder, String> {
  Optional<ShopOrder> findByMemberIdAndIdempotencyKey(String m, String k);
  List<ShopOrder> findByMemberIdOrderByIdDesc(String m);

  @Modifying(clearAutomatically = true, flushAutomatically = true)
  @Query(
    value = "update shop_order set status='PAID', paid_at=:paidAt, payment_provider='INTERNAL_TEST', paid_amount=total_amount where order_id=:id and member_id=:memberId and status='CREATED'",
    nativeQuery = true
  )
  int markPaid(
    @Param("id") String id,
    @Param("memberId") String memberId,
    @Param("paidAt") java.time.LocalDateTime paidAt
  );

  /** 결제 대조 대상: 아직 CREATED 인 주문 중 created_at 이 [from, to] 인 것, 최근 것부터. */
  @Query(
    value = "select order_id from shop_order where status='CREATED' and created_at >= :from and created_at <= :to order by created_at desc limit :limit",
    nativeQuery = true
  )
  List<String> findReconcileCandidateIds(
    @Param("from") java.time.LocalDateTime from,
    @Param("to") java.time.LocalDateTime to,
    @Param("limit") int limit
  );

  @Modifying(clearAutomatically = true, flushAutomatically = true)
  @Query(
    value = "update shop_order set status='PAID', paid_at=:paidAt, payment_id=:paymentId, payment_provider='PORTONE_TEST', paid_amount=:paidAmount where order_id=:id and member_id=:memberId and status='CREATED'",
    nativeQuery = true
  )
  int markVerifiedPaid(
    @Param("id") String id,
    @Param("memberId") String memberId,
    @Param("paymentId") String paymentId,
    @Param("paidAmount") java.math.BigDecimal paidAmount,
    @Param("paidAt") java.time.LocalDateTime paidAt
  );
}
