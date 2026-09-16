package com.cosmetic.shopbackend.payment;

import com.cosmetic.shopbackend.commerce.ShopOrder;
import com.cosmetic.shopbackend.commerce.ShopOrderRepository;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.server.ResponseStatusException;

@Service
public class PaymentConfirmationService {

  private static final ZoneId SEOUL = ZoneId.of("Asia/Seoul");
  private final ShopOrderRepository orders;
  private final PortOneClient portOne;
  private final TransactionTemplate transactions;
  private final JdbcTemplate jdbc;

  public PaymentConfirmationService(
    ShopOrderRepository orders,
    PortOneClient portOne,
    PlatformTransactionManager transactionManager,
    JdbcTemplate jdbc
  ) {
    this.orders = orders;
    this.portOne = portOne;
    this.transactions = new TransactionTemplate(transactionManager);
    this.jdbc = jdbc;
  }

  public Confirmation confirm(String orderId, String memberId, String paymentId) {
    ShopOrder order = ownedOrder(orderId, memberId);
    String expectedPaymentId = "hwabun-" + orderId;
    if (!expectedPaymentId.equals(paymentId)) {
      throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "paymentId does not match order");
    }
    if (order.getStatus() == ShopOrder.Status.PAID) {
      if (paymentId.equals(order.getPaymentId())) return view(order);
      throw new ResponseStatusException(HttpStatus.CONFLICT, "order was paid by another payment method");
    }
    if (order.getStatus() != ShopOrder.Status.CREATED) {
      throw new ResponseStatusException(HttpStatus.CONFLICT, "order cannot be paid in its current status");
    }

    Map<String, Object> payment = portOne.payment(paymentId);
    validate(payment, order, paymentId);
    LocalDateTime paidAt = paidAt(payment.get("paidAt"));
    return transactions.execute(status ->
      complete(orderId, memberId, paymentId, order.getTotalAmount(), paidAt)
    );
  }

  private Confirmation complete(
    String orderId,
    String memberId,
    String paymentId,
    BigDecimal amount,
    LocalDateTime paidAt
  ) {
    int updated = orders.markVerifiedPaid(orderId, memberId, paymentId, amount, paidAt);
    jdbc.update(
      "insert into payment(payment_id,order_id,provider,status,amount,currency,paid_at,verified_at,raw_status) values(?,?,?,?,?,?,?,?,?) on duplicate key update status=values(status),amount=values(amount),paid_at=values(paid_at),verified_at=values(verified_at),raw_status=values(raw_status)",
      paymentId,
      orderId,
      "PORTONE_TEST",
      "PAID",
      amount,
      "KRW",
      paidAt,
      LocalDateTime.now(SEOUL),
      "PAID"
    );
    ShopOrder current = ownedOrder(orderId, memberId);
    if (updated == 0 && !paymentId.equals(current.getPaymentId())) {
      throw new ResponseStatusException(HttpStatus.CONFLICT, "order payment changed concurrently");
    }
    return view(current);
  }

  private ShopOrder ownedOrder(String orderId, String memberId) {
    return orders
      .findById(orderId)
      .filter(order -> order.getMemberId().equals(memberId))
      .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "order not found"));
  }

  @SuppressWarnings("unchecked")
  private void validate(Map<String, Object> payment, ShopOrder order, String paymentId) {
    if (!paymentId.equals(String.valueOf(payment.get("id")))) mismatch("payment id");
    if (!"PAID".equals(String.valueOf(payment.get("status")))) {
      throw new ResponseStatusException(HttpStatus.CONFLICT, "PortOne payment is not paid");
    }
    if (!order.getCurrency().equals(String.valueOf(payment.get("currency")))) mismatch("currency");
    Object amountValue = payment.get("amount");
    if (!(amountValue instanceof Map<?, ?>)) mismatch("amount");
    Map<String, Object> amount = (Map<String, Object>) amountValue;
    BigDecimal paid = decimal(amount.get("total"));
    if (paid.compareTo(order.getTotalAmount()) != 0) mismatch("amount");
    Object customDataValue = payment.get("customData");
    if (!(customDataValue instanceof Map<?, ?>)) mismatch("customData");
    Map<?, ?> customData = (Map<?, ?>) customDataValue;
    if (!order.getId().equals(String.valueOf(customData.get("orderId")))) mismatch("customData.orderId");
  }

  private BigDecimal decimal(Object value) {
    try {
      return new BigDecimal(String.valueOf(value));
    } catch (RuntimeException exception) {
      mismatch("amount");
      throw exception;
    }
  }

  private LocalDateTime paidAt(Object value) {
    if (value == null) return LocalDateTime.now(SEOUL);
    try {
      return OffsetDateTime.parse(String.valueOf(value)).atZoneSameInstant(SEOUL).toLocalDateTime();
    } catch (RuntimeException ignored) {
      try {
        return Instant.parse(String.valueOf(value)).atZone(SEOUL).toLocalDateTime();
      } catch (RuntimeException exception) {
        throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "PortOne paidAt is invalid", exception);
      }
    }
  }

  private void mismatch(String field) {
    throw new ResponseStatusException(HttpStatus.CONFLICT, "PortOne payment " + field + " mismatch");
  }

  private Confirmation view(ShopOrder order) {
    return new Confirmation(
      order.getId(),
      order.getStatus().name(),
      order.getPaymentId(),
      order.getPaidAmount(),
      order.getCurrency(),
      order.getPaidAt()
    );
  }

  public record Confirmation(
    String orderId,
    String status,
    String paymentId,
    BigDecimal paidAmount,
    String currency,
    LocalDateTime paidAt
  ) {}
}
