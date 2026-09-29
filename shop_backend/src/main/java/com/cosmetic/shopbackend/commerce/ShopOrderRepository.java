package com.cosmetic.shopbackend.commerce;

import java.util.*;
import org.springframework.data.jpa.repository.*;
import org.springframework.data.repository.query.Param;

public interface ShopOrderRepository extends JpaRepository<ShopOrder, String> {
  Optional<ShopOrder> findByMemberIdAndIdempotencyKey(String m, String k);
  List<ShopOrder> findByMemberIdOrderByIdDesc(String m);

  /** 회원 탈퇴 차단 판정용 — 이 상태로 이 시각 이후에 만든 주문이 있는가 */
  boolean existsByMemberIdAndStatusAndCreatedAtAfter(
    String memberId,
    ShopOrder.Status status,
    java.time.LocalDateTime after
  );

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
