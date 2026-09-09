package com.cosmetic.shopbackend.commerce;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.*;

@Entity
@Table(name = "shop_order")
public class ShopOrder {

  @Id
  @Column(name = "order_id")
  private String id;

  @Column(name = "member_id")
  private String memberId;

  @Column(name = "idempotency_key")
  private String idempotencyKey;

  @Column(name = "request_hash")
  private String requestHash;

  @Enumerated(EnumType.STRING)
  private Status status = Status.CREATED;

  private String currency = "KRW";

  @Column(name = "total_amount")
  private BigDecimal totalAmount;

  @Column(name = "paid_at")
  private LocalDateTime paidAt;

  protected ShopOrder() {}

  public ShopOrder(
    String id,
    String m,
    String key,
    String hash,
    BigDecimal total
  ) {
    this.id = id;
    memberId = m;
    idempotencyKey = key;
    requestHash = hash;
    totalAmount = total;
  }

  public String getId() {
    return id;
  }

  public String getMemberId() {
    return memberId;
  }

  public String getIdempotencyKey() {
    return idempotencyKey;
  }

  public String getRequestHash() {
    return requestHash;
  }

  public BigDecimal getTotalAmount() {
    return totalAmount;
  }

  public Status getStatus() {
    return status;
  }

  public void paid() {
    if (status == Status.CREATED) {
      status = Status.PAID;
      paidAt = LocalDateTime.now();
    }
  }

  public enum Status {
    CREATED,
    PAID,
    CANCELLED,
    REFUNDED,
  }
}
